"""
Service for Git init, add, and commit operations.
"""
import logging
from typing import List, Dict, Any, Optional
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver

logger = logging.getLogger("runtimeforce.service.git.commit")

class GitCommitService:
    @staticmethod
    async def init_repo(driver: IWorkspaceDriver) -> Dict[str, Any]:
        r = await driver.execute_command("git init")
        return {
            "success": r.get("exit_code") == 0,
            "stdout": r.get("stdout", ""),
            "stderr": r.get("stderr", "")
        }

    @staticmethod
    async def commit(
        driver: IWorkspaceDriver, message: str, paths: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        if paths:
            quoted = " ".join(f"'{p}'" for p in paths)
            add_cmd = f"git add -- {quoted}"
        else:
            add_cmd = "git add -A"

        r_add = await driver.execute_command(add_cmd)
        if r_add.get("exit_code") != 0:
            return {"error": f"git add failed: {r_add.get('stderr', '')}"}

        safe_msg = message.replace("'", "'\\''")
        r_commit = await driver.execute_command(f"git commit -m '{safe_msg}'")

        if r_commit.get("exit_code") != 0:
            stderr = r_commit.get("stderr", "")
            if "nothing to commit" in stderr:
                return {"hash": None, "message": "Nothing to commit"}
            return {"error": f"git commit failed: {stderr}"}

        stdout = r_commit.get("stdout", "")
        commit_hash = ""
        for line in stdout.splitlines():
            if line.startswith("[") and "]" in line:
                try:
                    bracket_content = line.split("]", 1)[0][1:]
                    parts = bracket_content.split(" ", 1)
                    if len(parts) >= 2:
                        commit_hash = parts[1].strip()
                    elif len(parts) == 1:
                        commit_hash = parts[0].strip()
                except Exception:
                    pass
                break

        return {"hash": commit_hash, "message": message}
