import uuid
import logging
from typing import List, Dict, Any, Optional
from app.repository.project_db_repository import ProjectDBRepository
from app.repository.workspace_db_repository import WorkspaceDBRepository
from app.core.interfaces.versioning_service_interface import IVersioningService

logger = logging.getLogger("runtimeforce.service.project")

class ProjectService:
    def __init__(
        self,
        project_repo: ProjectDBRepository,
        version_calculator: Optional[IVersioningService] = None,
        workspace_repo: Optional[WorkspaceDBRepository] = None
    ):
        self.repo = project_repo
        self.version_calculator = version_calculator
        self.workspace_repo = workspace_repo

    def list_projects(self, user_id: str) -> List[Dict[str, Any]]:
        return self.repo.list_projects(user_id)

    def list_user_projects(self, user_id: str) -> List[Dict[str, Any]]:
        return self.list_projects(user_id)

    def get_active_project(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.repo.get_active_project(user_id)

    def get_project_details(self, project_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        proj = self.repo.get_project(project_id, user_id)
        if proj:
            proj["changelogs"] = self.repo.get_changelogs(project_id)
            if self.workspace_repo:
                proj["workspace"] = self.workspace_repo.get_workspace_by_project_id(project_id, user_id)
        return proj

    def get_project_with_workspace(self, project_id: str, user_id: str) -> Dict[str, Any]:
        proj = self.get_project_details(project_id, user_id)
        ws = self.workspace_repo.get_workspace_by_project_id(project_id, user_id) if self.workspace_repo else None
        return {"project": proj, "workspace": ws}

    def create_project(self, user_id: str, payload: Dict[str, Any], plan: str = "free", max_projects: int = 1) -> Dict[str, Any]:
        existing = self.repo.list_projects(user_id)
        max_allowed = max(0, int(1 if max_projects is None else max_projects))
        
        if len(existing) >= max_allowed:
            return {
                "error": f"Project limit reached for {plan.upper()} tier ({len(existing)}/{max_allowed}). Please upgrade your plan.",
                "status": "limit_reached"
            }

        pid = str(uuid.uuid4())
        initial_version = payload.get("current_version") or "v1.0.0"
        success = self.repo.create_project(
            project_id=pid,
            user_id=user_id,
            name=payload.get("name", "New Project"),
            workspace_id=payload.get("workspace_id", ""),
            project_context=payload.get("project_context", ""),
            rules_of_engagement=payload.get("rules_of_engagement", ""),
            workspace_path=payload.get("workspace_path", ""),
            ssh_host=payload.get("ssh_host", ""),
            ssh_port=payload.get("ssh_port", 22),
            ssh_username=payload.get("ssh_username", ""),
            ssh_key_id=payload.get("ssh_key_id", ""),
            github_remote_url=payload.get("github_remote_url", ""),
            github_pat_enc=payload.get("github_pat_enc", ""),
            x_api_key_enc=payload.get("x_api_key_enc", ""),
            reddit_client_id_enc=payload.get("reddit_client_id_enc", ""),
            reddit_client_secret_enc=payload.get("reddit_client_secret_enc", ""),
            git_mode=payload.get("git_mode", "manual"),
            git_branch_main=payload.get("git_branch_main", "main"),
            git_branch_dev=payload.get("git_branch_dev", "dev"),
            version_scheme=payload.get("version_scheme", "semver"),
            prerelease_tag=payload.get("prerelease_tag", ""),
            current_version=initial_version,
            is_active=payload.get("activate", True)
        )
        if success:
            if payload.get("activate", True):
                self.repo.set_active_project(pid, user_id)
            self.repo.record_changelog(pid, initial_version, "Initial project creation", None, payload.get("git_branch_main", "main"))
        return {"id": pid, "status": "created" if success else "failed"}

    def activate_project(self, project_id: str, user_id: str) -> bool:
        return self.repo.set_active_project(project_id, user_id)

    def update_project(self, project_id: str, user_id: str, payload: Dict[str, Any]) -> bool:
        return self.repo.update_project(project_id, user_id, **payload)

    def delete_project(self, project_id: str, user_id: str) -> bool:
        return self.repo.delete_project(project_id, user_id)

    def bump_version(self, project_id: str, user_id: str, changelog_entry: str, bump_type: str = "patch", commit_hash: Optional[str] = None, target_branch: Optional[str] = None) -> Dict[str, Any]:
        proj = self.repo.get_project(project_id, user_id)
        if not proj:
            return {"error": "Project not found"}

        if self.version_calculator:
            next_ver = self.version_calculator.calculate_next_version(
                current_version=proj.get("current_version", "v1.0.0"),
                scheme=proj.get("version_scheme", "semver"),
                bump_type=bump_type,
                tag=proj.get("prerelease_tag", "")
            )
        else:
            next_ver = proj.get("current_version", "v1.0.0")

        branch = target_branch or (proj.get("git_branch_main") if bump_type in ("major", "minor") else proj.get("git_branch_dev"))
        self.repo.record_changelog(project_id, next_ver, changelog_entry, commit_hash, branch)
        return {
            "project_id": project_id,
            "new_version": next_ver,
            "changelog_entry": changelog_entry,
            "target_branch": branch
        }
