"""
LLM Orchestrator Core for RuntimeForce.
Добавлена защита от repetition loops и галлюцинаций моделей.
"""
import os
import time
import logging
import json
import re
import asyncio
from typing import AsyncGenerator, List, Dict, Any, Optional
import litellm
from app.core.llm.registry import model_registry
from app.memory.store import store

logger = logging.getLogger("ai_runtime.llm.orchestrator")

litellm.drop_params = True
litellm.telemetry = False
litellm.suppress_debug_info = True
logging.getLogger("LiteLLM").setLevel(logging.WARNING)

ENV_MAPPING = {
    "gemini": "GEMINI_API_KEY", "google": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY", "groq": "GROQ_API_KEY",
    "sambanova": "SAMBANOVA_API_KEY", "cerebras": "CEREBRAS_API_KEY",
    "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
    "mistral": "MISTRAL_API_KEY", "together": "TOGETHERAI_API_KEY",
    "fireworks": "FIREWORKS_API_KEY", "cohere": "COHERE_API_KEY",
    "perplexity": "PERPLEXITYAI_API_KEY", "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY", "nvidia": "NVIDIA_NIM_API_KEY",
}

PROVIDER_TIERS = {
    "gemini": "free", "google": "free", "openrouter": "free",
    "groq": "free", "sambanova": "free", "cerebras": "free",
    "openai": "pro", "anthropic": "pro", "mistral": "pro",
    "together": "pro", "fireworks": "pro", "cohere": "pro",
    "perplexity": "pro", "xai": "pro", "deepseek": "pro", "nvidia": "pro",
    "ollama": "local", "lm_studio": "local",
}

STRATEGY_PRIORITIES = {
    "coding": ["gemini", "groq", "deepseek", "openrouter", "anthropic", "openai", "cerebras"],
    "consilium": ["gemini", "anthropic", "openai", "deepseek", "cerebras"],
    "manual": [],
}

# Паттерны для детекции repetition loops (галлюцинаций)
REPETITION_PATTERNS = [
    r"(we will run[.\s]*){3,}",
    r"(let'?s (run|execute|do it)[.\s]*){3,}",
    r"(we need to run[.\s]*){3,}",
    r"(now[.\s]*){5,}",
    r"(execute[.\s]*){4,}",
]


class ModelRegistryProxy:
    @staticmethod
    def classify_tier(model_id: str) -> int:
        mid_lower = model_id.lower()
        tier_1_keywords = [
            "gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0", "gemini-2.5",
            "gemini-3.0", "gemini-3.5", "gpt-4o", "gpt-4-turbo", "gpt-4o-mini",
            "claude-3-5-sonnet", "claude-3-5-haiku", "claude-3-opus",
            "deepseek-coder", "deepseek-chat", "deepseek-v3",
            "qwen3-coder", "llama-3.3", "gpt-oss-120b"
        ]
        if any(kw in mid_lower for kw in tier_1_keywords):
            return 1
        if "ollama" in mid_lower or "lm_studio" in mid_lower:
            match = re.search(r':(\d+)b', mid_lower)
            if match and int(match.group(1)) >= 14:
                return 1
        return 2

    @staticmethod
    def is_text_model(model_id: str) -> bool:
        mid_lower = model_id.lower()
        blacklisted = [
            "-image", "image-", "/image", "-tts", "tts-", "/tts", "preview-tts",
            "-embedding", "embedding-", "-audio", "audio-", "-music", "-video",
            "whisper", "dall-e", "dalle", "stable-diffusion", "sdxl",
            "playai", "orpheus", "computer-use",
        ]
        if any(kw in mid_lower for kw in blacklisted):
            return False
        return True

    @staticmethod
    def detect_repetition_loop(text: str) -> bool:
        """Детектирует repetition loops (галлюцинации) в тексте."""
        if not text or len(text) < 50:
            return False
        text_lower = text.lower()
        for pattern in REPETITION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        # Дополнительная проверка: если одна фраза повторяется > 5 раз
        words = text_lower.split()
        if len(words) > 20:
            word_counts = {}
            for word in words:
                word_counts[word] = word_counts.get(word, 0) + 1
            max_count = max(word_counts.values()) if word_counts else 0
            if max_count > len(words) * 0.3:  # > 30% слов — одно и то же
                return True
        return False


class Router:
    @staticmethod
    def build_route(
        strategy: str,
        model_lock: Optional[str],
        plan: str,
        provider_keys: Dict[str, str],
        cooldown_models: Dict[str, float],
        preferred_models: Dict[str, List[str]],
        scores: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        now = time.time()
        active_cooldown_models = {m: t for m, t in cooldown_models.items() if t > now}

        if strategy == "manual" and model_lock:
            meta = model_registry.get_model(model_lock)
            if meta and (meta.provider in provider_keys or meta.provider in ["ollama", "lm_studio"]):
                if model_lock not in active_cooldown_models:
                    return [model_lock]
            return []

        if strategy == "consilium":
            all_models = model_registry.get_available_models()
            candidates = [
                m for m in all_models
                if (m.provider in provider_keys or m.provider in ["ollama", "lm_studio"])
                and m.id not in active_cooldown_models
                and ModelRegistryProxy.classify_tier(m.id) == 1
                and ModelRegistryProxy.is_text_model(m.id)
            ]
            priority_order = STRATEGY_PRIORITIES["consilium"]

            def sort_key(m):
                try:
                    pr = priority_order.index(m.provider)
                except ValueError:
                    pr = 100
                score = scores.get(m.id, {}).get("total", 50.0)
                v = 0
                if "3.5" in m.id: v = -40
                elif "2.5" in m.id: v = -30
                elif "2.0" in m.id: v = -20
                elif "1.5" in m.id: v = -10
                return (pr, (100 - score), v, m.name)

            candidates.sort(key=sort_key)
            return [m.id for m in candidates]

        all_models = model_registry.get_available_models()
        is_pro_user = plan in ("pro", "studio", "enterprise")

        candidates = []
        for m in all_models:
            if m.id in active_cooldown_models:
                continue
            has_key = m.provider in provider_keys or m.provider in ["ollama", "lm_studio"]
            if not has_key:
                continue
            if not ModelRegistryProxy.is_text_model(m.id):
                continue
            provider_tier = PROVIDER_TIERS.get(m.provider, "pro")
            if not is_pro_user and provider_tier == "pro":
                continue
            if not is_pro_user and m.tier != "free":
                continue
            provider_preferred = preferred_models.get(m.provider, [])
            if provider_preferred and m.id not in provider_preferred:
                continue
            if ModelRegistryProxy.classify_tier(m.id) != 1:
                continue
            candidates.append(m)

        if not candidates:
            raise ValueError(f"Нет доступных Tier-1 моделей для режима '{strategy}' и тарифа '{plan}'.")

        priority_order = STRATEGY_PRIORITIES.get(strategy, STRATEGY_PRIORITIES["coding"])

        def sort_key(m):
            try:
                pr = priority_order.index(m.provider)
            except ValueError:
                pr = 100
            score = scores.get(m.id, {}).get("total", 50.0)
            v = 0
            if "3.5" in m.id: v = -40
            elif "2.5" in m.id: v = -30
            elif "2.0" in m.id: v = -20
            elif "1.5" in m.id: v = -10
            preferred_bonus = -50 if m.id in preferred_models.get(m.provider, []) else 0
            return (pr, preferred_bonus, (100 - score), v, m.name)

        candidates.sort(key=sort_key)
        return [m.id for m in candidates]


class LLMOrchestrator:
    def __init__(self):
        self.provider_keys: Dict[str, str] = {}
        self.cooldown_models: Dict[str, float] = {}
        self.cooldown_providers: Dict[str, float] = {}
        self.preferred_models: Dict[str, List[str]] = {}
        self.cooldown_duration = 60.0
        self.cooldown_no_tools = 3600.0
        self.cooldown_terms = 10800.0
        self.cooldown_repetition = 600.0  # 10 минут за repetition loop
        self.current_model: Optional[str] = None

    def set_provider_keys(self, keys: Dict[str, str]):
        self.provider_keys = {k: v for k, v in keys.items() if v and v.strip()}
        self._apply_to_environment()

    def update_provider_keys(self, new_keys: Dict[str, str]):
        for provider, key in new_keys.items():
            if key and key.strip():
                self.provider_keys[provider] = key
            elif provider in self.provider_keys:
                del self.provider_keys[provider]
        self._apply_to_environment()

    def set_preferred_models(self, preferred: Dict[str, List[str]]):
        self.preferred_models = {k: v for k, v in preferred.items() if v}

    def _apply_to_environment(self):
        for provider, key in self.provider_keys.items():
            env_var = ENV_MAPPING.get(provider)
            if env_var:
                os.environ[env_var] = key

    def get_models_for_mode(self, strategy: str, model_lock: Optional[str] = None, plan: str = "free") -> List[str]:
        scores = store.get_model_scores()
        try:
            route = Router.build_route(
                strategy=strategy,
                model_lock=model_lock,
                plan=plan,
                provider_keys=self.provider_keys,
                cooldown_models=self.cooldown_models,
                preferred_models=self.preferred_models,
                scores=scores
            )
            if not route:
                raise ValueError(f"Реестр моделей пуст для режима '{strategy}'.")
            return route
        except ValueError as ve:
            logger.error(f"Routing error: {ve}")
            raise ve

    def _get_route(self, strategy: str, model_lock: Optional[str], needs_tools: bool = False, plan: str = "free") -> List[str]:
        route = self.get_models_for_mode(strategy, model_lock, plan)
        if self.current_model and self.current_model in route:
            route.remove(self.current_model)
            route.insert(0, self.current_model)
        elif route:
            self.current_model = route[0]
        return route

    async def stream_completion(
        self,
        messages: List[Dict[str, str]],
        strategy: str = "coding",
        model_lock: Optional[str] = None,
        temperature: float = 0.2,
        tools: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
        consilium_draft_model: Optional[str] = None,
        consilium_critic_model: Optional[str] = None,
        consilium_synth_model: Optional[str] = None,
        plan: str = "free",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"🎯 Stream: strategy={strategy}, model_lock={model_lock}, tools={'YES' if tools else 'NO'}")

        if strategy == "consilium":
            async for chunk in self._run_consilium_debate(
                messages, temperature, session_id,
                draft_lock=consilium_draft_model,
                critic_lock=consilium_critic_model,
                synth_lock=consilium_synth_model,
                plan=plan
            ):
                yield chunk
            return

        needs_tools = bool(tools)
        try:
            route = self._get_route(strategy, model_lock, needs_tools=needs_tools, plan=plan)
        except ValueError as ve:
            yield {"status": "no_models", "error": str(ve), "strategy": strategy}
            return

        if not route:
            yield {"status": "no_models", "error": "Нет доступных моделей.", "strategy": strategy}
            return

        consecutive_errors = 0
        MAX_CONSECUTIVE_ERRORS = 3
        model_idx = 0

        while model_idx < len(route):
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.critical(f"🚨 Circuit Breaker: {consecutive_errors} errors. Aborting.")
                yield {"status": "failed", "error": "Gateway/Network unreachable.", "strategy": strategy}
                return

            model_id = route[model_idx]
            meta = model_registry.get_model(model_id)
            if not meta:
                model_idx += 1
                continue

            now = time.time()
            if meta.provider in self.cooldown_providers and self.cooldown_providers[meta.provider] > now:
                logger.info(f"⏭ Skipping {model_id}: provider {meta.provider} on cooldown")
                model_idx += 1
                continue

            yield {
                "status": "model_try",
                "model": model_id,
                "provider": meta.provider,
                "tier": meta.tier,
                "strategy": strategy,
                "timestamp": time.time(),
            }
            start_time = time.time()
            tokens_in = sum(len(m.get("content", "")) // 4 for m in messages)
            tokens_out = 0
            full_content = ""  # Для детекции repetition loops

            try:
                env_var = ENV_MAPPING.get(meta.provider)
                if env_var and meta.provider in self.provider_keys:
                    os.environ[env_var] = self.provider_keys[meta.provider]

                local_messages = list(messages)
                short_name = model_id.split("/")[-1]

                core_system_prompt = (
                    "You are RuntimeForce AI, an autonomous Senior Software Engineer operating directly "
                    "Always respond in the exact same language used by the user in their prompt."
                    "inside the user's local IDE, SSH and terminal environment.\n\n"
                    "YOUR CAPABILITIES:\n"
                    "- You have FULL ACCESS to the user's local filesystem and terminal\n"
                    "- You can read, write, and modify any files in the workspace\n"
                    "- You can execute shell commands (bash, git, npm, python, etc.)\n"
                    "- You can scan directory structures and search for code patterns\n"
                    "- You are NOT a cloud-based chatbot. You are an execution engine running locally.\n\n"
                    "CORE DIRECTIVES:\n"
                    "1. ZERO-WATER: Be extremely concise. No introductions or moral lectures.\n"
                    "2. NO DELEGATION: NEVER tell the user to run commands themselves. Execute them using tools.\n"
                    "3. READ-ONLY vs WRITE: Classify requests before acting.\n"
                    "4. TOOL EXECUTION: Use native JSON tool calling when tools are provided.\n"
                    "5. CONVERSATIONAL: If user just greets or asks simple questions, respond with text ONLY. DO NOT call scan_workspace or execute_command for greetings.\n"
                    "6. NO REPETITION: Never repeat the same phrase multiple times. If you need to think, just output your reasoning once.\n"
                    "7. ROLE: You are an execution engine, not a consultant.\n\n"
                    "IMPORTANT: Even if tools are not provided in this request, you still have access to the "
                    "user's environment. If the user asks about files, directories, or commands, you CAN "
                    "help by calling the appropriate tools when they become available."
                )
                full_system = f"{core_system_prompt}\n[System: {short_name} via {meta.provider}]"

                if local_messages and local_messages[0]["role"] == "system":
                    first_sys = dict(local_messages[0])
                    first_sys["content"] += f"\n\n{full_system}"
                    local_messages[0] = first_sys
                else:
                    local_messages.insert(0, {"role": "system", "content": full_system})

                max_tokens_limit = min(meta.max_output_tokens, 8192) if meta.max_output_tokens else 4096
                kwargs: Dict[str, Any] = {
                    "model": model_id,
                    "messages": local_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens_limit,
                    "stream": True,
                }

                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                    if strategy == "coding":
                        kwargs["parallel_tool_calls"] = False

                response = await litellm.acompletion(**kwargs)
                async for chunk in response:
                    if not chunk or not hasattr(chunk, "choices") or not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta = getattr(choice, "delta", None)
                    if delta is None:
                        continue
                    content = getattr(delta, "content", None) or ""
                    if content:
                        tokens_out += len(content) // 4
                        full_content += content
                        
                        # ДЕТЕКЦИЯ REPETITION LOOP В РЕАЛЬНОМ ВРЕМЕНИ
                        if len(full_content) > 100 and ModelRegistryProxy.detect_repetition_loop(full_content):
                            logger.warning(f"🔁 Repetition loop detected in {model_id}. Aborting stream.")
                            # Баним модель на 10 минут
                            self.cooldown_models[model_id] = time.time() + self.cooldown_repetition
                            yield {
                                "status": "model_error",
                                "model": model_id,
                                "provider": meta.provider,
                                "error": "Repetition loop detected. Switching to next model.",
                                "elapsed_ms": int((time.time() - start_time) * 1000),
                                "error_type": "RepetitionLoop",
                                "strategy": strategy,
                            }
                            model_idx += 1
                            return  # Прерываем стрим, переходим к следующей модели
                    
                    yield {
                        "model": model_id,
                        "provider": meta.provider,
                        "content": content,
                        "tool_calls": getattr(delta, "tool_calls", None),
                        "finish_reason": getattr(choice, "finish_reason", None),
                        "status": "streaming",
                        "strategy": strategy,
                    }

                elapsed = int((time.time() - start_time) * 1000)
                store.log_telemetry(
                    model_id=model_id, provider=meta.provider, latency_ms=elapsed,
                    tokens_in=tokens_in, tokens_out=tokens_out, success=True,
                    strategy=strategy, was_fallback=False, session_id=session_id,
                )
                self.current_model = model_id
                yield {
                    "status": "model_success",
                    "model": model_id,
                    "provider": meta.provider,
                    "elapsed_ms": elapsed,
                    "tokens_out": tokens_out,
                    "strategy": strategy,
                }
                consecutive_errors = 0
                return

            except Exception as e:
                elapsed = int((time.time() - start_time) * 1000)
                error_type = type(e).__name__
                error_msg = str(e).lower()

                is_rate_limit = any(x in error_msg for x in [
                    "429", "quota", "rate_limit", "exhausted",
                    "too many requests", "limit exceeded", "requires more credits"
                ])
                is_network_or_gateway = any(x in error_msg for x in [
                    "502", "503", "504", "bad gateway", "connection",
                    "timeout", "maximum context length exceeded"
                ])

                store.log_telemetry(
                    model_id=model_id, provider=meta.provider, latency_ms=elapsed,
                    tokens_in=tokens_in, tokens_out=0, success=False,
                    error_type=error_type, strategy=strategy, was_fallback=True, session_id=session_id,
                )
                if self.current_model == model_id:
                    self.current_model = None

                if is_rate_limit:
                    consecutive_errors += 1
                    self.cooldown_models[model_id] = time.time() + 300.0
                    self.cooldown_providers[meta.provider] = time.time() + 120.0
                    logger.warning(f"⚠️ Rate Limit: {model_id} ({meta.provider}). Cooldown: model=300s, provider=120s")
                    yield {
                        "status": "model_error",
                        "model": model_id,
                        "provider": meta.provider,
                        "error": f"Rate limit. Switching provider...",
                        "elapsed_ms": elapsed,
                        "error_type": error_type,
                        "strategy": strategy,
                    }
                    model_idx += 1
                    continue

                elif is_network_or_gateway:
                    consecutive_errors += 1
                    wait_time = min(30, 2 ** consecutive_errors)
                    self.cooldown_models[model_id] = time.time() + 300.0
                    yield {
                        "status": "model_error",
                        "model": model_id,
                        "provider": meta.provider,
                        "error": f"Network error. Sleeping {wait_time}s...",
                        "elapsed_ms": elapsed,
                        "error_type": error_type,
                        "strategy": strategy,
                    }
                    await asyncio.sleep(wait_time)
                    model_idx += 1
                    continue

                else:
                    consecutive_errors = 0
                    cooldown_sec = self.cooldown_duration
                    if "tool calling" in error_msg and "not supported" in error_msg:
                        cooldown_sec = self.cooldown_no_tools
                    elif "payload" in error_msg:
                        cooldown_sec = 3600.0
                    elif "terms acceptance" in error_msg or "requires terms" in error_msg:
                        cooldown_sec = self.cooldown_terms
                    self.cooldown_models[model_id] = time.time() + cooldown_sec
                    yield {
                        "status": "model_error",
                        "model": model_id,
                        "provider": meta.provider,
                        "error": str(e)[:150],
                        "elapsed_ms": elapsed,
                        "error_type": error_type,
                        "strategy": strategy,
                    }
                    model_idx += 1
                    continue

        yield {"status": "failed", "error": "Каскад моделей исчерпан.", "strategy": strategy}

    async def _run_consilium_debate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        session_id: Optional[str] = None,
        draft_lock: Optional[str] = None,
        critic_lock: Optional[str] = None,
        synth_lock: Optional[str] = None,
        plan: str = "expert",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        strategy = "consilium"
        logger.info(f"👥 Consilium: draft={draft_lock}, critic={critic_lock}, synth={synth_lock}")

        route = self._get_route(strategy, None, needs_tools=False, plan=plan)

        model_a = draft_lock if draft_lock else (route[0] if route else None)
        model_b = critic_lock if critic_lock else (route[1] if len(route) > 1 else model_a)
        model_c = synth_lock if synth_lock else (route[2] if len(route) > 2 else model_a)

        if not model_a or not model_b or not model_c:
            yield {
                "status": "fallback",
                "message": "Недостаточно моделей для консилиума. Перехожу в coding...",
                "strategy": strategy,
            }
            async for chunk in self.stream_completion(messages, "coding", temperature=temperature, session_id=session_id, plan=plan):
                yield chunk
            return

        user_query = messages[-1]["content"] if messages else ""

        yield {
            "status": "fallback",
            "message": f"👥 Шаг 1/3: Генерация черновика ({model_a.split('/')[-1]})...",
            "strategy": strategy,
        }
        model_a_chunks = []
        try:
            async for chunk in self.stream_completion(messages, "coding", model_lock=model_a, temperature=temperature, session_id=session_id, plan=plan):
                if chunk.get("status") == "streaming" and chunk.get("content"):
                    model_a_chunks.append(chunk["content"])
        except Exception as e:
            logger.error(f"Consilium Step 1 failed: {e}")
            yield {"status": "fallback", "message": "Сбой консилиума. Перехожу к coding...", "strategy": strategy}
            async for chunk in self.stream_completion(messages, "coding", temperature=temperature, session_id=session_id, plan=plan):
                yield chunk
            return

        model_a_response = "".join(model_a_chunks).strip()
        if not model_a_response:
            model_a_response = "Не удалось сгенерировать черновик."

        yield {
            "status": "fallback",
            "message": f"👥 Шаг 2/3: Перекрестный аудит ({model_b.split('/')[-1]})...",
            "strategy": strategy,
        }
        critique_prompt = (
            "You are a Lead Code Reviewer in RuntimeForce AI Consilium.\n\n"
            "TASK:\n"
            "1. Review the proposed solution critically.\n"
            "2. Find logical flaws, security issues, over-engineering.\n"
            "3. Provide corrected, optimized answer.\n\n"
            "RULES: No filler. Get straight to flaws. NO REPETITION.\n\n"
            f"USER REQUEST:\n{user_query}\n\n"
            f"PROPOSED SOLUTION:\n{model_a_response}"
        )
        model_b_chunks = []
        try:
            async for chunk in self.stream_completion([{"role": "user", "content": critique_prompt}], "coding", model_lock=model_b, temperature=temperature, session_id=session_id, plan=plan):
                if chunk.get("status") == "streaming" and chunk.get("content"):
                    model_b_chunks.append(chunk["content"])
        except Exception as e:
            logger.error(f"Consilium Step 2 failed: {e}")
            model_b_chunks = ["Аудит не получен."]

        model_b_response = "".join(model_b_chunks).strip()

        yield {
            "status": "fallback",
            "message": f"👥 Шаг 3/3: СВЕРХСИНТЕЗ ({model_c.split('/')[-1]})...",
            "strategy": strategy,
        }
        synthesis_prompt = (
            f"You are the Lead Architect. Merge draft and critique, fix all errors, eliminate filler, "
            f"output final answer in Russian. NO REPETITION LOOPS.\n\n"
            f"USER REQUEST:\n{user_query}\n\n"
            f"DRAFT:\n{model_a_response}\n\n"
            f"CRITIQUE:\n{model_b_response}"
        )

        model_c_chunks = []
        try:
            async for chunk in self.stream_completion([{"role": "user", "content": synthesis_prompt}], "coding", model_lock=model_c, temperature=temperature, session_id=session_id, plan=plan):
                if chunk.get("status") == "streaming" and chunk.get("content"):
                    model_c_chunks.append(chunk["content"])
                yield chunk
        except Exception as e:
            logger.error(f"Consilium Step 3 failed: {e}")

        model_c_response = "".join(model_c_chunks).strip()

        if not model_c_response:
            logger.warning("Consilium Step 3 empty (safety filter?). Fallback to draft.")
            yield {
                "status": "streaming",
                "content": "\n\n⚠️ *Финальный синтез заблокирован. Выдаю черновик:*\n\n",
                "strategy": strategy,
            }
            yield {"status": "streaming", "content": model_a_response, "strategy": strategy}


orchestrator = LLMOrchestrator()