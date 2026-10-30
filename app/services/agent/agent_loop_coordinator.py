"""
Agent Loop Coordinator — Strict Factual Grounding, Anti-Hallucination & Autonomous Tool Execution.
"""
import json
import time
import asyncio
import logging
import re
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.core.events.event_bus import EventBus
from app.services.agent.architect_agent_service import ArchitectAgentService
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver
from app.services.agent.agent_loop_detector import AgentLoopDetector
from app.services.agent.agent_regex_fallback import AgentRegexFallbackParser
from app.services.llm.llm_router_service import LLMRouterService
from app.tools.tool_registry_manifest import AGENT_TOOLS_MANIFEST
from app.tools.tool_dispatcher_service import ToolDispatcherService

logger = logging.getLogger("runtimeforce.service.agent.coordinator")

MAX_AGENT_ITERATIONS = 25
NO_LOCK_SENTINELS = (None, "", "auto")

# Master Directive enforcing 100% empirical verification and zero flattery
RUNTIMEFORCE_ATM_SYSTEM_DIRECTIVE = """
You are the principal autonomous Software Engineering Agent in RuntimeForce AI Runtime Environment.
You have direct, real filesystem and terminal execution capabilities.

CRITICAL INVARIANTS:
1. STRICT FACTUAL GROUNDING (ZERO TOLERANCE FOR HALLUCINATIONS OR GUESSING):
   - NEVER assert that a file, directory, function, import, or architectural flaw exists or is missing WITHOUT FIRST verifying it using tools (`scan_workspace`, `read_workspace_file`, `search_grep`).
   - If asked to audit, review, or analyze code, your VERY FIRST ACTION must be tool inspection. You are strictly forbidden from outputting speculative audit points before reading the actual files.

2. ZERO FLATTERY & OBJECTIVE RIGOR:
   - Speak with absolute technical honesty. Never agree with assumptions or hallucinate non-existent issues to please the user. If something is already implemented correctly, state it clearly.
   - If requested to create a project or business concept, conduct market research with realistic trade-offs, constraints, and verifiable facts. No generic hype.

3. SURGICAL DISK EXECUTION (NO PASSIVE TEXT OR BLIND BOILERPLATE):
   - Never output raw code blocks in chat asking the user to manually copy/paste. You must invoke `write_workspace_file` or `apply_code_patch` to write files to disk directly.
   - Read files before modifying them to preserve working logic.

4. COMPLETE PIPELINE:
   - Inspect files -> Implement changes -> Run terminal commands/tests -> Verify exit codes -> Finalize.
"""

REFUSAL_PATTERNS = [
    r"не могу напрямую",
    r"не могу изменять",
    r"предоставить архитектурные рекомендации",
    r"вы сможете применить",
    r"i cannot directly",
    r"i don't have access to your local",
    r"i cannot run commands",
    r"as an ai language model",
    r"as an ai,",
    r"i am unable to modify",
    r"вам нужно создать",
    r"вы можете создать",
]

from app.services.agent.role_router_service import RoleRouterService

class AgentLoopCoordinator:
    def __init__(
        self,
        orchestrator_service: Any,
        architect_agent: Optional[ArchitectAgentService] = None,
        storage_repository: Optional[Any] = None,
        conversation_repo: Optional[Any] = None,
        context_builder: Optional[Any] = None,
        project_service: Optional[Any] = None,
        rotation_service: Optional[Any] = None,
        event_bus: Optional[EventBus] = None,
        graph_memory: Optional[Any] = None,
        provider_keys_repo: Optional[Any] = None,
        role_router: Optional[Any] = None,
        llm_router: Optional[LLMRouterService] = None,
    ):
        self._orchestrator = orchestrator_service
        self._architect_agent = architect_agent
        self._storage_repo = storage_repository
        self._conversation_repo = conversation_repo
        self._context_builder = context_builder
        self._project_service = project_service
        self._rotation_service = rotation_service
        self._event_bus = event_bus
        self._graph_memory = graph_memory
        self._provider_keys_repo = provider_keys_repo
        self._role_router = role_router
        self._llm_router = llm_router
        self._cooldown_models: Dict[str, float] = {}

    def _resolve_strict_whitelist(self, enabled_models: Optional[List[str]], user_id: str) -> Optional[List[str]]:
        db_allowed = []
        has_global_models = False
        if self._provider_keys_repo:
            try:
                conn = self._provider_keys_repo.db.get_connection()
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) as cnt FROM provider_selected_models")
                row = cur.fetchone()
                if row and row["cnt"] > 0:
                    has_global_models = True
            except Exception:
                pass

            selected_map = self._provider_keys_repo.get_all_selected_models(user_id)
            if selected_map:
                for mlist in selected_map.values():
                    if isinstance(mlist, list):
                        db_allowed.extend(mlist)
        db_set = set(db_allowed)

        if enabled_models is not None:
            if db_set:
                return [m for m in enabled_models if m in db_set and LLMRouterService.is_text_model(m)]
            return [m for m in enabled_models if LLMRouterService.is_text_model(m)]

        if db_allowed:
            return [m for m in db_allowed if LLMRouterService.is_text_model(m)]

        if has_global_models:
            return []

        return None

    @staticmethod
    def _contains_conversational_refusal(text: str) -> bool:
        t_lower = text.lower()
        return any(re.search(pat, t_lower) for pat in REFUSAL_PATTERNS)

    async def run_agent_loop(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        driver: IWorkspaceDriver,
        strategy: str = "auto",
        model_lock: Optional[str] = None,
        temperature: float = 0.2,
        plan: str = "free",
        user_id: str = "default_user",
        managed_ai_token: Optional[str] = None,
        enabled_models: Optional[List[str]] = None,
        project_id: str = "default_project",
        atm_architect_model: Optional[str] = None,
        atm_engineer_model: Optional[str] = None,
        atm_tester_model: Optional[str] = None,
        atm_critic_model: Optional[str] = None,
        atm_designer_model: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        user_prompt = messages[-1].get("content", "") if messages else ""
        strategy_upper = (strategy or "AUTO").upper()

        loop_detector = AgentLoopDetector(max_empty_responses=2, max_repeated_tools=3, max_iterations=25)

        strict_enabled = self._resolve_strict_whitelist(enabled_models, user_id)
        managed_ai_enabled = bool(
            managed_ai_token
            and plan.lower() in {"pro", "studio", "expert", "enterprise"}
        )

        db_allowed_all = []
        if self._provider_keys_repo:
            selected_map = self._provider_keys_repo.get_all_selected_models(user_id)
            if selected_map:
                for mlist in selected_map.values():
                    if isinstance(mlist, list):
                        db_allowed_all.extend(mlist)
        db_set_all = set(db_allowed_all)

        if enabled_models is not None and db_set_all:
            for em in enabled_models:
                if em not in db_set_all:
                    yield {"status": "warning", "warning": f"Manual model ignored: {em}"}

        if model_lock and model_lock.lower() not in ("auto", "none", ""):
            if strict_enabled is not None and model_lock not in strict_enabled:
                if not managed_ai_enabled:
                    yield {"status": "warning", "warning": f"Manual model ignored: {model_lock}"}
                    model_lock = None

        for atm_val, name in [
            (atm_architect_model, "architect"),
            (atm_engineer_model, "engineer"),
            (atm_tester_model, "tester"),
            (atm_critic_model, "critic"),
            (atm_designer_model, "designer"),
        ]:
            if atm_val and atm_val.lower() not in ("auto", "none", ""):
                if strict_enabled is not None and atm_val not in strict_enabled:
                    yield {"status": "warning", "warning": f"Manual model ignored: {atm_val}"}
                    if name == "architect": atm_architect_model = None
                    elif name == "engineer": atm_engineer_model = None
                    elif name == "tester": atm_tester_model = None
                    elif name == "critic": atm_critic_model = None
                    elif name == "designer": atm_designer_model = None

        if self._conversation_repo and user_prompt:
            self._conversation_repo.append_message(
                session_id=session_id, role="user", content=user_prompt,
                user_id=user_id, project_id=project_id,
            )

        logger.info(
            f"[AgentCoordinator] Loop start session='{session_id}', "
            f"strategy='{strategy_upper}', plan='{plan}', project_id='{project_id}'"
        )

        if strict_enabled is not None and len(strict_enabled) == 0 and not managed_ai_enabled:
            err_msg = "No models enabled in settings. Please select models in Settings -> Providers."
            if self._conversation_repo:
                self._conversation_repo.append_trace(session_id, "ERROR", err_msg)
            yield {"status": "error", "error": err_msg, "retry_after": 0}
            yield {"status": "done"}
            return

        yield {"status": "phase", "label": "Retrieving Graph Memory & Project Context...", "role": "System"}
        if self._conversation_repo:
            self._conversation_repo.append_trace(session_id, "PHASE", "Retrieving context...")

        memory_context_str = ""
        if self._context_builder:
            try:
                context_res = await self._context_builder.build_optimal_context(
                    user_prompt=user_prompt, session_id=session_id,
                    user_id=user_id, project_id=project_id, max_context_tokens=8000,
                )
                memory_context_str = context_res.get("compiled_memory_context", "")
            except Exception as e:
                logger.warning(f"[AgentCoordinator] Context build failed: {e}")

        proj_context, proj_rules = "", ""
        if self._project_service:
            try:
                p = self._project_service.get_project_details(project_id, user_id)
                if not p:
                    p = self._project_service.get_active_project(user_id)
                if p:
                    proj_context = p.get("project_context", "")
                    proj_rules = p.get("rules_of_engagement", "")
            except Exception as e:
                logger.warning(f"[AgentCoordinator] Project details failed: {e}")


        yield {"status": "phase", "label": "Routing task...", "role": "Router"}
        routing = await self._role_router.classify_and_route(
            user_prompt=user_prompt, project_id=project_id,
            user_id=user_id, user_plan=plan, mode=strategy_upper,
            enabled_models=strict_enabled,
        )

        architect_guidance = ""
        if strategy_upper in ("CODING", "ATM") and self._architect_agent:
            yield {
                "status": "phase",
                "label": "ATM Planning: Architect analyzing...",
                "role": "Architect",
                "model": atm_architect_model or "auto"
            }
            arch_res = await self._architect_agent.consult(
                user_prompt=user_prompt, project_id=project_id,
                user_id=user_id, user_plan=plan, enabled_models=strict_enabled,
                override_model=atm_architect_model
            )
            architect_guidance = arch_res.get("recommendation", "")

        candidate_models: List[Dict[str, Any]] = []
        is_manual_override = model_lock not in NO_LOCK_SENTINELS or strategy_upper == "MANUAL"

        provider_keys = {}
        if self._provider_keys_repo:
            try:
                provider_keys = self._provider_keys_repo.get_all_provider_keys(user_id) or {}
            except Exception:
                pass

        if self._llm_router:
            try:
                routed_model_ids = self._llm_router.build_route(
                    strategy=strategy_upper,
                    model_lock=model_lock,
                    plan=plan,
                    provider_keys=provider_keys,
                    scores={},
                    user_prompt=user_prompt,
                    enabled_models=strict_enabled,
                    required_capability="chat_completion"
                )
                for mid in routed_model_ids:
                    prov = mid.split("/", 1)[0] if "/" in mid else "unknown"
                    candidate_models.append({"model_id": mid, "provider": prov})
            except Exception as e:
                if managed_ai_enabled:
                    logger.info("[AgentCoordinator] No local route; trying server Managed AI (%s)", type(e).__name__)
                else:
                    logger.warning(f"[AgentCoordinator] LLMRouter build_route failed: {e}")

        if managed_ai_enabled and strategy_upper != "LOCAL":
            is_managed_model_lock = bool(
                model_lock and model_lock.startswith("runtimeforce-managed/")
            )
            if is_managed_model_lock:
                managed_model_id = model_lock
            else:
                requested_server_model = model_lock if model_lock not in NO_LOCK_SENTINELS else "auto"
                managed_model_id = f"runtimeforce-managed/{requested_server_model}"
            managed_candidate = {"model_id": managed_model_id, "provider": "runtimeforce-managed"}
            local_candidates_with_keys = [
                candidate for candidate in candidate_models
                if candidate.get("provider", "").lower() in provider_keys
                or candidate.get("provider", "").lower() in ("local", "ollama", "lm_studio")
            ]
            if is_managed_model_lock:
                # An explicit Managed AI selection must stay on the server proxy.
                candidate_models = [managed_candidate]
            elif (
                strategy_upper in ("AUTO", "CODING", "ATM")
                or model_lock in NO_LOCK_SENTINELS
                or not local_candidates_with_keys
            ):
                # Paid plans prefer the server's admin-selected catalog for cloud routing.
                candidate_models = [managed_candidate] + local_candidates_with_keys
            else:
                # Preserve an explicit local Manual lock before trying the server catalog.
                candidate_models = local_candidates_with_keys + [managed_candidate]

        if strategy_upper == "LOCAL":
            candidate_models = [m for m in candidate_models if m.get("provider", "").lower() in ("ollama", "lm_studio")]

        now = time.time()
        active_candidates = []
        for m in candidate_models:
            mid = m.get("model_id", "")
            if is_manual_override:
                active_candidates.append(m)
                continue
            if mid in self._cooldown_models and now < self._cooldown_models[mid]:
                continue
            elif mid in self._cooldown_models:
                del self._cooldown_models[mid]
            if self._rotation_service and not self._rotation_service.is_model_available(mid):
                continue
            active_candidates.append(m)

        if not active_candidates and candidate_models:
            active_candidates = candidate_models

        if not active_candidates:
            err_msg = "No eligible models available. Please configure a free Groq or Gemini key in Settings -> Providers."
            if self._conversation_repo:
                self._conversation_repo.append_trace(session_id, "ERROR", err_msg)
            yield {"status": "error", "error_code": "NO_MODELS_AVAILABLE", "error": err_msg, "retry_after": 0}
            yield {"status": "done"}
            return

        db_messages = []
        if self._conversation_repo:
            db_messages = self._conversation_repo.get_session_messages(session_id)
        history_source = db_messages if db_messages else list(messages)
        trimmed_history = history_source[-6:]

        system_prompt_blocks = [RUNTIMEFORCE_ATM_SYSTEM_DIRECTIVE.strip()]
        if proj_context:
            system_prompt_blocks.append(f"### PROJECT CONTEXT:\n{proj_context}")
        if proj_rules:
            system_prompt_blocks.append(f"### RULES OF ENGAGEMENT:\n{proj_rules}")
        if memory_context_str:
            system_prompt_blocks.append(f"### KNOWLEDGE GRAPH & DECISION MEMORY:\n{memory_context_str}")
        if architect_guidance:
            system_prompt_blocks.append(f"### ATM ACTION PLAN:\n{architect_guidance}")

        combined_system_prompt = "\n\n".join(system_prompt_blocks)
        agent_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": combined_system_prompt}
        ]
        for m in trimmed_history:
            agent_messages.append({"role": m["role"], "content": m["content"]})

        final_text = ""
        active_specialist_index = 0
        force_no_tools = False

        for iteration in range(1, MAX_AGENT_ITERATIONS + 1):
            iter_limit_err = loop_detector.check_max_iterations(iteration)
            if iter_limit_err:
                err_msg = "Max execution iterations reached."
                yield {"status": "error", "error_code": iter_limit_err, "error": err_msg}
                break

            iteration_text, tool_calls = "", []
            iteration_success = False
            effective_tools = None if force_no_tools else AGENT_TOOLS_MANIFEST

            while active_specialist_index < len(active_candidates):
                specialist_model = active_candidates[active_specialist_index]
                model_id = specialist_model["model_id"]
                provider = specialist_model.get("provider", "unknown").lower()

                if not is_manual_override and model_id in self._cooldown_models:
                    if time.time() < self._cooldown_models[model_id]:
                        active_specialist_index += 1
                        continue
                    else:
                        del self._cooldown_models[model_id]

                current_step_role = "Engineer"
                if strategy_upper in ("ATM", "CODING"):
                    if any(kw in user_prompt.lower() for kw in ["design", "ui", "css", "tailwind", "layout"]):
                        current_step_role = "Designer"
                    else:
                        current_step_role = "Engineer"
                else:
                    current_step_role = "Agent"

                yield {
                    "status": "model_try",
                    "model": model_id,
                    "provider": provider,
                    "role": current_step_role,
                    "label": f"{current_step_role} processing with {model_id}..."
                }
                if self._conversation_repo:
                    self._conversation_repo.append_trace(session_id, "TRY", f"Attempting: {model_id}")

                has_chunk_error, error_details = False, ""
                is_stream_dropped = False
                partial_output_failure = False

                stream_kwargs = {
                    "messages": agent_messages,
                    "model_id": model_id,
                    "provider": provider,
                    "temperature": temperature,
                    "user_id": user_id,
                    "tools": effective_tools,
                    "strategy": strategy,
                }
                if provider == "runtimeforce-managed":
                    stream_kwargs["managed_ai_token"] = managed_ai_token

                async for chunk in self._orchestrator.stream_completion(**stream_kwargs):
                    status = chunk.get("status")
                    if status == "streaming":
                        iteration_text += chunk.get("content", "")
                        final_text += chunk.get("content", "")
                        yield chunk
                    elif status == "reasoning":
                        yield chunk
                    elif status in ("model_try", "phase"):
                        yield chunk
                    elif status == "tool_calls":
                        tool_calls = chunk.get("calls", [])
                    elif status == "error":
                        has_chunk_error = True
                        error_details = chunk.get("error", "Unknown")
                        partial_output_failure = bool(iteration_text or tool_calls)
                        if chunk.get("error_code") in ("STREAM_DROPPED", "TIMEOUT", "LOCAL_TIMEOUT", "LOCAL_UNREACHABLE"):
                            is_stream_dropped = True
                        break

                if partial_output_failure:
                    err_msg = "The selected model failed after response output began. Automatic fallback was stopped to avoid mixing answers."
                    logger.warning("[AgentCoordinator] %s (%s)", err_msg, model_id)
                    yield {"status": "error", "error_code": "PARTIAL_RESPONSE_FAILURE", "error": err_msg}
                    yield {"status": "done"}
                    return

                # Parse tool calls from markdown blocks if model emitted text
                if not tool_calls and iteration_text:
                    clean_text, parsed_tools = AgentRegexFallbackParser.parse(iteration_text)
                    if parsed_tools:
                        tool_calls = parsed_tools
                        iteration_text = clean_text

                if is_stream_dropped:
                    logger.warning(f"[AgentCoordinator] Model {model_id} failed: {error_details}. Failing over.")
                    self._cooldown_models[model_id] = time.time() + 300
                    if self._rotation_service:
                        self._rotation_service.mark_model_failed(model_id, provider, error_details or "stream_dropped")
                    iteration_text = ""
                    active_specialist_index += 1
                    continue

                empty_err = loop_detector.check_empty_response(iteration_text, tool_calls)
                if empty_err:
                    err_msg = f"Model '{model_id}' returned empty response. Switching candidate..."
                    if self._conversation_repo:
                        self._conversation_repo.append_trace(session_id, "SKIP", err_msg)
                    self._cooldown_models[model_id] = time.time() + 300
                    if self._rotation_service:
                        self._rotation_service.mark_model_failed(model_id, provider, "empty_response")
                    active_specialist_index += 1
                    continue

                if not has_chunk_error and (len(iteration_text.strip()) > 0 or len(tool_calls) > 0):
                    iteration_success = True
                    break

                self._cooldown_models[model_id] = time.time() + 300
                if self._rotation_service:
                    self._rotation_service.mark_model_failed(model_id, provider, error_details or "failed")
                active_specialist_index += 1

            if not iteration_success:
                err_msg = f"All candidate models failed: {error_details}. Please configure a free Groq or Gemini key in Settings -> Providers."
                if self._conversation_repo:
                    self._conversation_repo.append_trace(session_id, "ERROR", err_msg)
                yield {"status": "error", "error": err_msg}
                yield {"status": "done"}
                return

            # Refusal and Blind Speculation Interceptor: Force tool execution before analysis
            if strategy_upper in ("ATM", "CODING") and not tool_calls and iteration <= 2:
                has_refusal = self._contains_conversational_refusal(iteration_text)
                has_passive_code = "```" in iteration_text or "class " in iteration_text or "def " in iteration_text
                if has_refusal or has_passive_code:
                    logger.info("[AgentCoordinator] Passive response or speculation intercepted. Enforcing tool execution.")
                    agent_messages.append({"role": "assistant", "content": iteration_text})
                    agent_messages.append({
                        "role": "user",
                        "content": (
                            "EMPIRICAL VERIFICATION DIRECTIVE: Do not speculate or output code in chat. "
                            "You must inspect files using `scan_workspace`/`read_workspace_file` first, "
                            "and apply all verified changes directly using `write_workspace_file`."
                        )
                    })
                    continue

            if not tool_calls:
                break

            tool_loop_err = loop_detector.check_tool_loop(tool_calls)
            if tool_loop_err:
                agent_messages.append({
                    "role": "system",
                    "content": "SYSTEM DIRECTIVE: Repeated tool calls detected. Stop repeating tools and synthesize final output now.",
                })
                force_no_tools = True

            formatted_tool_calls = []
            for c in tool_calls:
                c_id = str(c.get("id") or f"call_{int(time.time())}")
                c_name = str(c.get("name") or "").strip()
                if not c_name:
                    continue

                args = c.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args_dict = json.loads(args)
                    except Exception:
                        args_dict = {"raw": args}
                else:
                    args_dict = args or {}

                formatted_tool_calls.append({
                    "id": c_id,
                    "type": "function",
                    "function": {
                        "name": c_name,
                        "arguments": json.dumps(args_dict, ensure_ascii=False)
                    }
                })

            if formatted_tool_calls:
                agent_messages.append({
                    "role": "assistant",
                    "content": iteration_text,
                    "tool_calls": formatted_tool_calls,
                })

            for call in tool_calls:
                tool_id = call.get("id") or f"tool-{int(time.time())}"
                tool_name = str(call.get("name") or "").strip()
                if not tool_name:
                    continue

                args_raw = call.get("arguments", {})
                arguments_json = json.dumps(args_raw, ensure_ascii=False) if isinstance(args_raw, dict) else str(args_raw)

                if self._conversation_repo:
                    self._conversation_repo.append_trace(session_id, "TOOL", f"Running: {tool_name}")
                    self._conversation_repo.save_tool_execution(session_id, tool_id, tool_name, "running")

                current_tool_role = "Tester" if strategy_upper in ("ATM", "CODING") else "Agent"
                yield {
                    "status": "tool_start",
                    "tool_id": tool_id,
                    "tool_name": tool_name,
                    "arguments": arguments_json,
                    "role": current_tool_role,
                    "label": f"Running tool {tool_name}..."
                }
                
                result = await ToolDispatcherService.dispatch(tool_name, arguments_json, driver)

                cmd_str = args_raw.get("command", "") if isinstance(args_raw, dict) else ""
                out_text = result.get("stdout") or result.get("stderr") or result.get("message") or ""
                
                if self._event_bus and out_text:
                    await self._event_bus.publish("terminal.agent_output", {
                        "session_id": session_id,
                        "command": cmd_str or tool_name,
                        "output": out_text,
                        "exit_code": result.get("exit_code", 0)
                    })

                if tool_name == "execute_command" and self._conversation_repo and cmd_str:
                    self._conversation_repo.append_terminal(session_id, "input", f"$ {cmd_str}")
                    if result.get("stdout"):
                        self._conversation_repo.append_terminal(session_id, "stdout", result["stdout"])
                    if result.get("stderr"):
                        self._conversation_repo.append_terminal(session_id, "stderr", result["stderr"])

                if self._conversation_repo:
                    self._conversation_repo.append_trace(session_id, "DONE", f"Completed: {tool_name}")
                    self._conversation_repo.save_tool_execution(
                        session_id, tool_id, tool_name,
                        "success" if result.get("exit_code", 0) == 0 else "error",
                    )

                yield {
                    "status": "tool_end",
                    "tool_id": tool_id,
                    "tool_name": tool_name,
                    "result": json.dumps(result, ensure_ascii=False)
                }

                agent_messages.append({
                    "role": "tool", "tool_call_id": tool_id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

        if self._conversation_repo and final_text.strip():
            self._conversation_repo.append_message(
                session_id=session_id, role="assistant", content=final_text,
                user_id=user_id, project_id=project_id,
            )

        yield {"status": "done"}
