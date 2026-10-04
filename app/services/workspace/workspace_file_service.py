"""
Service for file content read/write, grep search, scan, and patch operations.
"""
import logging
from typing import Dict, Any
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver

logger = logging.getLogger("runtimeforce.service.workspace.file")

class WorkspaceFileService:
    @staticmethod
    async def read_file(driver: IWorkspaceDriver, path: str) -> str:
        content = await driver.read_file(path)
        if chr(0) in content:
            return "[Binary file]"
        return content

    @staticmethod
    async def write_file(driver: IWorkspaceDriver, path: str, content: str) -> bool:
        await driver.write_file(path, content)
        return True

    @staticmethod
    async def grep(driver: IWorkspaceDriver, query: str, file_pattern: str = "**/*") -> Dict[str, Any]:
        safe_query = query.replace("'", "'\\''")
        cmd = f"grep -rn --include='{file_pattern}' '{safe_query}' . 2>/dev/null | head -100"
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

    @staticmethod
    async def scan_files(driver: IWorkspaceDriver, pattern: str = "**/*") -> Dict[str, Any]:
        cmd = f"find . -type f -path '{pattern}' 2>/dev/null | head -300"
        res = await driver.execute_command(cmd)
        stdout = res.get("stdout", "")
        files = [f.lstrip("./") for f in stdout.splitlines() if f.strip()]
        return {"files": files, "count": len(files), "pattern": pattern}

    @staticmethod
    async def apply_patch(driver: IWorkspaceDriver, filepath: str, patch_content: str) -> Dict[str, Any]:
        try:
            current = await driver.read_file(filepath)
            if current == "[Binary file]":
                return {"success": False, "error": f"Cannot patch binary file: {filepath}", "applied": 0}

            blocks = patch_content.split("<<<<<<< SEARCH")
            result = current
            applied_count = 0

            for block in blocks[1:]:
                if "=======" not in block or ">>>>>>> REPLACE" not in block:
                    continue
                search_part, replace_part = block.split("=======", 1)
                replace_part = replace_part.split(">>>>>>> REPLACE", 1)[0]
                search_text = search_part.strip("\n")
                replace_text = replace_part.strip("\n")

                if search_text in result:
                    result = result.replace(search_text, replace_text, 1)
                    applied_count += 1
                else:
                    return {
                        "success": False,
                        "error": f"SEARCH block not found in {filepath}",
                        "applied": applied_count,
                    }

            if applied_count == 0:
                return {"success": False, "error": "No valid SEARCH/REPLACE blocks found", "applied": 0}

            await driver.write_file(filepath, result)
            return {
                "success": True,
                "message": f"Applied {applied_count} block(s) to {filepath}",
                "applied": applied_count,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "applied": 0}
