"""
Tool Shell Executors with Sudo Password Support and Security Filter.
"""
from typing import Dict, Any, Optional
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver

class ToolShellExecutors:
    @staticmethod
    async def execute_command(
        driver: IWorkspaceDriver,
        command: str,
        cwd: Optional[str] = None,
        password: Optional[str] = None,
        command_filter: Optional[Any] = None
    ) -> Dict[str, Any]:
        # Every shell command is gated by the workspace driver's approval service.
        # Risk classification must never bypass the interactive approval flow.
        return await driver.execute_command(command, cwd=cwd, password=password)
