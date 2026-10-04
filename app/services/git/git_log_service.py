"""
Service for Git log history retrieval.
"""
import logging
from typing import List, Dict, Any
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver

logger = logging.getLogger("runtimeforce.service.git.log")

class GitLogService:
    @staticmethod
    async def log(driver: IWorkspaceDriver, n: int = 10) -> List[Dict[str, str]]:
        fmt = "--format=%H||%an||%ai||%s"
        r = await driver.execute_command(f"git log {fmt} -n {n} 2>/dev/null")

        if r.get("exit_code") == 0 and r.get("stdout", "").strip():
            commits = []
            for line in r.get("stdout", "").splitlines():
                line = line.strip()
                if not line or "||" not in line:
                    continue
                parts = line.split("||", 3)
                if len(parts) == 4:
                    commits.append({
                        "hash": parts[0][:12],
                        "author": parts[1],
                        "date": parts[2],
                        "message": parts[3],
                    })
            if commits:
                return commits

        r2 = await driver.execute_command(f"git log --oneline -n {n} 2>/dev/null")
        if r2.get("exit_code") == 0 and r2.get("stdout", "").strip():
            commits = []
            for line in r2.get("stdout", "").splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(" ", 1)
                commits.append({
                    "hash": parts[0],
                    "author": "",
                    "date": "",
                    "message": parts[1] if len(parts) >= 2 else "",
                })
            return commits

        return []
