import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from app.services.llm.bitnet_manager import bitnet_manager

logger = logging.getLogger("runtimeforce.service.llm.bitnet_provider")


class BitNetProvider:
    def __init__(self, manager=bitnet_manager):
        self.manager = manager

    async def healthcheck(self) -> bool:
        status = await self.manager.status()
        return bool(status["running"])

    async def list_models(self) -> List[Dict[str, Any]]:
        return self.manager.catalog()

    async def stream_chat(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.2,
        max_tokens: int = 4096,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        base_url = await self.manager.ensure_running(model_id)
        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        timeout = httpx.Timeout(900.0, connect=10.0, read=900.0)
        tool_calls: Dict[int, Dict[str, str]] = {}
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", f"{base_url}/chat/completions",
                headers={"Authorization": "Bearer runtimeforce-local"},
                json=payload,
            ) as response:
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
                    content = delta.get("content")
                    if content:
                        yield {"status": "streaming", "content": content}
                    for call in delta.get("tool_calls") or []:
                        index = int(call.get("index", 0))
                        item = tool_calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                        if call.get("id"):
                            item["id"] = call["id"]
                        function = call.get("function") or {}
                        item["name"] += function.get("name") or ""
                        item["arguments"] += function.get("arguments") or ""
                    if choice.get("finish_reason") == "tool_calls" and tool_calls:
                        calls = []
                        for index in sorted(tool_calls):
                            item = tool_calls[index]
                            if item["name"]:
                                calls.append({
                                    "id": item["id"] or f"bitnet_call_{index}",
                                    "name": item["name"],
                                    "arguments": item["arguments"] or "{}",
                                })
                        if calls:
                            yield {"status": "tool_calls", "calls": calls}
