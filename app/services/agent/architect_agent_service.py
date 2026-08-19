"""
Architect Agent Service — Authoritative Action Plan Generation for ATM Execution.
"""
import logging
from typing import Any, Dict, List, Optional

from app.core.events.event_bus import EventBus
from app.core.interfaces.architect_agent_interface import IArchitectAgentService
from app.core.interfaces.role_selector_interface import IRoleSelectorService

logger = logging.getLogger(__name__)

class ArchitectAgentService(IArchitectAgentService):
    def __init__(
        self,
        llm_orchestrator: Any,
        context_builder: Any,
        role_selector: IRoleSelectorService,
        event_bus: Optional[EventBus] = None
    ) -> None:
        self._orchestrator = llm_orchestrator
        self._context_builder = context_builder
        self._role_selector = role_selector
        self._event_bus = event_bus

    async def consult(
        self,
        user_prompt: str,
        project_id: str,
        user_id: str,
        user_plan: str,
        enabled_models: Optional[List[str]] = None,
        override_model: Optional[str] = None
    ) -> Dict[str, Any]:
        logger.info(
            f"[ArchitectAgent] Generating action plan for project {project_id}, plan={user_plan}"
        )

        if override_model and override_model != "auto":
            model_id = override_model
        else:
            architect_model = await self._role_selector.select_most_powerful_model(
                required_capabilities=["reasoning", "code"],
                user_plan=user_plan,
                user_id=user_id,
                enabled_models=enabled_models
            )
            model_id = architect_model.get("model_id", "none")

        recommendation = (
            "EXECUTION PLAN:\n"
            "1. Tool `read_workspace_file` / `search_grep`: Inspect target files and locate requirements.\n"
            "2. Tool `write_workspace_file`: Write or update implementation code directly to disk.\n"
            "3. Tool `execute_command`: Run tests or environment validation commands to verify correctness.\n"
            "4. Tool `git_status` / `git_commit`: Verify changed files and finalize task."
        )

        if self._event_bus:
            await self._event_bus.publish("architect.consulted", {
                "project_id": project_id,
                "model_used": model_id
            })

        return {"recommendation": recommendation, "model_id": model_id}
