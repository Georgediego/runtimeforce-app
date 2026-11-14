"""
WebSocket Router for Real-Time Agent Stream Orchestration with Strict Whitelist & Safe Disconnects.
"""
import json
import logging
import asyncio
from typing import Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.container import container
from app.core.security.jwt_auth_service import JWTAuthService, AuthVerificationUnavailable
from app.core.security.entitlements import chat_strategy_feature, feature_enabled

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
    try:
        user = await JWTAuthService.verify_token(token)
    except AuthVerificationUnavailable:
        logger.warning("[WS] AUTH UNAVAILABLE session=%s reason=control_plane_error", session_id)
        await websocket.close(code=1013, reason="Authentication service temporarily unavailable")
        return
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

            prompt = data.get("prompt") or data.get("text") or ""
            if not prompt and not data.get("messages"):
                logger.debug("[WS] IGNORE empty send session=%s", session_id)
                continue
            strategy = str(data.get("strategy") or "auto").strip().lower()
            entitlements = await container.license_service.get_entitlements(token)
            if not entitlements.get("valid"):
                await websocket.send_json({
                    "status": "error",
                    "code": "entitlements_unavailable",
                    "error": "Your plan could not be verified. Please reconnect and try again.",
                })
                continue
            plan = str(entitlements.get("plan") or "free")
            feature_key = chat_strategy_feature(strategy)
            if not feature_key:
                await websocket.send_json({
                    "status": "error",
                    "code": "unsupported_strategy",
                    "error": "The selected chat mode is not supported.",
                })
                continue
            if not feature_enabled(entitlements, feature_key):
                await websocket.send_json({
                    "status": "error",
                    "code": "feature_not_enabled",
                    "feature": feature_key,
                    "error": f"The {strategy.upper()} mode is not included in your current plan.",
                })
                continue

            logger.info(
                "[WS] GENERATION REQUEST session=%s user=%s action=%s strategy=%s prompt_chars=%s",
                session_id, user_id, action, strategy, len(str(prompt))
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

            active_workspace = container.workspace_repo.get_workspace_by_project_id(project_id, user_id)
            active_project = container.project_repo.get_project(project_id, user_id)
            uses_ssh = bool(
                (active_workspace and str(active_workspace.get("type") or "").lower() == "ssh")
                or (not active_workspace and active_project and (active_project.get("ssh_host") or "").strip())
            )
            if uses_ssh:
                if (entitlements.get("features") or {}).get("ssh") is not True:
                    await websocket.send_json({
                        "status": "error",
                        "code": "feature_not_enabled",
                        "feature": "ssh",
                        "error": "SSH workspaces are not included in your current plan.",
                    })
                    continue

            driver = await container.workspace_manager_service.get_driver_for_project(user_id, project_id)
            if not driver:
                await websocket.send_json({
                    "status": "error",
                    "error": "No Workspace is connected to this project. Connect a local folder or SSH Workspace in Project Settings before running AI tasks."
                })
                continue

            model_lock = data.get("model_lock")
            enabled_models = data.get("enabled_models")
            logger.info(
                "[WS] ROUTE session=%s project=%s strategy=%s model_lock=%s enabled_model_count=%s",
                session_id, project_id, strategy, model_lock or "auto",
                len(enabled_models) if isinstance(enabled_models, list) else "server-selected"
            )

            # If frontend omitted enabled_models, strictly pull from SQLite
            if enabled_models is None:
                selected_map = container.provider_keys_repo.get_all_selected_models(user_id)
                if selected_map:
                    enabled_models = []
                    for mlist in selected_map.values():
                        enabled_models.extend(mlist)

            atm_architect = data.get("atm_architect_model")
            atm_engineer = data.get("atm_engineer_model")
            atm_tester = data.get("atm_tester_model")
            atm_critic = data.get("atm_critic_model")
            atm_designer = data.get("atm_designer_model")

            messages = [{"role": "user", "content": prompt}]

            if not container.llm_registry.get_available_models():
                try:
                    decrypted_keys = container.byok_key_service.get_decrypted_keys(user_id, token)
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
                    features=entitlements.get("features") or {},
                    user_id=user_id,
                    enabled_models=enabled_models,
                    project_id=project_id,
                    atm_architect_model=atm_architect,
                    atm_engineer_model=atm_engineer,
                    atm_tester_model=atm_tester,
                    atm_critic_model=atm_critic,
                    atm_designer_model=atm_designer,
                    existing_message_id=existing_message_id,
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
