"""
Git operations abstraction.
Uses --porcelain (v1) for maximum compatibility across git versions.
Works transparently for both local and SSH workspaces.
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("ai_runtime.git")


# ── Git v1 porcelain status map ──────────────────
# Format: XY PATH where XY are 2 chars
# X = index (staged), Y = working tree (unstaged)
STATUS_MAP = {
    " ": "unchanged",
    "M": "modified",
    "A": "added",
    "D": "deleted",
    "R": "renamed",
    "C": "copied",
    "U": "unmerged",
    "?": "untracked",
    "!": "ignored",
    "T": "typechange",
}


class GitOps:
    """High-level git operations delegated to workspace_manager."""

    def __init__(self, workspace_manager):
        self.wm = workspace_manager

    async def _run(self, cmd: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        return await self.wm.execute(cmd, cwd=cwd, timeout=30.0)

    async def is_repo(self) -> bool:
        r = await self._run("git rev-parse --is-inside-work-tree")
        return r.get("exit_code") == 0

    async def status(self) -> List[Dict[str, Any]]:
        """
        Parse git status --porcelain (v1 format).
        Format: XY PATH (or XY ORIG -> PATH for renames)
        More reliable than v2 across git versions.
        """
        # Try v1 format (more compatible)
        r = await self._run("git status --porcelain")
        if r.get("exit_code") != 0:
            # Maybe git not installed or not a repo
            return []

        entries = []
        for line in r.get("stdout", "").splitlines():
            # Minimum: 2 status chars + 1 space + 1 char path = 4 chars
            if len(line) < 4:
                continue

            x = line[0]  # index status (staged)
            y = line[1]  # worktree status (unstaged)
            rest = line[3:].strip()  # path (after "XY ")

            if not rest:
                continue

            # Determine overall status
            if x == "?" and y == "?":
                status = "untracked"
            elif x == "!" and y == "!":
                status = "ignored"
            elif x == "A":
                status = "added"
            elif x == "R" or " -> " in rest:
                status = "renamed"
                # Parse "orig -> new"
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
                status = "modified"  # fallback

            # Remove quotes from path if present
            path = rest.strip('"')

            entries.append({
                "path": path,
                "status": status,
                "staged": x not in (" ", "?", "!", ""),
                "unstaged": y not in (" ", "?", "!", ""),
            })

        return entries

    async def diff(self, path: Optional[str] = None, staged: bool = False) -> str:
        cmd = "git diff"
        if staged:
            cmd += " --cached"
        if path:
            cmd += f" -- '{path}'"
        r = await self._run(cmd)
        return r.get("stdout", "") if r.get("exit_code") == 0 else ""

    async def commit(self, message: str, paths: Optional[List[str]] = None) -> Dict[str, Any]:
        if paths:
            quoted = " ".join(f"'{p}'" for p in paths)
            add_cmd = f"git add -- {quoted}"
        else:
            add_cmd = "git add -A"

        r_add = await self._run(add_cmd)
        if r_add.get("exit_code") != 0:
            return {"error": f"git add failed: {r_add.get('stderr', '')}"}

        safe_msg = message.replace("'", "'\"'\"'")
        r_commit = await self._run(f"git commit -m '{safe_msg}'")

        if r_commit.get("exit_code") != 0:
            stderr = r_commit.get("stderr", "")
            if "nothing to commit" in stderr:
                return {"hash": None, "message": "Nothing to commit"}
            return {"error": f"git commit failed: {stderr}"}

        # Extract commit hash from output like "[main abc1234] message"
        stdout = r_commit.get("stdout", "")
        commit_hash = ""
        for line in stdout.splitlines():
            if line.startswith("[") and "]" in line:
                try:
                    # Format: [branch hash] message
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

    async def log(self, n: int = 10) -> List[Dict[str, str]]:
        """Get last N commits with fallback formats."""
        # Try structured format first
        fmt = "--format=%H||%an||%ai||%s"
        r = await self._run(f"git log {fmt} -n {n} 2>/dev/null")

        if r.get("exit_code") == 0 and r.get("stdout", "").strip():
            commits = []
            for line in r.get("stdout", "").splitlines():
                line = line.strip()
                if not line or "||" not in line:
                    continue
                parts = line.split("||", 3)
                if len(parts) == 4:
                    commits.append({
                        "hash": parts[0][:12],  # Short hash
                        "author": parts[1],
                        "date": parts[2],
                        "message": parts[3],
                    })
            if commits:
                return commits

        # Fallback: --oneline (simpler, works on older git)
        r2 = await self._run(f"git log --oneline -n {n} 2>/dev/null")
        if r2.get("exit_code") == 0 and r2.get("stdout", "").strip():
            commits = []
            for line in r2.get("stdout", "").splitlines():
                line = line.strip()
                if not line:
                    continue
                # Format: "abc1234 commit message"
                parts = line.split(" ", 1)
                if len(parts) >= 2:
                    commits.append({
                        "hash": parts[0],
                        "author": "",
                        "date": "",
                        "message": parts[1],
                    })
                elif len(parts) == 1:
                    commits.append({
                        "hash": parts[0],
                        "author": "",
                        "date": "",
                        "message": "",
                    })
            return commits

        return []

    async def revert_file(self, path: str) -> Dict[str, Any]:
        r = await self._run(f"git checkout HEAD -- '{path}'")
        if r.get("exit_code") == 0:
            return {"status": "success", "path": path}
        return {"error": r.get("stderr", "Revert failed")}

    async def checkpoint(self, label: str) -> Dict[str, Any]:
        status = await self.status()
        has_changes = any(e["status"] not in ("unchanged",) for e in status)
        if not has_changes:
            return {"hash": None, "message": "No changes to checkpoint"}
        msg = f"[AI checkpoint] {label}"
        return await self.commit(msg)

    async def branches(self) -> List[Dict[str, Any]]:
        # Try with format first
        r = await self._run("git branch --format='%(refname:short) %(HEAD)' 2>/dev/null")
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

        # Fallback: plain git branch
        r2 = await self._run("git branch 2>/dev/null")
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
