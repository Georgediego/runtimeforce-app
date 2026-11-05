"""
Database Repository for Studio Plan Projects with Workspace & Git Binding.
"""
import sqlite3
import logging
from typing import List, Dict, Any, Optional
from app.repository.db_connection import DatabaseConnectionManager

logger = logging.getLogger("runtimeforce.repository.project")

PROJECTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    workspace_id TEXT DEFAULT '',
    project_context TEXT,
    rules_of_engagement TEXT,
    workspace_path TEXT,
    ssh_host TEXT,
    ssh_port INTEGER DEFAULT 22,
    ssh_username TEXT,
    ssh_key_id TEXT,
    github_remote_url TEXT DEFAULT '',
    github_pat_enc TEXT DEFAULT '',
    x_api_key_enc TEXT DEFAULT '',
    reddit_client_id_enc TEXT DEFAULT '',
    reddit_client_secret_enc TEXT DEFAULT '',
    git_mode TEXT DEFAULT 'manual',
    git_branch_main TEXT DEFAULT 'main',
    git_branch_dev TEXT DEFAULT 'dev',
    version_scheme TEXT DEFAULT 'semver',
    prerelease_tag TEXT DEFAULT '',
    current_version TEXT DEFAULT 'v1.0.0',
    is_active INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_changelogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    version TEXT NOT NULL,
    changelog_entry TEXT NOT NULL,
    git_commit_hash TEXT,
    target_branch TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_changelogs_project ON project_changelogs(project_id);
"""

class ProjectDBRepository:
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db = db_manager
        self.init_schema()

    def init_schema(self):
        conn = self.db.get_connection()
        conn.executescript(PROJECTS_SCHEMA)
        
        migrations = [
            ("workspace_id", "TEXT DEFAULT ''"),
            ("github_remote_url", "TEXT DEFAULT ''"),
            ("github_pat_enc", "TEXT DEFAULT ''"),
            ("x_api_key_enc", "TEXT DEFAULT ''"),
            ("reddit_client_id_enc", "TEXT DEFAULT ''"),
            ("reddit_client_secret_enc", "TEXT DEFAULT ''"),
            ("workspace_path", "TEXT DEFAULT ''"),
            ("ssh_host", "TEXT DEFAULT ''"),
            ("ssh_port", "INTEGER DEFAULT 22"),
            ("ssh_username", "TEXT DEFAULT ''"),
            ("ssh_key_id", "TEXT DEFAULT ''"),
            ("project_context", "TEXT DEFAULT ''"),
            ("rules_of_engagement", "TEXT DEFAULT ''"),
            ("git_mode", "TEXT DEFAULT 'manual'"),
            ("git_branch_main", "TEXT DEFAULT 'main'"),
            ("git_branch_dev", "TEXT DEFAULT 'dev'"),
            ("version_scheme", "TEXT DEFAULT 'semver'"),
            ("prerelease_tag", "TEXT DEFAULT ''"),
            ("current_version", "TEXT DEFAULT 'v1.0.0'"),
            ("is_active", "INTEGER DEFAULT 0"),
        ]
        
        for col_name, col_def in migrations:
            try:
                conn.execute(f"ALTER TABLE projects ADD COLUMN {col_name} {col_def}")
            except Exception:
                pass

        conn.commit()

    def list_projects(self, user_id: str) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM projects WHERE user_id=? ORDER BY is_active DESC, updated_at DESC", (user_id,))
        return [dict(r) for r in cur.fetchall()]

    def get_active_project(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM projects WHERE user_id=? AND is_active=1 LIMIT 1", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_project(self, project_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM projects WHERE id=? AND user_id=?", (project_id, user_id))
        row = cur.fetchone()
        return dict(row) if row else None

    def create_project(self, project_id: str, user_id: str, **kwargs) -> bool:
        try:
            conn = self.db.get_connection()
            conn.execute(
                """
                INSERT INTO projects
                    (id, user_id, name, workspace_id, project_context, rules_of_engagement,
                     workspace_path, ssh_host, ssh_port, ssh_username, ssh_key_id,
                     github_remote_url, github_pat_enc, x_api_key_enc, reddit_client_id_enc, reddit_client_secret_enc,
                     git_mode, git_branch_main, git_branch_dev, version_scheme,
                     prerelease_tag, current_version, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id, user_id, kwargs.get("name"),
                    kwargs.get("workspace_id", ""),
                    kwargs.get("project_context", ""),
                    kwargs.get("rules_of_engagement", ""),
                    kwargs.get("workspace_path", ""),
                    kwargs.get("ssh_host", ""),
                    kwargs.get("ssh_port", 22),
                    kwargs.get("ssh_username", ""),
                    kwargs.get("ssh_key_id", ""),
                    kwargs.get("github_remote_url", ""),
                    kwargs.get("github_pat_enc", ""),
                    kwargs.get("x_api_key_enc", ""),
                    kwargs.get("reddit_client_id_enc", ""),
                    kwargs.get("reddit_client_secret_enc", ""),
                    kwargs.get("git_mode", "manual"),
                    kwargs.get("git_branch_main", "main"),
                    kwargs.get("git_branch_dev", "dev"),
                    kwargs.get("version_scheme", "semver"),
                    kwargs.get("prerelease_tag", ""),
                    kwargs.get("current_version", "v1.0.0"),
                    1 if kwargs.get("is_active") else 0
                )
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to create project {project_id}: {e}")
            return False

    def set_active_project(self, project_id: str, user_id: str) -> bool:
        conn = self.db.get_connection()
        conn.execute("UPDATE projects SET is_active=0 WHERE user_id=?", (user_id,))
        conn.execute("UPDATE projects SET is_active=1, updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", (project_id, user_id))
        conn.commit()
        return True

    def update_project(self, project_id: str, user_id: str, **kwargs) -> bool:
        conn = self.db.get_connection()
        allowed = (
            "name", "workspace_id", "project_context", "rules_of_engagement", "workspace_path",
            "ssh_host", "ssh_port", "ssh_username", "ssh_key_id",
            "github_remote_url", "github_pat_enc", "x_api_key_enc", "reddit_client_id_enc", "reddit_client_secret_enc",
            "git_mode", "git_branch_main", "git_branch_dev", "version_scheme", "prerelease_tag",
            "current_version", "is_active"
        )
        fields = []
        params = []
        for k, v in kwargs.items():
            if k in allowed:
                fields.append(f"{k}=?")
                params.append(v)
        if not fields:
            return False
        fields.append("updated_at=CURRENT_TIMESTAMP")
        params.extend([project_id, user_id])
        conn.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id=? AND user_id=?", params)
        conn.commit()
        return True

    def delete_project(self, project_id: str, user_id: str) -> bool:
        """Delete all database data owned by a project without touching user files or global settings."""
        try:
            with self.db.transaction() as conn:
                project = conn.execute(
                    "SELECT is_active FROM projects WHERE id=? AND user_id=?",
                    (project_id, user_id)
                ).fetchone()
                if not project:
                    return False

                # Capture this project's sessions before deleting them and all session-scoped data.
                session_rows = conn.execute(
                    "SELECT id FROM sessions WHERE project_id=? AND user_id=?",
                    (project_id, user_id)
                ).fetchall()
                session_ids = [row["id"] for row in session_rows]

                if session_ids:
                    placeholders = ",".join("?" for _ in session_ids)
                    params = tuple(session_ids)
                    for table in ("session_traces", "session_tools", "session_terminal", "messages"):
                        conn.execute(
                            f"DELETE FROM {table} WHERE session_id IN ({placeholders})",
                            params
                        )
                    conn.execute(
                        f"DELETE FROM model_telemetry WHERE user_id=? AND session_id IN ({placeholders})",
                        (user_id, *session_ids)
                    )
                    conn.execute(
                        f"DELETE FROM sessions WHERE user_id=? AND id IN ({placeholders})",
                        (user_id, *session_ids)
                    )

                # Delete project-scoped decision and version history.
                conn.execute(
                    "DELETE FROM decision_memory WHERE project_id=? AND user_id=?",
                    (project_id, user_id)
                )
                conn.execute(
                    "DELETE FROM project_version_logs WHERE project_id=? AND user_id=?",
                    (project_id, user_id)
                )
                conn.execute(
                    "DELETE FROM project_changelogs WHERE project_id=?",
                    (project_id,)
                )

                # Remove project memory, embeddings, and graph relationships.
                node_rows = conn.execute(
                    "SELECT id FROM graph_nodes WHERE project_id=? AND user_id=?",
                    (project_id, user_id)
                ).fetchall()
                node_ids = [row["id"] for row in node_rows]
                if node_ids:
                    placeholders = ",".join("?" for _ in node_ids)
                    params = tuple(node_ids)
                    conn.execute(
                        f"DELETE FROM graph_edges WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})",
                        (*node_ids, *node_ids)
                    )
                    conn.execute(
                        f"DELETE FROM node_embeddings WHERE node_id IN ({placeholders})",
                        params
                    )
                    conn.execute(
                        f"DELETE FROM graph_nodes WHERE user_id=? AND id IN ({placeholders})",
                        (user_id, *node_ids)
                    )

                # Delete project-owned workspace records and credentials stored on those rows.
                # This is database-only: never remove local directories, files, or Git repositories.
                conn.execute(
                    "DELETE FROM workspaces WHERE project_id=? AND user_id=?",
                    (project_id, user_id)
                )

                was_active = bool(project["is_active"])
                conn.execute(
                    "DELETE FROM projects WHERE id=? AND user_id=?",
                    (project_id, user_id)
                )

                # If the active project was deleted, activate the user's most recently updated remaining project.
                if was_active:
                    conn.execute("UPDATE projects SET is_active=0 WHERE user_id=?", (user_id,))
                    next_project = conn.execute(
                        "SELECT id FROM projects WHERE user_id=? ORDER BY updated_at DESC, created_at DESC LIMIT 1",
                        (user_id,)
                    ).fetchone()
                    if next_project:
                        conn.execute(
                            "UPDATE projects SET is_active=1 WHERE id=? AND user_id=?",
                            (next_project["id"], user_id)
                        )

            return True
        except Exception as e:
            logger.error(f"Failed to delete project {project_id} for user {user_id}: {e}")
            raise

    def record_changelog(self, project_id: str, version: str, entry: str, commit_hash: Optional[str] = None, target_branch: Optional[str] = None) -> bool:
        conn = self.db.get_connection()
        conn.execute(
            "INSERT INTO project_changelogs (project_id, version, changelog_entry, git_commit_hash, target_branch) VALUES (?, ?, ?, ?, ?)",
            (project_id, version, entry, commit_hash, target_branch)
        )
        conn.execute("UPDATE projects SET current_version=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (version, project_id))
        conn.commit()
        return True

    def get_changelogs(self, project_id: str) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM project_changelogs WHERE project_id=? ORDER BY id DESC", (project_id,))
        return [dict(r) for r in cur.fetchall()]
