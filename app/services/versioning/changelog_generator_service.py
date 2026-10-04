"""
Service for generating structured changelogs from git commit history.
"""
import logging
from typing import List, Dict, Any

logger = logging.getLogger("runtimeforce.service.versioning.changelog")

class ChangelogGeneratorService:
    @staticmethod
    def generate_from_commits(commits: List[Dict[str, str]]) -> str:
        if not commits:
            return "Routine maintenance and bug fixes."
        lines = []
        for c in commits:
            msg = c.get("message", "").strip()
            if msg:
                lines.append(f"- {msg}")
        return "\n".join(lines) if lines else "General code improvements."
