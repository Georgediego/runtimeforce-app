"""
Service for AI Credit balance tracking and deduction.
"""
import logging
from typing import Dict, Any
from app.core.interfaces.credit_balance_service_interface import ICreditBalanceService

logger = logging.getLogger("runtimeforce.service.billing.credit")

class CreditBalanceService(ICreditBalanceService):
    def __init__(self):
        self._user_credits: Dict[str, int] = {}

    async def get_balance(self, user_id: str) -> Dict[str, Any]:
        current = self._user_credits.get(user_id, 5000)
        return {"user_id": user_id, "credits_remaining": current, "total_allocated": 5000}

    async def deduct_credits(self, user_id: str, amount: int, reason: str) -> bool:
        current = self._user_credits.get(user_id, 5000)
        if current < amount:
            return False
        self._user_credits[user_id] = current - amount
        logger.info(f"Deducted {amount} credits from {user_id} for: {reason}")
        return True
