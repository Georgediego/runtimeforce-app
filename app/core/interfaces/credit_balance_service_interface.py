"""
Abstract interface for AI Credit ledger and usage tracking.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict

class ICreditBalanceService(ABC):

    @abstractmethod
    async def get_balance(self, user_id: str) -> Dict[str, Any]:
        """Retrieve remaining AI Credits for user_id."""
        pass

    @abstractmethod
    async def deduct_credits(self, user_id: str, amount: int, reason: str) -> bool:
        """Deduct AI Credits from user balance."""
        pass
