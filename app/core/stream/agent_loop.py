import json
import logging
import time
import copy
import asyncio
import re
import uuid
from typing import AsyncGenerator, List, Dict, Any, Optional
from app.core.llm.orchestrator import orchestrator
from app.tools.router import ToolRouter, AGENT_TOOLS_MANIFEST
from app.memory.store import store

logger = logging.getLogger("ai_runtime.stream")


class IntentClassifier:
    """Классификатор намерений пользователя."""

    SHELL_COMMANDS = [
        "pwd", "ls", "cd", "cat", "grep", "find", "mkdir", "rm", "cp", "mv",
        "git", "npm", "yarn", "pip", "python", "node", "bash", "sh",
        "docker", "kubectl", "ssh", "scp", "curl", "wget"
    ]

    ACTION_KEYWORDS = {
        "ru": [
            "сделай", "создай", "напиши", "исправь", "выполни", "запусти", "удали", "измени",
            "покажи", "прочитай", "открой", "найди", "поищи", "просканируй", "проверь",
            "какая папка", "где находится", "что в папке", "какой путь", "текущая директория",
            "инициализируй", "установи", "деплой", "настрой", "собери"
        ],
        "en": [
            "make", "create", "write", "fix", "run", "execute", "delete", "modify",
            "show", "read", "open", "find", "search", "scan", "check",
            "what folder", "where is", "what's in", "current directory", "working directory",
            "init", "install", "deploy", "setup", "build"
        ]
    }

    CONVERSATIONAL_KEYWORDS = {
        "ru": ["привет", "здравствуй", "хай", "как дела", "кто ты", "что ты", "спасибо", "пока", "ok", "ок", "да", "нет"],
        "en": ["hello", "hi", "hey", "how are you", "who are you", "thanks", "bye", "ok", "yes", "no"]
    }

    @classmethod
    def classify(cls, text: str, history: List[Dict[str, Any]] = None) -> str:
        """
        Классифицирует намерение.
        ВАЖНО: если history содержит недавние tool calls, а текущий запрос - приветствие,
        возвращаем "conversational" чтобы не продолжать паттерн вызова инструментов.
        """
        if not text or not text.strip():
            return "conversational"

        text_lower = text.lower().strip()

        # 1. Проверяем на чистое приветствие (самый высокий приоритет)
        for lang in ["ru", "en"]:
            for greeting in cls.CONVERSATIONAL_KEYWORDS[lang]:
                if text_lower == greeting or text_lower == greeting + "!":
                    return "conversational"
                if text_lower.startswith(greeting + " ") and len(text_lower.split()) <= 3:
                    return "conversational"

        # 2. Короткие подтверждения (да, нет, ок) — всегда conversational
        if text_lower in ["да", "нет", "ок", "ok", "yes", "no", "давай", "погнали", "continue", "продолжай"]:
            return "conversational"

        # 3. Проверяем на явные команды терминала
        for cmd in cls.SHELL_COMMANDS:
            if cmd in text_lower and len(text_lower) < 100:
                return "action"

        # 4. Проверяем на явные триггеры действий
        for lang in ["ru", "en"]:
            for action in cls.ACTION_KEYWORDS[lang]:
                if action in text_lower:
                    return "action"

        # 5. Вопросы о файловой системе, путях, директориях
        fs_keywords = ["папк", "директори", "файл", "путь", "folder", "directory", "file", "path"]
        if any(kw in text_lower for kw in fs_keywords):
            return "action"

        # 6. Если в истории есть недавние tool calls, а запрос короткий — conversational
        # (чтобы модель не продолжала вызывать инструменты на "Да" или "Привет")
        if history:
            recent_tool_calls = sum(1 for m in history[-6:] if m.get("role") == "tool")
            if recent_tool_calls > 0 and len(text) < 50:
                return "conversational"

        # 7. Короткие сообщения без явных триггеров — разговор
        if len(text) < 30:
            return "conversational"

        # 8. По умолчанию — действие
        return "action"


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

    @staticmethod
    def _clean_string_error(err_msg: str, plan: str = "free", model_name: str = "модели") -> str:
        if not err_msg or not isinstance(err_msg, str):
            return err_msg
        err_lower = err_msg.lower()
        if "429" in err_lower or "quota" in err_lower:
            return f"⚠️ Rate Limit для {model_name}."
        if "503" in err_lower or "502" in err_lower:
            return f"⚠️ Провайдер {model_name} перегружен."
        if "repetition" in err_lower:
            return f"⚠️ Модель {model_name} зациклилась. Переключаюсь на другую."
        return err_msg

    @classmethod
    def _prepare_optimized_history(cls, history: List[Dict[str, Any]], strategy: str, plan: str) -> List[Dict[str, Any]]:
        """
        Оптимизация истории с СОХРАНЕНИЕМ последнего сообщения пользователя.
        """
        if len(history) <= 6:
            return history

        optimized = []
        system_msg = next((m for m in history if m.get("role") == "system"), None)
        first_user_msg = next((m for m in history if m.get("role") == "user"), None)
        
        # ВАЖНО: сохраняем ПОСЛЕДНЕЕ сообщение пользователя (даже при обрезке)
        last_user_msg = next((m for m in reversed(history) if m.get("role") == "user"), None)

        if system_msg:
            optimized.append(copy.deepcopy(system_msg))
        if first_user_msg and first_user_msg != system_msg and first_user_msg != last_user_msg:
            optimized.append(copy.deepcopy(first_user_msg))

        tail_messages = []
        steps_counted = 0
        core_elements = [system_msg, first_user_msg]

        for msg in reversed(history):
            if msg in core_elements:
                continue
            msg_copy = copy.deepcopy(msg)
            if msg_copy.get("role") == "tool" and "content" in msg_copy:
                content_str = str(msg_copy["content"])
                if len(content_str) > 4000:
                    msg_copy["content"] = f"{content_str[:1000]}\n🔄 [... Truncated ...]\n{content_str[-2000:]}"
            tail_messages.insert(0, msg_copy)
            if msg_copy.get("role") in ("tool", "assistant"):
                steps_counted += 1
            if steps_counted >= 12:
                break

        # Убеждаемся, что последнее сообщение пользователя сохранено
        if last_user_msg and last_user_msg not in tail_messages and last_user_msg not in core_elements:
            tail_messages.append(copy.deepcopy(last_user_msg))

        optimized.extend(tail_messages)
        return optimized

    @classmethod
    async def run_agent_loop(
        cls,
        session_id: str,
        messages: List[Dict[str, str]],
        strategy: str = "coding",
        model_lock: Optional[str] = None,
        temperature: float = 0.2,
        max_iterations: int = 15,
        consilium_draft_model: Optional[str] = None,
        consilium_critic_model: Optional[str] = None,
        consilium_synth_model: Optional[str] = None,
        plan: str = "free",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        history = list(messages)
        iteration = 0
        tool_call_counts = {}
        modified_since_last_test = False

        logger.info(f"🎯 Agent loop started: strategy={strategy}, model_lock={model_lock}, plan={plan}")

        if messages and messages[-1]["role"] == "user":
            store.append_message(session_id, "user", messages[-1]["content"])

        while iteration < max_iterations:
            iteration += 1
            yield {
                "status": "iteration_start",
                "iteration": iteration,
                "max_iterations": max_iterations,
                "history_len": len(history),
                "strategy": strategy,
                "timestamp": time.time()
            }

            # Intent Classification С УЧЕТОМ ИСТОРИИ
            last_user_msg = next((m for m in reversed(history) if m.get("role") == "user"), None)
            user_text = last_user_msg.get("content", "") if last_user_msg else ""

            intent = IntentClassifier.classify(user_text, history=history)
            logger.info(f"Intent: {intent} for text: {user_text[:50]}...")

            # Передаем инструменты ТОЛЬКО если нужно действие
            tools_to_pass = AGENT_TOOLS_MANIFEST if intent == "action" else None

            text_buf = ""
            tc_acc: Dict[int, Dict[str, Any]] = {}
            cur_model = model_lock if model_lock else "auto"
            cur_provider = ""

            optimized_history = cls._prepare_optimized_history(history, strategy, plan)

            try:
                async for chunk in orchestrator.stream_completion(
                    messages=optimized_history,
                    strategy=strategy,
                    model_lock=model_lock,
                    temperature=temperature,
                    tools=tools_to_pass,
                    session_id=session_id,
                    consilium_draft_model=consilium_draft_model,
                    consilium_critic_model=consilium_critic_model,
                    consilium_synth_model=consilium_synth_model,
                    plan=plan,
                ):
                    cur_model = chunk.get("model", cur_model)
                    cur_provider = chunk.get("provider", cur_provider)
                    status = chunk.get("status")

                    if status in ("fallback", "failed", "model_try", "model_error", "model_success", "no_models"):
                        if "error" in chunk and chunk["error"]:
                            chunk["error"] = cls._clean_string_error(chunk["error"], plan, cur_model)
                        yield chunk
                        if status in ("failed", "no_models"):
                            return
                        # Если model_error — прерываем итерацию, не продолжаем обработку чанков
                        if status == "model_error":
                            break
                        continue

                    if chunk.get("content"):
                        text_buf += chunk["content"]
                        yield {
                            "status": "streaming",
                            "model": cur_model,
                            "provider": cur_provider,
                            "content": chunk["content"],
                            "strategy": strategy,
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

            except Exception as ex:
                logger.error(f"Loop Error: {ex}", exc_info=True)
                yield {
                    "status": "model_error",
                    "model": cur_model,
                    "provider": cur_provider,
                    "error": str(ex),
                    "strategy": strategy,
                }
                break

            # Если был model_error, переходим к следующей итерации (оркестратор уже переключил модель)
            if not text_buf and not tc_acc:
                continue

            fmt_tc = cls._reconstruct_tool_calls(tc_acc)

            # Regex Fallback Parser
            fallback_pattern = re.compile(r"<function\((?P<name>[a-zA-Z0-9_]+)\((?P<args>[\s\S]*?)\)\)>")
            matches = list(fallback_pattern.finditer(text_buf))
            if matches and intent == "action":
                for match in matches:
                    try:
                        parsed_args = json.loads(match.group("args").strip())
                    except:
                        parsed_args = {}
                    fmt_tc.append({
                        "id": f"call_fallback_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": match.group("name"),
                            "arguments": json.dumps(parsed_args)
                        }
                    })
                text_buf = fallback_pattern.sub(" ", text_buf).strip()

            if not fmt_tc:
                if text_buf and text_buf.strip():
                    logger.info("Text response received. Finishing.")
                    store.append_message(session_id, "assistant", text_buf)
                    break
                else:
                    logger.warning(f"Empty response on iteration {iteration}.")
                    yield {
                        "status": "streaming",
                        "content": "\n\n⚠️ Модель вернула пустой ответ.",
                        "strategy": strategy,
                    }
                    break

            # Если intent был conversational, но модель вернула tool calls — блокируем их
            if intent == "conversational" and fmt_tc:
                logger.warning(f"Blocked tool calls for conversational intent: {[tc['function']['name'] for tc in fmt_tc]}")
                # Отвечаем текстом, игнорируя tool calls
                if text_buf and text_buf.strip():
                    store.append_message(session_id, "assistant", text_buf)
                else:
                    store.append_message(session_id, "assistant", "Чем могу помочь?")
                break

            contains_execution = any(tc["function"]["name"] == "execute_command" for tc in fmt_tc)
            if contains_execution and len(fmt_tc) > 2:
                fmt_tc = fmt_tc[:2]

            loop_detected = False
            executed_commands = set()

            for tc in fmt_tc:
                tn = tc["function"]["name"]
                ta = tc["function"]["arguments"]
                call_key = f"{tn}:{ta}"

                if tn == "execute_command":
                    try:
                        cmd_str = json.loads(ta).get("command", "").strip()
                    except:
                        cmd_str = str(ta).strip()
                    if cmd_str in executed_commands:
                        continue
                    executed_commands.add(cmd_str)

                if tn in ("write_workspace_file", "apply_code_patch"):
                    modified_since_last_test = True

                tool_call_counts[call_key] = tool_call_counts.get(call_key, 0) + 1
                if tool_call_counts.get(call_key, 0) >= 4:
                    loop_detected = True
                    break

            if loop_detected:
                yield {
                    "status": "failed",
                    "error": "Loop Detected",
                    "content": "\n\n🛑 Loop Detected.",
                    "strategy": strategy,
                }
                return

            history.append({
                "role": "assistant",
                "content": text_buf if text_buf else "",
                "tool_calls": fmt_tc,
            })
            store.append_message(session_id, "assistant", f"[Tools: {', '.join(t['function']['name'] for t in fmt_tc)}]")
            executed_commands.clear()

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
                    "strategy": strategy,
                }

                try:
                    result = await ToolRouter.dispatch(tn, ta)
                    rs = json.dumps(result, ensure_ascii=False)
                except Exception as ex:
                    result = {"error": str(ex)}
                    rs = json.dumps(result)

                yield {
                    "status": "tool_end",
                    "model": cur_model,
                    "tool_name": tn,
                    "result": result,
                    "tool_id": tid,
                    "strategy": strategy,
                }

                history.append({
                    "role": "tool",
                    "tool_call_id": tid,
                    "name": tn,
                    "content": rs,
                })

        if iteration >= max_iterations:
            yield {"status": "streaming", "content": "\n\nMax iterations reached.", "strategy": strategy}