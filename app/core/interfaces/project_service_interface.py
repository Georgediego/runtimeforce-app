"""
Abstract interface for Studio Plan top-level Project hierarchy management.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class IProjectService(ABC):

    @abstractmethod
    def list_projects(self, user_id: str) -> List[Dict[str, Any]]:
        """List projects belonging to user_id."""
        pass

    @abstractmethod
    def get_project_details(self, project_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get project details and history."""
        pass

    @abstractmethod
    def create_project(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create top-level project object."""
        pass

    @abstractmethod
    def update_project(self, project_id: str, user_id: str, payload: Dict[str, Any]) -> bool:
        """Update project context, rules, or configs."""
        pass

    @abstractmethod
    def delete_project(self, project_id: str, user_id: str) -> bool:
        """Delete project and associated changelogs."""
        pass
