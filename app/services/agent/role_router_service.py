"""
Role Router Service — Classifies user prompts and routes tasks to appropriate agent roles (Engineer, Implementer, Designer, Architect) supporting English and Russian.
"""
import logging
from typing import Any, Dict, List, Optional
from app.services.agent.agent_role_profiles import ROLE_PROFILES

logger = logging.getLogger("runtimeforce.service.agent.role_router")

class RoleRouterService:
    """Classifies user prompts and determines execution role and capabilities."""

    async def classify_and_route(
        self,
        user_prompt: str,
        project_id: str = "default_project",
        user_id: str = "default_user",
        user_plan: str = "free",
        mode: str = "AUTO",
        enabled_models: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        prompt_lower = (user_prompt or "").lower()
        
        role = "Engineer"
        capabilities = ["code", "text"]

        if any(kw in prompt_lower for kw in ["design", "ui", "css", "tailwind", "layout", "ux", "visual", "дизайн", "интерфейс", "стили", "кнопка"]):
            role = "Designer"
            capabilities = ["code", "design", "ui"]
        elif any(kw in prompt_lower for kw in ["implement", "write", "create", "fix", "реал", "напис", "созд", "исправ"]):
            role = "Implementer"
            capabilities = ["code", "patch", "testing"]
        elif any(kw in prompt_lower for kw in ["architect", "plan", "design system", "structure", "архитектур", "план", "структур"]):
            role = "Architect"
            capabilities = ["architecture", "reasoning"]

        logger.info(f"[RoleRouter] Classified prompt into role='{role}', mode='{mode}'")
        return {
            "role": role,
            "suggested_capabilities": capabilities,
            "task_type": "coding"
        }
