"""
Service for AI Credit balance tracking and subscription/account synchronization with last-known-good caching and offline grace.
"""
import time
import logging
import httpx
from typing import Dict, Any, Optional
from app.core.interfaces.credit_balance_service_interface import ICreditBalanceService

logger = logging.getLogger("runtimeforce.service.billing.credit")

class CreditBalanceService(ICreditBalanceService):
    def __init__(self, saas_base_url: str = "https://runtimeforce.dev"):
        self.saas_base_url = saas_base_url
        self._cache: Dict[str, Dict[str, Any]] = {}  # user_id -> cached account data with timestamp

    async def get_account_details(self, user_id: str, token: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.saas_base_url}/api/v1/billing/account"
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    data["is_stale"] = False
                    data["cached_at"] = time.time()
                    self._cache[user_id] = data
                    return data
                elif response.status_code == 404:
                    raise RuntimeError("Missing contract: /api/v1/billing/account endpoint not found on server")
                else:
                    raise RuntimeError(f"Server returned status {response.status_code}")
        except Exception as e:
            logger.warning(f"[CreditBalanceService] Failed to fetch live account details: {e}. Checking last-known-good cache.")
            if user_id in self._cache:
                cached = self._cache[user_id].copy()
                cached["is_stale"] = True
                return cached
            raise RuntimeError(f"Missing contract / Network offline and no cached account data available: {e}")

    async def get_balance(self, user_id: str, token: Optional[str] = None) -> Dict[str, Any]:
        try:
            account = await self.get_account_details(user_id, token)
            return {
                "user_id": user_id,
                "credits_remaining": account.get("remaining_credits", 0),
                "total_allocated": account.get("included_credits", 0),
                "plan": account.get("plan", "free"),
                "status": account.get("status", "active"),
                "is_stale": account.get("is_stale", False)
            }
        except Exception as e:
            logger.error(f"[CreditBalanceService] Error getting balance: {e}")
            raise e

    async def deduct_credits(self, user_id: str, amount: int, reason: str) -> bool:
        if user_id in self._cache:
            current = self._cache[user_id].get("remaining_credits", 0)
            if current < amount:
                return False
            self._cache[user_id]["remaining_credits"] = current - amount
            self._cache[user_id]["used_credits"] = self._cache[user_id].get("used_credits", 0) + amount
            logger.info(f"Deducted {amount} credits from {user_id} for: {reason}")
            return True
        return True
