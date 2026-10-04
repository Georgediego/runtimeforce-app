"""
Service for Git branch inspection.
"""
import logging
from typing import List, Dict, Any
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver

logger = logging.getLogger("runtimeforce.service.git.branch")

class GitBranchService:
    @staticmethod
    async def branches(driver: IWorkspaceDriver) -> List[Dict[str, Any]]:
        r = await driver.execute_command("git branch --format='%(refname:short) %(HEAD)' 2>/dev/null")
        if r.get("exit_code") == 0 and r.get("stdout", "").strip():
            branches = []
            for line in r.get("stdout", "").splitlines():
                line = line.strip().strip("'")
                if not line:
                    continue
                parts = line.rsplit(" ", 1)
                if len(parts) == 2:
                    branches.append({
                        "name": parts[0].strip(),
                        "current": parts[1].strip() == "*",
                    })
                elif len(parts) == 1:
                    branches.append({"name": parts[0].strip(), "current": False})
            if branches:
                return branches

        r2 = await driver.execute_command("git branch 2>/dev/null")
        if r2.get("exit_code") == 0 and r2.get("stdout", "").strip():
            branches = []
            for line in r2.get("stdout", "").splitlines():
                line = line.strip()
                if not line:
                    continue
                is_current = line.startswith("* ")
                name = line[2:].strip() if is_current else line.strip()
                if name:
                    branches.append({"name": name, "current": is_current})
            return branches

        return []
