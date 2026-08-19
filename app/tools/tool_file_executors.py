"""
Tool File Executors with Fuzzy Path Resolution, Smart Search Fallback & Real Disk Writing.
"""
import os
import glob
import logging
from typing import Dict, Any, List, Optional
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver

logger = logging.getLogger("runtimeforce.tools.file_executors")

class ToolFileExecutors:
    @staticmethod
    def _find_actual_filepath(driver: IWorkspaceDriver, target_path: str) -> str:
        """Find the real relative path in workspace if agent passed a misaligned subpath."""
        root = getattr(driver, "root", ".")
        clean_target = target_path.lstrip("/").strip()

        # 1. Direct path check
        direct = os.path.join(root, clean_target)
        if os.path.exists(direct):
            return clean_target

        # 2. Check if absolute path starts with workspace root
        if os.path.isabs(target_path) and os.path.exists(target_path):
            try:
                rel = os.path.relpath(target_path, root)
                if not rel.startswith(".."):
                    return rel
            except Exception:
                pass

        # 3. Search by filename or relative subpath inside workspace
        basename = os.path.basename(clean_target)
        for dirpath, _, filenames in os.walk(root):
            if any(skip in dirpath for skip in [".git", "node_modules", ".venv", "__pycache__", ".cache"]):
                continue
            for f in filenames:
                if f == basename or clean_target.endswith(f):
                    full_match = os.path.join(dirpath, f)
                    rel = os.path.relpath(full_match, root)
                    if clean_target in rel or rel.endswith(clean_target) or f == basename:
                        return rel

        return clean_target

    @staticmethod
    async def read_file(driver: IWorkspaceDriver, filepath: str) -> Dict[str, Any]:
        if not filepath:
            return {"error": "Filepath argument is required"}

        actual_path = ToolFileExecutors._find_actual_filepath(driver, filepath)
        try:
            content = await driver.read_file(actual_path)
            if chr(0) in content:
                content = "[Binary file]"
            return {"path": actual_path, "content": content, "status": "success"}
        except FileNotFoundError:
            # Provide actionable hint so agent creates or scans instead of giving up
            return {
                "error": f"File '{filepath}' not found in workspace.",
                "path": actual_path,
                "hint": "Use write_workspace_file to create this file directly, or scan_workspace to locate existing files."
            }
        except Exception as e:
            return {"error": str(e), "path": actual_path}

    @staticmethod
    async def write_file(driver: IWorkspaceDriver, filepath: str, content: str) -> Dict[str, Any]:
        if not filepath:
            return {"error": "Filepath argument is required"}
        try:
            actual_path = ToolFileExecutors._find_actual_filepath(driver, filepath)
            await driver.write_file(actual_path, content)
            return {"success": True, "path": actual_path, "bytes_written": len(content.encode("utf-8"))}
        except Exception as e:
            logger.error(f"Failed to write file {filepath}: {e}")
            return {"error": str(e), "path": filepath}

    @staticmethod
    async def scan_workspace(driver: IWorkspaceDriver, pattern: str = "**/*") -> Dict[str, Any]:
        cmd = f"find . -type f -not -path '*/.*' -not -path './node_modules/*' -not -path './.venv/*' | head -300"
        res = await driver.execute_command(cmd)
        stdout = res.get("stdout", "")
        files = [f.lstrip("./") for f in stdout.splitlines() if f.strip()]
        return {"files": files, "count": len(files), "pattern": pattern}

    @staticmethod
    async def search_grep(driver: IWorkspaceDriver, query: str, file_pattern: str = "**/*") -> Dict[str, Any]:
        safe_query = query.replace("'", "'\\''")
        cmd = f"grep -rn --exclude-dir='.git' --exclude-dir='.venv' --exclude-dir='node_modules' '{safe_query}' . 2>/dev/null | head -100"
        res = await driver.execute_command(cmd)
        stdout = res.get("stdout", "")
        matches = []
        for line in stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split(":", 2)
            if len(parts) >= 3:
                matches.append({
                    "file": parts[0].lstrip("./"),
                    "line": parts[1],
                    "content": parts[2].strip()[:200],
                })
        return {"matches": matches[:100], "count": len(matches), "query": query}
