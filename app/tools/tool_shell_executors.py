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
        if command_filter and hasattr(command_filter, "is_safe"):
            is_safe, reason = command_filter.is_safe(command)
            if not is_safe and not password:
                return {"exit_code": -1, "stdout": "", "stderr": f"Security Block: {reason}", "status": "blocked"}
        return await driver.execute_command(command, cwd=cwd, password=password)
