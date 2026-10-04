"""
Service for Git repository status check and porcelain parsing.
"""
import logging
from typing import List, Dict, Any
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver

logger = logging.getLogger("runtimeforce.service.git.status")

class GitStatusService:
    @staticmethod
    async def is_repo(driver: IWorkspaceDriver) -> bool:
        r = await driver.execute_command("git rev-parse --is-inside-work-tree")
        return r.get("exit_code") == 0

    @staticmethod
    async def status(driver: IWorkspaceDriver) -> List[Dict[str, Any]]:
        r = await driver.execute_command("git status --porcelain")
        if r.get("exit_code") != 0:
            return []

        entries = []
        for line in r.get("stdout", "").splitlines():
            if len(line) < 4:
                continue
            x = line[0]
            y = line[1]
            rest = line[3:].strip()
            if not rest:
                continue

            if x == "?" and y == "?":
                status = "untracked"
            elif x == "!" and y == "!":
                status = "ignored"
            elif x == "A":
                status = "added"
            elif x == "R" or " -> " in rest:
                status = "renamed"
                if " -> " in rest:
                    parts = rest.split(" -> ", 1)
                    rest = parts[1].strip().strip('"')
            elif x == "C":
                status = "copied"
            elif x == "D" or y == "D":
                status = "deleted"
            elif x == "U" or y == "U":
                status = "unmerged"
            elif x == "T" or y == "T":
                status = "typechange"
            elif x == "M" or y == "M":
                status = "modified"
            else:
                status = "modified"

            path = rest.strip('"')
            entries.append({
                "path": path,
                "status": status,
                "staged": x not in (" ", "?", "!", ""),
                "unstaged": y not in (" ", "?", "!", ""),
            })

        return entries
