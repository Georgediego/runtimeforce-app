"""
Workspace Manager Service with Strict Project-Driven Driver Resolution.
All workspace drivers are now bound to active project context.
"""
import os
import logging
from typing import Dict, Optional, Any

from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver
from app.core.interfaces.workspace_driver_factory_interface import IWorkspaceDriverFactory
from app.repository.workspace_db_repository import WorkspaceDBRepository

logger = logging.getLogger("runtimeforce.service.workspace.manager")


class WorkspaceManagerService:
    def __init__(
        self,
        workspace_repo: WorkspaceDBRepository,
        driver_factory: IWorkspaceDriverFactory,
        project_repo: Optional[Any] = None,
        command_approval_service: Optional[Any] = None,
    ):
        self.workspace_repo = workspace_repo
        self.driver_factory = driver_factory
        self.project_repo = project_repo
        self.command_approval_service = command_approval_service
        self._drivers: Dict[str, IWorkspaceDriver] = {}

    async def get_driver_for_project(
        self, user_id: str, project_id: str
    ) -> Optional[IWorkspaceDriver]:
        """Resolve driver strictly bound to given project_id."""
        if not project_id:
            return await self.get_driver(user_id)

        ws = self.workspace_repo.get_workspace_by_project_id(project_id, user_id)
        if not ws and self.project_repo:
            proj = self.project_repo.get_project(project_id, user_id)
            if proj:
                if proj.get("workspace_id"):
                    ws = self.workspace_repo.get_workspace_by_id(proj["workspace_id"], user_id)
                elif proj.get("workspace_path") or proj.get("ssh_host"):
                    ws = {
                        "id": f"ws-{project_id[-8:]}",
                        "name": f"{proj.get('name', 'Project')} Workspace",
                        "type": "ssh" if proj.get("ssh_host") else "local",
                        "path": proj.get("workspace_path") or "~",
                        "host": proj.get("ssh_host", ""),
                        "port": proj.get("ssh_port", 22),
                        "username": proj.get("ssh_username", ""),
                        "key_id": proj.get("ssh_key_id", ""),
                        "project_id": project_id,
                    }
        if not ws:
            return await self.get_driver(user_id)
        return await self.get_driver_by_workspace_id(ws["id"], user_id, override_ws=ws)

    async def get_driver(self, user_id: str) -> Optional[IWorkspaceDriver]:
        """Resolve driver via active project first, fallback to active workspace."""
        active_project = None
        if self.project_repo:
            active_project = self.project_repo.get_active_project(user_id)

        if active_project:
            ws = self.workspace_repo.get_workspace_by_project_id(
                active_project["id"], user_id
            )
            if ws:
                return await self.get_driver_by_workspace_id(ws["id"], user_id)
            elif active_project.get("workspace_path") or active_project.get("ssh_host"):
                return await self.get_driver_for_project(user_id, active_project["id"])

        active_ws = self.workspace_repo.get_active_workspace(user_id)
        if not active_ws:
            return None
        return await self.get_driver_by_workspace_id(active_ws["id"], user_id)

    async def get_driver_by_workspace_id(
        self, wid: str, user_id: str, override_ws: Optional[Dict[str, Any]] = None
    ) -> Optional[IWorkspaceDriver]:
        ws = override_ws or self.workspace_repo.get_workspace_by_id(wid, user_id)
        if not ws:
            return None

        ws_type = ws.get("type", "local")
        path = ws.get("path") or "~"
        norm_path = os.path.realpath(os.path.abspath(os.path.expanduser(path)))

        existing = self._drivers.get(wid)
        if existing:
            if ws_type == "local" and getattr(existing, "root", "") == norm_path:
                self._attach_approval(existing, ws, user_id)
                return existing

        driver = self.driver_factory.create_driver(ws, user_id)
        if driver:
            self._drivers[wid] = driver
            self._attach_approval(driver, ws, user_id)
        return driver

    def _attach_approval(self, driver, ws: Dict[str, Any], user_id: str) -> None:
        if not self.command_approval_service:
            return
        driver.command_approval_service = self.command_approval_service
        driver.command_approval_metadata = {
            "user_id": user_id,
            "workspace_id": str(ws.get("id") or ""),
            "project_id": str(ws.get("project_id") or ""),
            "target": "ssh" if ws.get("type") == "ssh" else "local",
        }

    def invalidate_driver(self, wid: str) -> None:
        """Remove cached driver (e.g. after credentials change)."""
        self._drivers.pop(wid, None)
