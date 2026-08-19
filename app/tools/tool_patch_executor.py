from typing import Dict, Any
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver

class ToolPatchExecutor:
    @staticmethod
    async def apply_code_patch(driver: IWorkspaceDriver, filepath: str, patch_content: str) -> Dict[str, Any]:
        try:
            current = await driver.read_file(filepath)
            if chr(0) in current:
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
