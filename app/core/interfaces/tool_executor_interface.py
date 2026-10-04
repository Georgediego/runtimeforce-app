"""
Abstract interface for dispatching and executing agent tool commands.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver

class IToolExecutor(ABC):

    @abstractmethod
    async def execute(
        self,
        tool_name: str,
        arguments_json: str,
        driver: IWorkspaceDriver
    ) -> Dict[str, Any]:
        """Dispatch and execute tool call with driver context."""
        pass
