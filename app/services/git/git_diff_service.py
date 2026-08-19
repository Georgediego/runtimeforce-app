"""
Service for Git diff generation.
"""
import logging
from typing import Optional
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver

logger = logging.getLogger("runtimeforce.service.git.diff")

class GitDiffService:
    @staticmethod
    async def diff(driver: IWorkspaceDriver, path: Optional[str] = None, staged: bool = False) -> str:
        cmd = "git diff"
        if staged:
            cmd += " --cached"
        if path:
            cmd += f" -- '{path}'"
        r = await driver.execute_command(cmd)
        return r.get("stdout", "") if r.get("exit_code") == 0 else ""
