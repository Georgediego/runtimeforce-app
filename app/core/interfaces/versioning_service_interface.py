"""
Abstract interface for SemVer/CalVer automatic version calculation and changelogs.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class IVersioningService(ABC):

    @abstractmethod
    def calculate_next_version(
        self,
        current_version: str,
        scheme: str = "semver",
        bump_type: str = "patch",
        tag: str = ""
    ) -> str:
        """Calculate next SemVer/CalVer version tag."""
        pass

    @abstractmethod
    def record_changelog(
        self,
        project_id: str,
        user_id: str,
        changelog_entry: str,
        bump_type: str = "patch",
        commit_hash: Optional[str] = None
    ) -> Dict[str, Any]:
        """Bump version and record changelog entry."""
        pass
