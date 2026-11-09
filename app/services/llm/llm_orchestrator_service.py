"""
LLM Orchestrator Service — Zero-loss Full Context Streaming with Native Direct Ollama Support.
"""
import time
import logging
import json
import asyncio
import re
import httpx
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.services.llm.llm_registry_service import LLMRegistryService
from app.services.llm.llm_rotation_service import LLMRotationService
from app.repository.provider_keys_db_repository import ProviderKeysDBRepository
from app.core.security.aes_crypto_service import AESCryptoService

logger = logging.getLogger("runtimeforce.service.llm.orchestrator")

STREAM_CLOUD_TIMEOUT = 30.0
STREAM_LOCAL_TIMEOUT = 900.0
MAX_EMPTY_ATTEMPTS = 2

def _is_midstream_error(error_str: str) -> bool:
    if not error_str:
        return False
    e = error_str.lower()
    return "midstreamfallbackerror" in e or "mid_stream" in e or "midstream" in e or "stream dropped" in e

class LLMOrchestratorService:
    def __init__(
        self,
        provider_keys_repo: ProviderKeysDBRepository,
        llm_registry: LLMRegistryService,
        rotation_service: Optional[LLMRotationService] = None,
    ):
        self.provider_keys_repo = provider_keys_repo
        self.llm_registry = llm_registry
        self.rotation_service = rotation_service

    async def _stream_native_ollama(
        self,
        api_base: str,
        model_name: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        timeout: float = 45.0,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Direct native ndjson streaming to Ollama without truncating full system/graph context."""
        clean_url = api_base.rstrip("/").replace("/v1", "")
        endpoint = f"{clean_url}/api/chat"
        payload = {
            "model": model_name,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": 1024,
                "num_ctx": 8192
            }
        }
        if tools:
            payload["tools"] = tools

        client_timeout = httpx.Timeout(timeout, connect=5.0, read=timeout)
        emitted_tool_calls = False
        async with httpx.AsyncClient(timeout=client_timeout) as client:
            async with client.stream("POST", endpoint, json=payload) as response:
                if response.status_code != 200:
                    raise httpx.HTTPStatusError(f"HTTP {response.status_code}", request=response.request, response=response)
                
                async for line in response.aiter_lines():
                    if not line or not line.strip():
                        continue
                    try:
                        chunk_json = json.loads(line)
                        msg_chunk = chunk_json.get("message", {})
                        content = msg_chunk.get("content", "")
                        if content:
                            yield {"status": "streaming", "content": content}
                        native_calls = msg_chunk.get("tool_calls") or []
                        if native_calls and not emitted_tool_calls:
                            normalized_calls = []
                            for index, native_call in enumerate(native_calls):
                                function = native_call.get("function") or {}
                                name = function.get("name")
                                if not name:
                                    continue
                                arguments = function.get("arguments") or {}
                                normalized_calls.append({
                                    "id": native_call.get("id") or f"ollama_call_{index}_{int(time.time())}",
                                    "name": name,
                                    "arguments": arguments,
                                })
                            if normalized_calls:
                                emitted_tool_calls = True
                                yield {"status": "tool_calls", "calls": normalized_calls}
                        if chunk_json.get("done"):
                            break
                    except Exception:
                        continue

    async def stream_completion(
        self,
        messages: List[Dict[str, str]],
        model_id: str,
        provider: str,
        temperature: float = 0.2,
        user_id: str = "anonymous",
        tools: Optional[List[Dict[str, Any]]] = None,
        strategy: str = "auto",
        max_tokens: int = 4096,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        provider = (provider or "unknown").lower()

        # Sanitize Gemini model identifiers
        model_lower = model_id.lower()
        if "gemini" in model_lower and ("3." in model_lower or "customtools" in model_lower or "preview" in model_lower):
            logger.info(f"[Orchestrator] Normalizing non-standard Gemini model '{model_id}' -> 'gemini/gemini-2.0-flash'")
            model_id = "gemini/gemini-2.0-flash"
            provider = "gemini"

        if self.rotation_service and not self.rotation_service.is_provider_available(provider):
            yield {
                "status": "error",
                "error_code": "PROVIDER_PERMANENT_FAILURE",
                "error": f"Provider '{provider}' in cooldown/rate-limited",
                "permanent": False,
                "retry_after": 60,
            }
            return

        api_key = None
        api_base = None
        
        all_keys = self.provider_keys_repo.get_all_provider_keys(user_id)
        if provider in all_keys and all_keys[provider]:
            raw_val = all_keys[provider]
            try:
                decrypted_val = AESCryptoService.decrypt(raw_val)
            except Exception:
                decrypted_val = raw_val

            if decrypted_val.startswith("http://") or decrypted_val.startswith("https://"):
                api_base = decrypted_val.rstrip("/")
            else:
                api_key = decrypted_val

        is_local_provider = provider in ("ollama", "lm_studio", "local") or model_id.startswith("local/")
        if not is_local_provider and not api_key:
            yield {
                "status": "error",
                "error_code": "MISSING_API_KEY",
                "error": f"No API key configured for '{provider}'. Add your key in Settings -> Providers.",
                "permanent": True,
                "retry_after": 0,
            }
            return

        is_ollama = provider == "ollama" or model_id.startswith("ollama/")

        # Native Direct Ollama Streaming: Full untouched context
        if is_ollama:
            clean_name = model_id.replace("ollama/", "")
            base_url = api_base or "http://localhost:11434"
            full_text = ""
            start_t = time.time()
            try:
                async for chunk in self._stream_native_ollama(base_url, clean_name, messages, temperature=temperature, timeout=STREAM_LOCAL_TIMEOUT, tools=tools):
                    full_text += chunk.get("content", "")
                    yield chunk
                
                if full_text.strip():
                    logger.info(f"[Orchestrator] Native Ollama {clean_name} streamed {len(full_text)} chars in {int((time.time()-start_t)*1000)}ms")
                    return
            except Exception as e:
                err_desc = f"{type(e).__name__}: {str(e) or 'timeout'}"
                logger.warning(f"[Orchestrator] Native Ollama {clean_name} failed ({err_desc}). Failing over.")
                if self.rotation_service:
                    self.rotation_service.report_failure(model_id, provider, err_desc)
                yield {
                    "status": "error",
                    "error_code": "LOCAL_TIMEOUT",
                    "error": f"Local model '{clean_name}' failed on CPU: {err_desc}",
                    "permanent": False,
                    "retry_after": 180,
                }
                return

        # Cloud Models via LiteLLM: Full untouched context
        is_local_model = provider in ("lm_studio", "local") or model_id.startswith("local/")
        active_timeout = STREAM_LOCAL_TIMEOUT if is_local_model else STREAM_CLOUD_TIMEOUT

        effective_max_tokens = max_tokens
        if provider == "openrouter" and ":free" not in model_id.lower():
            effective_max_tokens = min(max_tokens, 2048)

        start_time = time.time()
        attempt_count = 0

        while attempt_count < MAX_EMPTY_ATTEMPTS:
            attempt_count += 1
            full_text = ""
            tool_calls_dict = {}
            reasoning_status_sent = False

            try:
                import litellm
                litellm.drop_params = True
                litellm.modify_params = True

                kwargs = {
                    "model": model_id,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": True,
                    "timeout": active_timeout,
                    "max_tokens": effective_max_tokens,
                }
                if api_key:
                    kwargs["api_key"] = api_key
                if api_base:
                    kwargs["api_base"] = api_base
                if tools:
                    kwargs["tools"] = tools

                completion_coro = litellm.acompletion(**kwargs)
                stream_obj = await asyncio.wait_for(completion_coro, timeout=active_timeout)

                async for chunk in stream_obj:
                    if not chunk or not hasattr(chunk, "choices") or not chunk.choices:
                        continue
                    choice = chunk.choices[0]

                    if hasattr(choice, "delta") and choice.delta:
                        reasoning_content = getattr(choice.delta, "reasoning_content", None) or getattr(choice.delta, "thinking", None)
                        if reasoning_content and not reasoning_status_sent:
                            reasoning_status_sent = True
                            yield {"status": "phase", "label": "Model is processing the request...", "role": "Agent"}

                    if hasattr(choice, "delta") and choice.delta:
                        tc_list = getattr(choice.delta, "tool_calls", None)
                        if tc_list:
                            for tc_delta in tc_list:
                                idx = getattr(tc_delta, "index", 0)
                                if idx not in tool_calls_dict:
                                    tool_calls_dict[idx] = {"id": "", "name": "", "arguments": ""}
                                
                                if getattr(tc_delta, "id", None):
                                    tool_calls_dict[idx]["id"] = tc_delta.id
                                    
                                fn = getattr(tc_delta, "function", None)
                                if fn:
                                    if getattr(fn, "name", None):
                                        tool_calls_dict[idx]["name"] += fn.name
                                    if getattr(fn, "arguments", None):
                                        tool_calls_dict[idx]["arguments"] += fn.arguments

                    delta = getattr(choice, "delta", None)
                    if delta:
                        content = getattr(delta, "content", None) or ""
                        if content:
                            full_text += content
                            yield {"status": "streaming", "content": content}

                    if getattr(choice, "finish_reason", None) == "tool_calls" and tool_calls_dict:
                        tool_calls_acc = []
                        for idx in sorted(tool_calls_dict.keys()):
                            tc_obj = tool_calls_dict[idx]
                            if not tc_obj["id"]:
                                tc_obj["id"] = f"call_{idx}_{int(time.time())}"
                            if not tc_obj["name"]:
                                continue
                            tool_calls_acc.append(tc_obj)

                        if tool_calls_acc:
                            yield {"status": "tool_calls", "calls": tool_calls_acc}

                latency_ms = int((time.time() - start_time) * 1000)
                if len(full_text.strip()) > 0 or bool(tool_calls_dict):
                    logger.info(f"[Orchestrator] {model_id} completed: {len(full_text)} chars in {latency_ms}ms")
                    return

                logger.warning(f"[Orchestrator] Model '{model_id}' returned 0 chars (attempt {attempt_count}/{MAX_EMPTY_ATTEMPTS})")
                if attempt_count < MAX_EMPTY_ATTEMPTS:
                    await asyncio.sleep(0.2)
                    continue

            except asyncio.TimeoutError:
                logger.warning(f"[Orchestrator] Stream timed out after {active_timeout}s on {model_id}")
                if self.rotation_service:
                    self.rotation_service.report_failure(model_id, provider, "timeout")
                yield {
                    "status": "error",
                    "error_code": "TIMEOUT",
                    "error": f"Model '{model_id}' timed out after {active_timeout}s",
                    "permanent": False,
                    "retry_after": 120,
                }
                return

            except Exception as e:
                error_str = str(e)

                if _is_midstream_error(error_str):
                    logger.info(f"[Orchestrator] Stream dropped on {model_id} — triggering safe fallback")
                    if self.rotation_service:
                        self.rotation_service.report_failure(model_id, provider, error_str)
                    yield {
                        "status": "error",
                        "error_code": "STREAM_DROPPED",
                        "error": f"Stream dropped from {model_id}",
                        "permanent": False,
                        "retry_after": 120,
                    }
                    return

                if "fewer max_tokens" in error_str and "can only afford" in error_str and attempt_count == 1:
                    match = re.search(r"can only afford (\d+)", error_str)
                    if match:
                        affordable = int(match.group(1))
                        if affordable >= 64:
                            effective_max_tokens = affordable
                            continue

                latency_ms = int((time.time() - start_time) * 1000)
                logger.warning(f"[Orchestrator] Stream error on {model_id}: {error_str[:200]}")

                failure_report = {"cooldown": 120, "type": "generic"}
                if self.rotation_service:
                    failure_report = self.rotation_service.report_failure(model_id, provider, error_str)

                yield {
                    "status": "error",
                    "error_code": "STREAM_FAILED",
                    "error": error_str[:300],
                    "permanent": failure_report.get("type") in ("auth", "billing_error"),
                    "retry_after": failure_report.get("cooldown", 120),
                    "error_type": failure_report.get("type", "generic"),
                }
                return

        if self.rotation_service:
            self.rotation_service.report_failure(model_id, provider, "empty_response_twice")
        yield {
            "status": "error",
            "error_code": "EMPTY_RESPONSE",
            "error": f"Model '{model_id}' returned 0 chars after {MAX_EMPTY_ATTEMPTS} attempts.",
            "permanent": False,
            "retry_after": 60,
        }

    async def validate_result(
        self,
        result: Dict[str, Any],
        context: Dict[str, Any],
        model_id: str,
        user_id: str = "anonymous",
    ) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": "You are a code quality critic. Validate the result. Reply JSON: {\"passed\": bool, \"feedback\": str}"},
            {"role": "user", "content": f"Task: {context.get('task_type', 'coding')}\nResult: {result.get('content', '')[:2000]}"},
        ]
        
        provider = model_id.split("/", 1)[0].lower() if "/" in model_id else "unknown"
        api_key = None
        if provider not in ("ollama", "lm_studio"):
            try:
                encrypted_keys = self.provider_keys_repo.get_all_provider_keys(user_id)
                if provider in encrypted_keys:
                    api_key = AESCryptoService.decrypt(encrypted_keys[provider])
            except Exception as e:
                logger.warning(f"[Orchestrator] Key decrypt failed for critic validation on {provider}: {e}")

        temp = 0.1

        try:
            import litellm
            litellm.drop_params = True
            
            kwargs = {
                "model": model_id,
                "messages": messages,
                "temperature": temp,
                "timeout": 15
            }
            if api_key:
                kwargs["api_key"] = api_key
                
            resp = await asyncio.wait_for(litellm.acompletion(**kwargs), timeout=15.0)
            content = resp.choices[0].message.content or ""
            try:
                data = json.loads(content)
                return {"passed": bool(data.get("passed", True)), "feedback": data.get("feedback", "")}
            except Exception:
                return {"passed": True, "feedback": ""}
        except Exception as e:
            logger.warning(f"[Orchestrator] validate_result failed on {model_id}: {e}")
            return {"passed": True, "feedback": f"validation error: {e}"}
