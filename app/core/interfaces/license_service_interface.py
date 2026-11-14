"""Interface for server-verified, dynamic plan entitlements."""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ILicenseService(ABC):
    @abstractmethod
    async def get_entitlements(self, jwt_token: Optional[str], user_id: Optional[str] = None) -> Dict[str, Any]:
        """Fetch and validate the account's feature map and limits from the SaaS server."""
        raise NotImplementedError
