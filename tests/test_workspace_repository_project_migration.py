from app.repository.db_connection import DatabaseConnectionManager
from app.repository.project_db_repository import ProjectDBRepository
from app.repository.workspace_db_repository import WorkspaceDBRepository


def test_shared_legacy_workspace_is_split_into_project_owned_records(tmp_path):
    db = DatabaseConnectionManager(str(tmp_path / "runtime.db"))
    ProjectDBRepository(db)
    conn = db.get_connection()
    conn.execute(
        """
        INSERT INTO projects (id, user_id, name, workspace_id, is_active)
        VALUES ('project-a', 'user-a', 'Project A', 'legacy-workspace', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO projects (id, user_id, name, workspace_id, is_active)
        VALUES ('project-b', 'user-a', 'Project B', 'legacy-workspace', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO workspaces
            (id, name, type, host, port, username, path, is_active, user_id)
        VALUES
            ('legacy-workspace', 'Shared Workspace', 'local', NULL, 22, NULL, '/srv/shared', 1, 'user-a')
        """
    )
    conn.commit()

    repo = WorkspaceDBRepository(db)
    workspace_a = repo.get_workspace_by_project_id("project-a", "user-a")
    workspace_b = repo.get_workspace_by_project_id("project-b", "user-a")

    assert workspace_a is not None
    assert workspace_b is not None
    assert workspace_a["id"] != workspace_b["id"]
    assert workspace_a["project_id"] == "project-a"
    assert workspace_b["project_id"] == "project-b"
    assert workspace_a["path"] == "/srv/shared"
    assert workspace_b["path"] == "/srv/shared"

    project_rows = conn.execute(
        "SELECT id, workspace_id FROM projects WHERE user_id='user-a' ORDER BY id"
    ).fetchall()
    assert len({row["workspace_id"] for row in project_rows}) == 2


def test_legacy_project_ssh_fields_are_migrated_to_its_workspace(tmp_path):
    db = DatabaseConnectionManager(str(tmp_path / "runtime.db"))
    ProjectDBRepository(db)
    conn = db.get_connection()
    conn.execute(
        """
        INSERT INTO ssh_keys (id, name, private_key_enc, user_id)
        VALUES ('key-1', 'Deploy key', 'encrypted-private-key', 'user-b')
        """
    )
    conn.execute(
        """
        INSERT INTO projects
            (id, user_id, name, workspace_path, ssh_host, ssh_port, ssh_username, ssh_key_id, is_active)
        VALUES
            ('project-ssh', 'user-b', 'SSH Project', '/var/www/app', 'server.example.com', 2222, 'deploy', 'key-1', 1)
        """
    )
    conn.commit()

    repo = WorkspaceDBRepository(db)
    workspace = repo.get_workspace_by_project_id("project-ssh", "user-b")

    assert workspace is not None
    assert workspace["type"] == "ssh"
    assert workspace["host"] == "server.example.com"
    assert workspace["port"] == 2222
    assert workspace["username"] == "deploy"
    assert workspace["path"] == "/var/www/app"
    assert workspace["key_id"] == "key-1"
