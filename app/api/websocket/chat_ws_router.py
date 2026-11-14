"""
WebSocket Router for Real-Time Agent Stream Orchestration with Strict Whitelist & Safe Disconnects.
"""
import json
import logging
import asyncio
from typing import Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from app.container import container
from app.core.security.jwt_auth_service import JWTAuthService
from app.core.security.entitlements import feature_enabled, model_allowed_by_plan, provider_feature, plan_limit, require_project_access, require_ssh_host_access, git_repo_quota_state

logger = logging.getLogger("runtimeforce.chat_ws")
router = APIRouter()

active_tasks: Dict[str, asyncio.Task] = {}


@router.websocket("/ws/chat/{session_id}")
async def ws_chat_endpoint(websocket: WebSocket, session_id: str):
    logger.info("[WS] CONNECT session=%s client=%s", session_id, websocket.client.host if websocket.client else "unknown")
    await websocket.accept()
    try:
        auth_message = json.loads(await websocket.receive_text())
        if not isinstance(auth_message, dict) or auth_message.get("action") != "authenticate":
            await websocket.close(code=1008, reason="Authentication required")
            return
    except (WebSocketDisconnect, json.JSONDecodeError, TypeError):
        return

    token = str(auth_message.get("token") or "")
    user = await JWTAuthService.verify_token(token)
    if not user:
        logger.warning("[WS] AUTH FAILED session=%s reason=invalid_token", session_id)
        await websocket.close(code=1008, reason="Authentication required")
        return
    user_id = JWTAuthService.get_local_user_id(user)
    entitlements = await container.license_service.get_entitlements(token)
    if not entitlements.get("valid"):
        logger.warning("[WS] AUTH FAILED session=%s reason=invalid_entitlements", session_id)
        await websocket.close(code=1008, reason="Subscription status could not be verified")
        return
    plan = str(entitlements.get("plan") or "free")
    logger.info(f"WebSocket authenticated for session: {session_id}")
    
    coordinator = container.agent_loop_coordinator
    conv_repo = container.conversation_repo
    if conv_repo.get_session_owner(session_id) != user_id:
        logger.warning("[WS] AUTH FAILED session=%s reason=session_owner_mismatch user=%s", session_id, user_id)
        await websocket.close(code=1008, reason="Session access denied")
        return

    try:
        while True:
            raw_data = await websocket.receive_text()
            data = json.loads(raw_data)
            
            action = data.get("action") or data.get("type") or "send"
            
            if action in ("abort", "abort_request"):
                logger.info(f"Received abort request for session {session_id}")
                task = active_tasks.get(session_id)
                if task and not task.done():
                    task.cancel()
                    try:
                        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=2.0)
                    except asyncio.TimeoutError:
                        logger.warning("Agent cancellation did not settle within 2s for session %s", session_id)
                    finally:
                        active_tasks.pop(session_id, None)
                await websocket.send_json({"status": "aborted", "session_id": session_id})
                continue

            # Refresh verified entitlements on every new request. Long-lived WebSockets
            # must not retain privileges after an admin plan change.
            entitlements = await container.license_service.get_entitlements(token)
            if not entitlements.get("valid"):
                await websocket.send_json({
                    "status": "error", "code": 403,
                    "error": "Account entitlements could not be verified.",
                })
                await websocket.close(code=1008, reason="Subscription status could not be verified")
                return
            plan = str(entitlements.get("plan") or "free")

            prompt = data.get("prompt") or data.get("text") or ""
            if not prompt and not data.get("messages"):
                logger.debug("[WS] IGNORE empty send session=%s", session_id)
                continue

            strategy = str(data.get("strategy") or "auto").strip().lower()
            strategy_features = {
                "auto": "auto",
                "coding": "atm",
                "atm": "atm",
                "local": "local_llms",
                "manual": "manual",
            }
            required_feature = strategy_features.get(strategy)
            if not required_feature:
                await websocket.send_json({
                    "status": "error", "code": 400,
                    "error": f"Unknown orchestration mode: {strategy}",
                })
                continue
            if not feature_enabled(entitlements, required_feature):
                await websocket.send_json({
                    "status": "error", "code": 403,
                    "feature": required_feature,
                    "error": f"Feature '{required_feature}' is not enabled for plan '{plan}'.",
                })
                continue
            if plan_limit(entitlements, "max_projects") <= 0:
                await websocket.send_json({
                    "status": "error", "code": 403, "feature": "max_projects",
                    "error": "Project access is not enabled for this plan.",
                })
                continue

            logger.info(
                "[WS] GENERATION REQUEST session=%s user=%s action=%s prompt_chars=%s",
                session_id, user_id, action, len(str(prompt))
            )

            existing_message_id = data.get("existing_message_id")
            if existing_message_id is not None:
                try:
                    existing_message_id = int(existing_message_id)
                except (TypeError, ValueError):
                    await websocket.send_json({"status": "error", "error": "Invalid edited message id."})
                    continue
                existing_message = conv_repo.get_message_by_id(existing_message_id)
                if not existing_message or existing_message.get("session_id") != session_id or existing_message.get("role") != "user":
                    await websocket.send_json({"status": "error", "error": "Edited message not found in this session."})
                    continue

            project_id = conv_repo.get_session_project(session_id)
            if not project_id or project_id == "default_project":
                active_proj = container.project_repo.get_active_project(user_id)
                project_id = active_proj.get("id", "default") if active_proj else "default"

            try:
                require_project_access(user_id, project_id, entitlements)
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {}
                await websocket.send_json({
                    "status": "error", "code": 403, "feature": "max_projects",
                    "error": detail.get("message", "This project is outside the Active Projects allowance for your current plan."),
                })
                continue

            project = container.project_repo.get_project(project_id, user_id)
            workspace = container.workspace_repo.get_workspace_by_project_id(project_id, user_id)
            ssh_host = str((workspace or {}).get("host") or (project or {}).get("ssh_host") or "").strip().lower()
            if ssh_host and ssh_host not in {"localhost", "127.0.0.1"}:
                try:
                    require_ssh_host_access(user_id, ssh_host, entitlements)
                except HTTPException as exc:
                    detail = exc.detail if isinstance(exc.detail, dict) else {}
                    await websocket.send_json({
                        "status": "error", "code": 403, "feature": "max_ssh_hosts",
                        "error": detail.get("message", "This SSH host is outside the host allowance for your current plan."),
                    })
                    continue
            driver = await container.workspace_manager_service.get_driver_for_project(user_id, project_id)
            if not driver:
                await websocket.send_json({
                    "status": "error",
                    "error": "No Workspace is connected to this project. Connect a local folder or SSH Workspace in Project Settings before running AI tasks."
                })
                continue

            git_repo_slot_available = False
            if feature_enabled(entitlements, "git") and plan_limit(entitlements, "git_repos") > 0:
                git_quota = await git_repo_quota_state(
                    user_id, project_id, container.workspace_manager_service, entitlements
                )
                git_repo_slot_available = git_quota["can_use_git"]

            model_lock = data.get("model_lock")
            enabled_models = data.get("enabled_models")
            logger.info(
                "[WS] ROUTE session=%s project=%s strategy=%s model_lock=%s enabled_model_count=%s",
                session_id, project_id, strategy, model_lock or "auto",
                len(enabled_models) if isinstance(enabled_models, list) else "server-selected"
            )

            # Apply the same plan gates to every model, including AUTO routing and
            # explicitly submitted model IDs. Never trust the browser's model list.
            available_models = container.llm_registry.get_available_models()
            available_by_id = {model.id: model for model in available_models}
            if enabled_models is None:
                selected_map = container.provider_keys_repo.get_all_selected_models(user_id)
                selected_ids = []
                for model_list in (selected_map or {}).values():
                    selected_ids.extend(model_list)
                enabled_models = selected_ids or None

            allowed_model_ids = {
                model_id for model_id, model in available_by_id.items()
                if model_allowed_by_plan(entitlements, model)
            }
            explicit_model_ids = [
                model_lock,
                data.get("atm_architect_model"),
                data.get("atm_engineer_model"),
                data.get("atm_tester_model"),
                data.get("atm_critic_model"),
                data.get("atm_designer_model"),
            ]
            if enabled_models is None:
                requested_ids = sorted(allowed_model_ids)
            else:
                requested_ids = [str(model_id) for model_id in enabled_models]
            requested_ids.extend(
                str(model_id) for model_id in explicit_model_ids
                if model_id and str(model_id).lower() != "auto"
            )
            denied_ids = [
                model_id for model_id in requested_ids
                if model_id in available_by_id and model_id not in allowed_model_ids
            ]
            if denied_ids:
                denied_model = available_by_id[denied_ids[0]]
                denied_feature = provider_feature(str(getattr(denied_model, "provider", "") or ""))
                await websocket.send_json({
                    "status": "error", "code": 403,
                    "feature": denied_feature,
                    "error": f"Selected model '{denied_ids[0]}' is not available on plan '{plan}'.",
                })
                continue
            enabled_models = [model_id for model_id in requested_ids if model_id in allowed_model_ids]

            if not enabled_models:
                await websocket.send_json({
                    "status": "error", "code": 403,
                    "feature": "model_access",
                    "error": "No models are enabled by the current plan and provider selection.",
                })
                continue

            atm_architect = data.get("atm_architect_model")
            atm_engineer = data.get("atm_engineer_model")
            atm_tester = data.get("atm_tester_model")
            atm_critic = data.get("atm_critic_model")
            atm_designer = data.get("atm_designer_model")

            messages = [{"role": "user", "content": prompt}]

            if not container.llm_registry.get_available_models():
                try:
                    decrypted_keys = container.byok_key_service.get_decrypted_keys(user_id, token)
                    decrypted_keys = {
                        provider: key for provider, key in decrypted_keys.items()
                        if feature_enabled(entitlements, provider_feature(provider))
                    }
                    await container.llm_discovery.discover_all(decrypted_keys)
                except Exception as disc_err:
                    logger.warning(f"Proactive model discovery failed: {disc_err}")

            async def run_task():
                logger.info("[WS] AGENT TASK START session=%s project=%s strategy=%s", session_id, project_id, strategy)
                agent_stream = coordinator.run_agent_loop(
                    session_id=session_id,
                    messages=messages,
                    driver=driver,
                    strategy=strategy,
                    model_lock=model_lock,
                    plan=plan,
                    user_id=user_id,
                    enabled_models=enabled_models,
                    project_id=project_id,
                    atm_architect_model=atm_architect,
                    atm_engineer_model=atm_engineer,
                    atm_tester_model=atm_tester,
                    atm_critic_model=atm_critic,
                    atm_designer_model=atm_designer,
                    existing_message_id=existing_message_id,
                    plan_entitlements=entitlements,
                    git_repo_slot_available=git_repo_slot_available,
                )

                with container.command_approval_service.context(session_id=session_id, project_id=project_id):
                    async for event in agent_stream:
                        await websocket.send_json(event)

                        status = event.get("status")
                        if status in ("model_try", "error", "done", "memory_graph", "phase"):
                            logger.info(
                                "[WS] EVENT session=%s status=%s model=%s error=%s",
                                session_id, status, event.get("model", ""), str(event.get("error", ""))[:350]
                            )
                        if status in ["model_try", "tool_start", "tool_end", "error", "failed"]:
                            try:
                                if status in ["tool_start", "tool_end"]:
                                    conv_repo.save_tool_execution(
                                        session_id=session_id,
                                        tool_id=event.get("tool_id", "tool-1"),
                                        tool_name=event.get("tool_name", "unknown"),
                                        status="running" if status == "tool_start" else "success"
                                    )
                                badge = "TRY" if status == "model_try" else ("TOOL" if status == "tool_start" else "ERROR")
                                text = event.get("label") or event.get("error") or event.get("tool_name") or ""
                                conv_repo.append_trace(
                                    session_id=session_id,
                                    badge=badge,
                                    text=text
                                )
                            except Exception as db_err:
                                logger.warning(f"Failed to persist trace/tool event: {db_err}")
                logger.info("[WS] AGENT TASK FINISHED session=%s", session_id)

            task = asyncio.create_task(run_task())
            active_tasks[session_id] = task
            reader_task = asyncio.create_task(websocket.receive_text())
            try:
                # Keep reading the socket while the agent streams. Otherwise Stop cannot
                # reach this handler until the awaited agent task has already completed.
                while not task.done():
                    done, _ = await asyncio.wait(
                        {task, reader_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if task in done:
                        break
                    if reader_task in done:
                        try:
                            incoming = json.loads(reader_task.result())
                        except WebSocketDisconnect:
                            task.cancel()
                            await asyncio.gather(task, return_exceptions=True)
                            raise
                        incoming_action = incoming.get("action") or incoming.get("type") or ""
                        if incoming_action in ("abort", "abort_request"):
                            logger.info("Stop received during active generation for session %s", session_id)
                            task.cancel()
                            await asyncio.gather(task, return_exceptions=True)
                            await websocket.send_json({"status": "aborted", "session_id": session_id})
                            break
                        await websocket.send_json({
                            "status": "busy",
                            "error": "An agent task is already running. Press Stop before sending another message.",
                        })
                        reader_task = asyncio.create_task(websocket.receive_text())

                if not task.cancelled():
                    await task
            finally:
                if not reader_task.done():
                    reader_task.cancel()
                    await asyncio.gather(reader_task, return_exceptions=True)
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                active_tasks.pop(session_id, None)

    except WebSocketDisconnect:
        logger.info(f"[WS] DISCONNECTED session={session_id}")
        if session_id in active_tasks and not active_tasks[session_id].done():
            active_tasks[session_id].cancel()
            del active_tasks[session_id]
    except Exception as e:
        logger.error(f"[WS] ERROR session={session_id}: {e}", exc_info=True)
        try:
            await websocket.send_json({"status": "error", "error": str(e)})
            await websocket.close()
        except Exception:
            pass
