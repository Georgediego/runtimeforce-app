"""
Service for local subscription status caching.
"""
import logging
from typing import Dict, Any, Optional
from app.repository.subscription_db_repository import SubscriptionDBRepository

logger = logging.getLogger("runtimeforce.service.billing.subscription_cache")

class SubscriptionCacheService:
    def __init__(self, repo: SubscriptionDBRepository):
        self.repo = repo

    def cache_user_plan(self, user_id: str, plan: str, valid_until: Optional[str] = None) -> bool:
        return self.repo.save_subscription(user_id, plan, valid_until)

    def get_cached_plan(self, user_id: str) -> str:
        sub = self.repo.get_by_id("", user_id)
        return sub.get("plan", "free") if sub else "free"
