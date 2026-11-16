import asyncio

from app.services.workspace.workspace_manager_service import WorkspaceManagerService


class FakeWorkspaceRepository:
    def __init__(self, workspace=None):
        self.workspace = workspace
        self.global_lookup_called = False

    def get_workspace_by_project_id(self, project_id, user_id):
        return self.workspace

    def get_workspace_by_id(self, workspace_id, user_id):
        return self.workspace if self.workspace and self.workspace["id"] == workspace_id else None

    def get_active_workspace(self, user_id):
        self.global_lookup_called = True
        return {"id": "another-project-workspace", "type": "local", "path": "/tmp/other"}


class FakeProjectRepository:
    def __init__(self, project=None):
        self.project = project

    def get_project(self, project_id, user_id):
        return self.project

    def get_active_project(self, user_id):
        return None


class FakeDriverFactory:
    def __init__(self):
        self.created_for = []

    def create_driver(self, workspace, user_id):
        self.created_for.append(workspace["id"])
        return object()


def test_project_without_workspace_does_not_inherit_global_workspace():
    workspace_repo = FakeWorkspaceRepository()
    factory = FakeDriverFactory()
    manager = WorkspaceManagerService(
        workspace_repo,
        factory,
        project_repo=FakeProjectRepository({"id": "project-a"}),
    )

    driver = asyncio.run(manager.get_driver_for_project("user-a", "project-a"))

    assert driver is None
    assert factory.created_for == []
    assert workspace_repo.global_lookup_called is False


def test_project_driver_uses_only_its_own_workspace():
    own_workspace = {
        "id": "workspace-project-a",
        "project_id": "project-a",
        "type": "local",
        "path": "/tmp/project-a",
    }
    workspace_repo = FakeWorkspaceRepository(own_workspace)
    factory = FakeDriverFactory()
    manager = WorkspaceManagerService(
        workspace_repo,
        factory,
        project_repo=FakeProjectRepository({"id": "project-a"}),
    )

    driver = asyncio.run(manager.get_driver_for_project("user-a", "project-a"))

    assert driver is not None
    assert factory.created_for == ["workspace-project-a"]
    assert workspace_repo.global_lookup_called is False


def test_user_global_workspace_is_not_used_when_no_project_is_active():
    workspace_repo = FakeWorkspaceRepository()
    manager = WorkspaceManagerService(
        workspace_repo,
        FakeDriverFactory(),
        project_repo=FakeProjectRepository(None),
    )

    driver = asyncio.run(manager.get_driver("user-a"))

    assert driver is None
    assert workspace_repo.global_lookup_called is False


def test_legacy_workspace_id_owned_by_another_project_is_rejected():
    class ForeignWorkspaceRepository(FakeWorkspaceRepository):
        def get_workspace_by_project_id(self, project_id, user_id):
            return None

    foreign_workspace = {
        "id": "workspace-project-b",
        "project_id": "project-b",
        "type": "local",
        "path": "/tmp/project-b",
    }
    workspace_repo = ForeignWorkspaceRepository(foreign_workspace)
    factory = FakeDriverFactory()
    project_repo = FakeProjectRepository({
        "id": "project-a",
        "workspace_id": "workspace-project-b",
        "workspace_path": "",
        "ssh_host": "",
    })
    manager = WorkspaceManagerService(workspace_repo, factory, project_repo=project_repo)

    driver = asyncio.run(manager.get_driver_for_project("user-a", "project-a"))

    assert driver is None
    assert factory.created_for == []
