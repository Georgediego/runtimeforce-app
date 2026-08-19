import logging
from typing import Any, Dict, List, Optional

from app.core.events.event_bus import EventBus
from app.core.interfaces.role_router_interface import IRoleRouterService
from app.core.interfaces.role_selector_interface import IRoleSelectorService

logger = logging.getLogger(__name__)


class RoleRouterService(IRoleRouterService):
    def __init__(
        self,
        llm_orchestrator: Any,
        role_selector: IRoleSelectorService,
        event_bus: Optional[EventBus] = None
    ) -> None:
        self._orchestrator = llm_orchestrator
        self._role_selector = role_selector
        self._event_bus = event_bus
        self.metrics = {"tasks_classified": 0}

    async def classify_and_route(
        self,
        user_prompt: str,
        project_id: str,
        user_id: str,
        user_plan: str,
        mode: str = "AUTO",
        enabled_models: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        mode_upper = (mode or "AUTO").upper()
        lower_prompt = user_prompt.lower()

        if any(k in lower_prompt for k in ["bug", "error", "fix", "crash", "broken"]):
            classification = {
                "task_type": "debug",
                "complexity": 7,
                "role": "debug",
                "needs_architect": False,
                "needs_critic": True,
                "suggested_capabilities": ["reasoning", "code"]
            }
        elif any(k in lower_prompt for k in ["architecture", "refactor", "design", "adr", "audit"]):
            classification = {
                "task_type": "architecture",
                "complexity": 9,
                "role": "architecture",
                "needs_architect": True,
                "needs_critic": True,
                "suggested_capabilities": ["reasoning", "heavy"]
            }
        elif mode_upper in ("CODING", "ATM"):
            classification = {
                "task_type": "atm_orchestration",
                "complexity": 8,
                "role": "architect_specialist_team",
                "needs_architect": True,
                "needs_critic": True,
                "suggested_capabilities": ["code", "reasoning"]
            }
        else:
            classification = {
                "task_type": "coding",
                "complexity": 5,
                "role": "coding",
                "needs_architect": False,
                "needs_critic": True,
                "suggested_capabilities": ["code"]
            }

        self.metrics["tasks_classified"] += 1

        if self._event_bus:
            await self._event_bus.publish("role.selected", {
                "project_id": project_id,
                "role": classification.get("role", "coding"),
                "task_type": classification.get("task_type")
            })

        return classification
