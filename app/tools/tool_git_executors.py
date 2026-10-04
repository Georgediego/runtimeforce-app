from typing import Dict, Any, Optional, List
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver

class ToolGitExecutors:
    @staticmethod
    async def git_status(driver: IWorkspaceDriver) -> Dict[str, Any]:
        res = await driver.execute_command("git status --porcelain")
        if res.get("exit_code") != 0:
            return {"error": "Not a git repository or git failed"}
        entries = []
        for line in res.get("stdout", "").splitlines():
            if len(line) >= 4:
                entries.append({"path": line[3:].strip(), "status": line[:2].strip()})
        return {"entries": entries, "count": len(entries)}

    @staticmethod
    async def git_diff(driver: IWorkspaceDriver, path: Optional[str] = None, staged: bool = False) -> Dict[str, Any]:
        cmd = "git diff"
        if staged:
            cmd += " --cached"
        if path:
            cmd += f" -- '{path}'"
        res = await driver.execute_command(cmd)
        return {"diff": res.get("stdout", "") if res.get("exit_code") == 0 else ""}

    @staticmethod
    async def git_commit(driver: IWorkspaceDriver, message: str, paths: Optional[List[str]] = None) -> Dict[str, Any]:
        if paths:
            quoted = " ".join(f"'{p}'" for p in paths)
            await driver.execute_command(f"git add -- {quoted}")
        else:
            await driver.execute_command("git add -A")

        safe_msg = message.replace("'", "'\\''")
        res = await driver.execute_command(f"git commit -m '{safe_msg}'")
        return {"success": res.get("exit_code") == 0, "stdout": res.get("stdout", ""), "stderr": res.get("stderr", "")}

    @staticmethod
    async def git_log(driver: IWorkspaceDriver, n: int = 10) -> Dict[str, Any]:
        res = await driver.execute_command(f"git log --oneline -n {n} 2>/dev/null")
        commits = []
        if res.get("exit_code") == 0 and res.get("stdout"):
            for line in res.get("stdout", "").splitlines():
                parts = line.strip().split(" ", 1)
                commits.append({"hash": parts[0], "message": parts[1] if len(parts) > 1 else ""})
        return {"commits": commits}
