"""OpenAI-compatible client for an independently managed BitNet server."""
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("runtimeforce.service.llm.bitnet_provider")


class BitNetProvider:
    @staticmethod
    def normalize_base_url(base_url: str) -> str:
        value = (base_url or "").strip().rstrip("/")
        if not value:
            raise ValueError("BitNet server URL is not configured.")
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("BitNet URL must be an http:// or https:// address.")
        return value[:-3] if value.endswith("/v1") else value

    async def healthcheck(self, base_url: str) -> bool:
        base = self.normalize_base_url(base_url)
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.get(f"{base}/v1/models")
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def stream_chat(
        self, base_url: str, model_id: str, messages: List[Dict[str, Any]],
        temperature: float = 0.2, max_tokens: int = 4096,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        base = self.normalize_base_url(base_url)
        model_name = model_id.split("/", 1)[1] if model_id.startswith("bitnet/") else model_id
        payload = {"model": model_name, "messages": messages, "temperature": temperature,
                   "max_tokens": max_tokens, "stream": True}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        timeout = httpx.Timeout(180.0, connect=10.0, read=120.0)
        tool_calls: Dict[int, Dict[str, str]] = {}
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", f"{base}/v1/chat/completions", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        logger.debug("Ignoring malformed BitNet SSE chunk")
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        yield {"status": "streaming", "content": delta["content"]}
                    for call in delta.get("tool_calls") or []:
                        index = int(call.get("index", 0))
                        item = tool_calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                        if call.get("id"):
                            item["id"] = call["id"]
                        function = call.get("function") or {}
                        item["name"] += function.get("name") or ""
                        item["arguments"] += function.get("arguments") or ""
                    if choice.get("finish_reason") == "tool_calls" and tool_calls:
                        calls = [{"id": item["id"] or f"bitnet_call_{index}", "name": item["name"],
                                  "arguments": item["arguments"] or "{}"}
                                 for index, item in sorted(tool_calls.items()) if item["name"]]
                        if calls:
                            yield {"status": "tool_calls", "calls": calls}
