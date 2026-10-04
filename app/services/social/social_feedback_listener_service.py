"""
Background listener service for social feedback filtering and task extraction.
"""
import uuid
import logging
from typing import Dict, Any
from app.repository.social_feed_db_repository import SocialFeedDBRepository

logger = logging.getLogger("runtimeforce.service.social.feedback")

class SocialFeedbackListenerService:
    def __init__(self, social_repo: SocialFeedDBRepository):
        self.repo = social_repo

    def process_raw_comment(self, project_id: str, user_id: str, platform: str, raw_text: str) -> Dict[str, Any]:
        if any(bad in raw_text.lower() for bad in ["spam", "crypto", "buy now"]):
            return {"status": "filtered", "reason": "spam_detected"}
        
        feedback_id = f"fb-{uuid.uuid4().hex[:8]}"
        task = f"User feedback issue: {raw_text[:120]}"
        self.repo.save_feedback(feedback_id, project_id, user_id, platform, raw_text, task)
        return {"id": feedback_id, "status": "actionable_task_created", "task": task}
