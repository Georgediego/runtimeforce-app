"""
Service for calculating SemVer, CalVer, and Hybrid version bumps.
"""
import time
import logging
from typing import Dict, Any, Optional
from app.core.interfaces.versioning_service_interface import IVersioningService
from app.repository.versioning_db_repository import VersioningDBRepository
from app.core.events.event_bus import EventBus

logger = logging.getLogger("runtimeforce.service.versioning")

class VersionCalculatorService(IVersioningService):
    def __init__(self, version_repo: VersioningDBRepository, event_bus: EventBus):
        self.repo = version_repo
        self.event_bus = event_bus

    def calculate_next_version(
        self,
        current_version: str,
        scheme: str = "semver",
        bump_type: str = "patch",
        tag: str = ""
    ) -> str:
        clean_curr = (current_version or "v1.0.0").lstrip("v")
        base_ver = clean_curr.split("-")[0]
        today_str = time.strftime("%Y.%m.%d")

        if scheme == "calver":
            if base_ver.startswith(today_str):
                try:
                    parts = base_ver.split(".")
                    sub = int(parts[3]) + 1 if len(parts) > 3 else 1
                    next_base = f"{today_str}.{sub}"
                except Exception:
                    next_base = f"{today_str}.1"
            else:
                next_base = today_str

        elif scheme == "hybrid":
            try:
                sem_part = base_ver.split("-")[0] if "-" in base_ver else "1.0.0"
                parts = [int(x) for x in sem_part.split(".")]
            except Exception:
                parts = [1, 0, 0]

            if bump_type == "major": parts[0] += 1; parts[1] = 0; parts[2] = 0
            elif bump_type == "minor": parts[1] += 1; parts[2] = 0
            else: parts[2] += 1

            next_base = f"{today_str}-{parts[0]}.{parts[1]}.{parts[2]}"

        else: # SemVer
            try:
                parts = [int(x) for x in base_ver.split(".")]
                while len(parts) < 3: parts.append(0)
            except Exception:
                parts = [1, 0, 0]

            if bump_type == "major": parts[0] += 1; parts[1] = 0; parts[2] = 0
            elif bump_type == "minor": parts[1] += 1; parts[2] = 0
            else: parts[2] += 1

            next_base = f"{parts[0]}.{parts[1]}.{parts[2]}"

        suffix = f"-{tag.lstrip('-')}" if tag else ""
        return f"v{next_base}{suffix}"

    def record_changelog(
        self,
        project_id: str,
        user_id: str,
        changelog_entry: str,
        bump_type: str = "patch",
        commit_hash: Optional[str] = None
    ) -> Dict[str, Any]:
        current_ver = "v1.0.0"
        next_ver = self.calculate_next_version(current_ver, bump_type=bump_type)
        success = self.repo.record_version(project_id, user_id, next_ver, changelog_entry, commit_hash)
        if success:
            try:
                self.event_bus.publish("project.version_bumped", project_id=project_id, version=next_ver, user_id=user_id)
            except Exception as e:
                logger.error(f"Failed to publish version_bumped event: {e}")
        return {"project_id": project_id, "new_version": next_ver, "changelog": changelog_entry}
