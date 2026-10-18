"""
Role Router Service — Classifies user prompts and routes tasks to appropriate agent roles and models.
"""
import logging
from typing import Any, Dict, List, Optional

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
        
        # Determine role based on keywords or mode
        role = "coding"
        capabilities = ["code", "text"]

        if any(kw in prompt_lower for kw in ["design", "ui", "css", "tailwind", "layout", "ux", "visual"]):
            role = "designer"
            capabilities = ["code", "design", "ui"]
        elif any(kw in prompt_lower for kw in ["test", "verify", "debug", "audit", "check"]):
            role = "tester"
            capabilities = ["code", "testing", "reasoning"]
        elif any(kw in prompt_lower for kw in ["architect", "plan", "design system", "structure"]):
            role = "architect"
            capabilities = ["architecture", "reasoning"]

        logger.info(f"[RoleRouter] Classified prompt into role='{role}', mode='{mode}'")
        return {
            "role": role,
            "suggested_capabilities": capabilities,
            "task_type": "coding"
        }
