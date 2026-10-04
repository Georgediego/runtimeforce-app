"""
Service for Studio Plan Build-in-Public post generation from changelogs.
"""
import uuid
import logging
from typing import Dict, Any, List
from app.core.interfaces.social_module_interface import ISocialModuleService
from app.repository.social_feed_db_repository import SocialFeedDBRepository
from app.core.events.event_bus import EventBus

logger = logging.getLogger("runtimeforce.service.social")

class SocialPostGeneratorService(ISocialModuleService):
    def __init__(self, social_repo: SocialFeedDBRepository, event_bus: EventBus):
        self.repo = social_repo
        self.event_bus = event_bus

    async def generate_post_draft(
        self,
        project_id: str,
        changelog_entry: str,
        platform: str = "x.com"
    ) -> Dict[str, Any]:
        draft_id = f"draft-{uuid.uuid4().hex[:8]}"
        user_id = "studio_user"
        content = f"🚀 Just shipped updates for project!\n\nKey changes:\n{changelog_entry}\n\nBuilt with #RuntimeForce AI IDE."
        self.repo.save_draft(draft_id, project_id, user_id, changelog_entry, content, platform)
        
        try:
            await self.event_bus.publish("social.post_drafted", draft_id=draft_id, project_id=project_id, user_id=user_id)
        except Exception as e:
            logger.error(f"Failed to publish post_drafted event: {e}")

        return {"draft_id": draft_id, "project_id": project_id, "content": content, "platform": platform}

    async def approve_and_publish(self, draft_id: str, user_id: str) -> bool:
        return self.repo.update_draft_status(draft_id, user_id, "published")

    async def fetch_incoming_feedback(self, project_id: str) -> List[Dict[str, Any]]:
        return self.repo.get_feedback_items(project_id, "studio_user")
