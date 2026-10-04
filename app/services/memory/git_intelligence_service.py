"""
Git Intelligence Service for parsing `git log -n 5 --stat` and linking Commits to Files.
"""
import re
import logging
from typing import List, Dict, Any, Optional
from app.services.memory.graph_memory_service import GraphMemoryService
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver

logger = logging.getLogger("runtimeforce.service.memory.git_intelligence")

class GitIntelligenceService:
    def __init__(self, graph_memory: GraphMemoryService):
        self.graph_memory = graph_memory

    async def index_recent_git_activity(
        self,
        driver: IWorkspaceDriver,
        project_id: str,
        user_id: str,
        commit_count: int = 5
    ) -> List[Dict[str, Any]]:
        res = await driver.execute_command(f"git log -n {commit_count} --stat 2>/dev/null")
        if res.get("exit_code") != 0 or not res.get("stdout"):
            return []

        stdout = res["stdout"]
        commits = []
        raw_commits = stdout.split("commit ")

        for block in raw_commits:
            if not block.strip():
                continue

            lines = block.strip().splitlines()
            commit_hash = lines[0].split()[0] if lines else ""
            if not commit_hash:
                continue

            author = ""
            message_lines = []
            files_changed = []

            for line in lines[1:]:
                if line.startswith("Author:"):
                    author = line.replace("Author:", "").strip()
                elif line.startswith("    "):
                    message_lines.append(line.strip())
                elif "|" in line and ("+" in line or "-" in line):
                    file_path = line.split("|")[0].strip()
                    if file_path:
                        files_changed.append(file_path)

            message = " ".join(message_lines)
            commit_node_id = f"commit-{commit_hash[:8]}"

            self.graph_memory.record_entity(
                node_id=commit_node_id,
                user_id=user_id,
                project_id=project_id,
                node_type="Commit",
                label=f"Commit {commit_hash[:7]}: {message[:40]}",
                attributes={"hash": commit_hash, "author": author, "message": message},
                text_for_search=f"{commit_hash} {author} {message}"
            )

            for fp in files_changed:
                file_node_id = f"file-{fp}"
                self.graph_memory.link_entities(commit_node_id, file_node_id, "MODIFIED")

            commits.append({"hash": commit_hash, "author": author, "message": message, "files": files_changed})

        return commits
