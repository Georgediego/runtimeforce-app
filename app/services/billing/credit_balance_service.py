"""
Service for AI Credit balance tracking and deduction.
"""
import logging
import httpx
from typing import Dict, Any, Optional
from app.core.interfaces.credit_balance_service_interface import ICreditBalanceService

logger = logging.getLogger("runtimeforce.service.billing.credit")

class CreditBalanceService(ICreditBalanceService):
    def __init__(self, saas_base_url: str = "https://runtimeforce.dev"):
        self.saas_base_url = saas_base_url
        self._user_credits: Dict[str, int] = {}
        self._cache: Dict[str, Dict[str, Any]] = {}

    async def get_account_details(self, user_id: str, token: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.saas_base_url}/api/v1/billing/account"
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(url, headers=headers, timeout=5.0)
                if res.status_code == 200:
                    data = res.json()
                    data["is_stale"] = False
                    self._cache[user_id] = data
                    return data
                elif res.status_code == 404:
                    raise Exception("Missing contract")
                else:
                    raise Exception(f"HTTP {res.status_code}")
        except Exception as e:
            if "Missing contract" in str(e) or "404" in str(e):
                raise Exception("Missing contract")
            if user_id in self._cache:
                cached = self._cache[user_id].copy()
                cached["is_stale"] = True
                return cached
            raise e

    async def get_balance(self, user_id: str, token: Optional[str] = None) -> Dict[str, Any]:
        try:
            acc = await self.get_account_details(user_id, token=token)
            return {
                "user_id": user_id,
                "credits_remaining": acc.get("remaining_credits", 5000),
                "total_allocated": acc.get("included_credits", 5000),
                "is_stale": acc.get("is_stale", False)
            }
        except Exception:
            current = self._user_credits.get(user_id, 5000)
            return {"user_id": user_id, "credits_remaining": current, "total_allocated": 5000, "is_stale": True}

    async def deduct_credits(self, user_id: str, amount: int, reason: str) -> bool:
        current = self._user_credits.get(user_id, 5000)
        if current < amount:
            return False
        self._user_credits[user_id] = current - amount
        logger.info(f"Deducted {amount} credits from {user_id} for: {reason}")
        return True
