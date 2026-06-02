import json
import logging
import time
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

        # Внедряем строгие системные инструкции для ИИ-ассистента
        system_instruction = (
            "You are RuntimeForce AI, an advanced developer assistant with access to local and SSH workspace tools.\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. Only invoke tools (e.g., execute_command, read_workspace_file, git_status) when strictly "
            "necessary to fulfill a specific technical task requested by the user.\n"
            "2. DO NOT call any tools for simple greetings, introductions, or generic conversational queries "
            "(e.g., 'hello', 'who are you', 'what model are you'). Respond directly with text."
        )

        # Инжектируем промпт в начало диалога
        if not any(m.get("role") == "system" and "RuntimeForce AI" in m.get("content", "") for m in history):
            history.insert(0, {"role": "system", "content": system_instruction})

        if messages and messages[-1]["role"] == "user":
            store.append_message(session_id, "user", messages[-1]["content"])

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Agent Loop {iteration}/{max_iterations}")

            yield {
                "status": "iteration_start",
                "iteration": iteration,
                "max_iterations": max_iterations,
                "history_len": len(history),
                "timestamp": time.time()
            }

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
                session_id=session_id,
            ):
                status = chunk.get("status")
                if status in ("fallback", "failed", "model_try", "model_error", "model_success", "no_models"):
                    yield chunk
                    if status in ("failed", "no_models"):
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
                "content": text_buf if text_buf else "",
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
            msg = "\n\nMax iterations reached."
            store.append_message(session_id, "assistant", msg)
            yield {"status": "streaming", "content": msg}
