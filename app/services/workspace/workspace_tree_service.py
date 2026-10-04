"""
Service for file tree generation and directory listing.
"""
import os
import logging
from typing import Dict, Any
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver

logger = logging.getLogger("runtimeforce.service.workspace.tree")

ALWAYS_SKIP = {
    ".git", "__pycache__", "node_modules", "venv", ".venv",
    ".pytest_cache", "staticfiles", "media", ".cache", ".DS_Store"
}

class WorkspaceTreeService:
    @staticmethod
    async def get_tree(driver: IWorkspaceDriver, root_path: str, max_depth: int = 3) -> Dict[str, Any]:
        root_name = os.path.basename(root_path.rstrip("/")) or root_path
        node = {
            "name": root_name,
            "path": root_path,
            "type": "directory",
            "is_dir": True,
            "children": [],
        }

        try:
            entries = await driver.list_dir(root_path)
            for entry in entries:
                name = entry["name"]
                if name in ALWAYS_SKIP:
                    continue
                node["children"].append({
                    "name": name,
                    "path": entry["path"],
                    "is_dir": entry["is_dir"],
                    "type": "directory" if entry["is_dir"] else "file",
                })
        except Exception as e:
            logger.error(f"Failed to build tree for {root_path}: {e}")

        return node

    @staticmethod
    async def get_tree_children(driver: IWorkspaceDriver, dir_path: str) -> Dict[str, Any]:
        children = []
        try:
            entries = await driver.list_dir(dir_path)
            for entry in entries:
                name = entry["name"]
                if name in ALWAYS_SKIP:
                    continue
                children.append({
                    "name": name,
                    "path": entry["path"],
                    "is_dir": entry["is_dir"],
                    "type": "directory" if entry["is_dir"] else "file",
                })
        except Exception as e:
            logger.error(f"Failed to fetch children for {dir_path}: {e}")

        return {"path": dir_path, "children": children}
