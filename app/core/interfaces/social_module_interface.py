"""
Abstract interface for Studio Plan Social & Feedback Build-in-Public module.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class ISocialModuleService(ABC):

    @abstractmethod
    async def generate_post_draft(
        self,
        project_id: str,
        changelog_entry: str,
        platform: str = "x.com"
    ) -> Dict[str, Any]:
        """Generate human-like post draft from changelog."""
        pass

    @abstractmethod
    async def approve_and_publish(self, draft_id: str, user_id: str) -> bool:
        """Publish approved draft to target platform."""
        pass

    @abstractmethod
    async def fetch_incoming_feedback(self, project_id: str) -> List[Dict[str, Any]]:
        """Fetch and filter public feedback into actionable project tasks."""
        pass
