"""
Abstract interface for verifying user subscription tiers and offline grace.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class ILicenseService(ABC):

    @abstractmethod
    def validate_license(self, jwt_token: Optional[str]) -> Dict[str, Any]:
        """Verify JWT claims and check subscription tier entitlement."""
        pass

    @abstractmethod
    def is_offline_grace_valid(self) -> bool:
        """Check if cached license is within allowed offline grace period."""
        pass
