import json
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional

from app.core.llm.orchestrator import orchestrator
from app.tools.router import ToolRouter, AGENT_TOOLS_MANIFEST
from app.memory.store import store

logger = logging.getLogger("ai_runtime.stream")


class AgentLoopCoordinator:

    @staticmethod
    def _reconstruct_tool_calls(acc: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
        calls = []
        for idx, tc in sorted(acc.items()):
            if not tc.get("name"):
                continue
            calls.append({
                "id": tc.get("id", f"call_{idx}"),
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": tc["arguments"],
                },
            })
        return calls

    @classmethod
    async def run_agent_loop(
        cls,
        session_id: str,
        messages: List[Dict[str, str]],
        strategy: str = "auto",
        model_lock: Optional[str] = None,
        temperature: float = 0.2,
        max_iterations: int = 8,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        history = list(messages)
        iteration = 0

        if messages and messages[-1]["role"] == "user":
            store.append_message(session_id, "user", messages[-1]["content"])

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Agent Loop {iteration}/{max_iterations}")

            text_buf = ""
            tc_acc: Dict[int, Dict[str, Any]] = {}
            cur_model = "auto"
            cur_provider = ""

            async for chunk in orchestrator.stream_completion(
                messages=history,
                strategy=strategy,
                model_lock=model_lock,
                temperature=temperature,
                tools=AGENT_TOOLS_MANIFEST,
            ):
                status = chunk.get("status")
                if status in ("fallback", "failed"):
                    yield chunk
                    if status == "failed":
                        return
                    continue

                cur_model = chunk.get("model", cur_model)
                cur_provider = chunk.get("provider", cur_provider)

                if chunk.get("content"):
                    text_buf += chunk["content"]
                    yield {
                        "status": "streaming",
                        "model": cur_model,
                        "provider": cur_provider,
                        "content": chunk["content"],
                    }

                if chunk.get("tool_calls"):
                    for tc in chunk["tool_calls"]:
                        idx = getattr(tc, "index", 0) or 0
                        if idx not in tc_acc:
                            tc_acc[idx] = {"id": "", "name": "", "arguments": ""}
                        if getattr(tc, "id", None):
                            tc_acc[idx]["id"] = tc.id
                        fn = getattr(tc, "function", None)
                        if fn:
                            if getattr(fn, "name", None):
                                tc_acc[idx]["name"] = fn.name
                            if getattr(fn, "arguments", None):
                                tc_acc[idx]["arguments"] += fn.arguments

            fmt_tc = cls._reconstruct_tool_calls(tc_acc)

            if not fmt_tc:
                logger.info("No tool calls. Finishing agent loop.")
                if text_buf:
                    store.append_message(session_id, "assistant", text_buf)
                break

            history.append({
                "role": "assistant",
                "content": text_buf if text_buf else None,
                "tool_calls": fmt_tc,
            })
            names = ", ".join(t["function"]["name"] for t in fmt_tc)
            store.append_message(session_id, "assistant", f"[Tools: {names}]")

            for tc in fmt_tc:
                tn = tc["function"]["name"]
                ta = tc["function"]["arguments"]
                tid = tc["id"]

                yield {
                    "status": "tool_start",
                    "model": cur_model,
                    "tool_name": tn,
                    "arguments": ta,
                    "tool_id": tid,
                }

                try:
                    result = await ToolRouter.dispatch(tn, ta)
                    rs = json.dumps(result, ensure_ascii=False)
                except Exception as ex:
                    logger.error(f"Tool dispatch error: {ex}")
                    result = {"error": str(ex)}
                    rs = json.dumps(result)

                yield {
                    "status": "tool_end",
                    "model": cur_model,
                    "tool_name": tn,
                    "result": result,
                    "tool_id": tid,
                }

                history.append({
                    "role": "tool",
                    "tool_call_id": tid,
                    "name": tn,
                    "content": rs,
                })
                store.append_message(
                    session_id, "system", f"Tool: {tn}. {rs[:2000]}"
                )

        if iteration >= max_iterations:
            msg = "\n\n⚠️ Max iterations reached."
            store.append_message(session_id, "assistant", msg)
            yield {"status": "streaming", "content": msg}