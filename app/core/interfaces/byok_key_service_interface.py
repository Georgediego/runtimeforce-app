"""
Abstract interface for local BYOK provider API key encryption and retrieval.
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional

class IByokKeyService(ABC):

    @abstractmethod
    def save_key(
        self,
        provider: str,
        plain_key: str,
        user_id: str,
        jwt_token: Optional[str] = None
    ) -> None:
        """Encrypt and store provider API key bound to user_id."""
        pass

    @abstractmethod
    def get_decrypted_keys(
        self,
        user_id: str,
        jwt_token: Optional[str] = None
    ) -> Dict[str, str]:
        """Decrypt and return active BYOK keys for authorized license."""
        pass
