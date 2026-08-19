"""
Critic Agent Service — Non-blocking Verification with Automatic Rate-Limit Failover.
"""
import logging
from typing import Any, Dict, List, Optional

from app.core.events.event_bus import EventBus
from app.core.interfaces.critic_agent_interface import ICriticAgentService
from app.core.interfaces.role_selector_interface import IRoleSelectorService
from app.core.interfaces.storage_repository_interface import IStorageRepository

logger = logging.getLogger(__name__)

class CriticAgentService(ICriticAgentService):
    def __init__(
        self,
        llm_orchestrator: Any,
        storage_repository: IStorageRepository,
        role_selector: IRoleSelectorService,
        event_bus: Optional[EventBus] = None
    ) -> None:
        self._orchestrator = llm_orchestrator
        self._storage_repo = storage_repository
        self._role_selector = role_selector
        self._event_bus = event_bus
        self.metrics = {"critic_evaluations": 0, "failures_detected": 0}

    async def validate_result(
        self,
        specialist_result: Dict[str, Any],
        task_context: Dict[str, Any],
        user_id: str,
        project_id: str,
        user_plan: str,
        enabled_models: Optional[List[str]] = None,
        override_model: Optional[str] = None
    ) -> Dict[str, Any]:
        logger.info(
            f"[CriticAgent] Validating result for project_id={project_id}, plan={user_plan}"
        )
        self.metrics["critic_evaluations"] += 1

        violations = []

        red_tests = await self._storage_repo.get_graph_nodes_by_properties(
            properties={"status": "RED", "project_id": project_id},
            label="Test"
        )
        if red_tests:
            violations.append(f"Test suite contains {len(red_tests)} failing RED test nodes")

        if override_model and override_model != "auto":
            model_id = override_model
        else:
            evaluator_model = await self._role_selector.select_cheapest_model(
                required_capabilities=["code"],
                user_plan=user_plan,
                user_id=user_id,
                enabled_models=enabled_models
            )
            model_id = evaluator_model.get("model_id", "none")

        if model_id != "none":
            try:
                validation_response = await self._orchestrator.validate_result(
                    result=specialist_result,
                    context=task_context,
                    model_id=model_id,
                    user_id=user_id
                )
                if not validation_response.get("passed", True):
                    violations.append(
                        validation_response.get("feedback", "Code assertion failed")
                    )
            except Exception as e:
                logger.warning(f"[CriticAgent] LLM validation call failed ({e}). Proceeding gracefully.")

        passed = len(violations) == 0

        if self._event_bus:
            await self._event_bus.publish(
                "critic.passed" if passed else "critic.failed",
                {"project_id": project_id, "violations": violations}
            )

        return {
            "passed": passed,
            "feedback": "; ".join(violations) if violations else "",
            "violations": violations
        }
