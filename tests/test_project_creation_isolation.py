from app.services.project.project_service import ProjectService


class FakeProjectRepository:
    def __init__(self):
        self.created = None

    def list_projects(self, user_id):
        return []

    def create_project(self, **kwargs):
        self.created = kwargs
        return True

    def set_active_project(self, project_id, user_id):
        return True

    def record_changelog(self, *args, **kwargs):
        return True


def test_new_project_ignores_workspace_ssh_and_github_bindings():
    repo = FakeProjectRepository()
    service = ProjectService(repo)

    result = service.create_project(
        "user-a",
        {
            "name": "Isolated Project",
            "workspace_id": "workspace-from-another-project",
            "workspace_path": "/tmp/another-project",
            "ssh_host": "production.example.com",
            "ssh_username": "deploy",
            "ssh_key_id": "shared-key",
            "github_remote_url": "git@github.com:someone/another-project.git",
            "github_pat_enc": "encrypted-token",
            "project_context": "inherited context",
            "rules_of_engagement": "inherited rules",
            "activate": True,
        },
    )

    assert result["status"] == "created"
    assert repo.created["workspace_id"] == ""
    assert repo.created["workspace_path"] == ""
    assert repo.created["ssh_host"] == ""
    assert repo.created["ssh_username"] == ""
    assert repo.created["ssh_key_id"] == ""
    assert repo.created["github_remote_url"] == ""
    assert repo.created["github_pat_enc"] == ""
    assert repo.created["project_context"] == ""
    assert repo.created["rules_of_engagement"] == ""
