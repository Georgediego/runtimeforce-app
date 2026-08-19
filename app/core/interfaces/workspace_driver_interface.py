"""
Abstract interface for workspace execution drivers (Local, SSH, Docker, etc.).
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class IWorkspaceDriver(ABC):

    @abstractmethod
    async def read_file(self, path: str) -> str:
        """Read file content as UTF-8 string."""
        pass

    @abstractmethod
    async def write_file(self, path: str, content: str) -> None:
        """Write content to file."""
        pass

    @abstractmethod
    async def execute_command(
        self, command: str, cwd: Optional[str] = None, timeout: float = 30.0
    ) -> Dict[str, Any]:
        """Execute shell command. Returns dict with stdout, stderr, exit_code."""
        pass

    @abstractmethod
    async def list_dir(self, path: str) -> List[Dict[str, Any]]:
        """List directory entries."""
        pass

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check driver connection/health status."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up connection resources."""
        pass
