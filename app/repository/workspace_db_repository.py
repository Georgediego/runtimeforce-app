import sqlcipher3 as sqlite3
import logging
import uuid
from typing import List, Dict, Any, Optional
from app.repository.db_connection import DatabaseConnectionManager

logger = logging.getLogger("runtimeforce.repository.workspace")

class WorkspaceDBRepository:
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db = db_manager
        self.init_schema()

    def init_schema(self):
        conn = self.db.get_connection()
        try:
            conn.execute("ALTER TABLE workspaces ADD COLUMN project_id TEXT DEFAULT ''")
            conn.commit()
        except Exception:
            pass

        try:
            conn.execute("""
                DELETE FROM workspaces WHERE rowid NOT IN (
                    SELECT MIN(rowid) FROM workspaces 
                    WHERE project_id IS NOT NULL AND project_id != ''
                    GROUP BY user_id, project_id, path, host, username
                ) AND project_id != ''
            """)
            conn.commit()
        except Exception as e:
            logger.debug(f"Workspace deduplication migration skipped: {e}")

        self._migrate_project_bindings(conn)

    def _migrate_project_bindings(self, conn):
        """Give every legacy project its own workspace database binding.

        Existing physical paths and SSH hosts are preserved; the migration
        duplicates only the per-project workspace record. New projects remain
        disconnected until the user configures them explicitly.
        """
        try:
            projects = conn.execute(
                "SELECT * FROM projects ORDER BY is_active DESC, updated_at DESC, created_at DESC"
            ).fetchall()
        except sqlite3.OperationalError:
            return

        project_counts = {}
        for row in projects:
            project_counts[row["user_id"]] = project_counts.get(row["user_id"], 0) + 1

        for row in projects:
            project = dict(row)
            project_id = str(project.get("id") or "")
            user_id = str(project.get("user_id") or "")
            if not project_id or not user_id:
                continue

            own_workspace = conn.execute(
                """
                SELECT * FROM workspaces
                WHERE user_id=? AND project_id=?
                ORDER BY is_active DESC, created_at DESC
                LIMIT 1
                """,
                (user_id, project_id),
            ).fetchone()
            if own_workspace:
                if project.get("workspace_id") != own_workspace["id"]:
                    conn.execute(
                        "UPDATE projects SET workspace_id=? WHERE id=? AND user_id=?",
                        (own_workspace["id"], project_id, user_id),
                    )
                continue

            legacy_workspace = None
            legacy_workspace_id = str(project.get("workspace_id") or "").strip()
            if legacy_workspace_id:
                legacy_workspace = conn.execute(
                    "SELECT * FROM workspaces WHERE id=? AND user_id=?",
                    (legacy_workspace_id, user_id),
                ).fetchone()

            if not legacy_workspace and project_counts.get(user_id) == 1:
                unbound = conn.execute(
                    """
                    SELECT * FROM workspaces
                    WHERE user_id=? AND (project_id IS NULL OR project_id='')
                    ORDER BY is_active DESC, created_at DESC
                    """,
                    (user_id,),
                ).fetchall()
                if len(unbound) == 1:
                    legacy_workspace = unbound[0]

            new_workspace_id = ""
            if legacy_workspace:
                source = dict(legacy_workspace)
                source_project_id = str(source.get("project_id") or "").strip()
                if not source_project_id:
                    new_workspace_id = source["id"]
                    conn.execute(
                        "UPDATE workspaces SET project_id=? WHERE id=? AND user_id=?",
                        (project_id, new_workspace_id, user_id),
                    )
                elif source_project_id == project_id:
                    new_workspace_id = source["id"]
                else:
                    new_workspace_id = str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO workspaces
                            (id, name, type, host, port, username, path, auth_type,
                             password_enc, key_id, is_active, user_id, project_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            new_workspace_id,
                            source.get("name"),
                            source.get("type"),
                            source.get("host"),
                            source.get("port", 22),
                            source.get("username"),
                            source.get("path"),
                            source.get("auth_type"),
                            source.get("password_enc"),
                            source.get("key_id"),
                            source.get("is_active", 0),
                            user_id,
                            project_id,
                        ),
                    )
            else:
                legacy_path = str(project.get("workspace_path") or "").strip()
                legacy_host = str(project.get("ssh_host") or "").strip()
                if legacy_path or legacy_host:
                    new_workspace_id = str(uuid.uuid4())
                    workspace_type = "ssh" if legacy_host else "local"
                    key_id = project.get("ssh_key_id") or None
                    conn.execute(
                        """
                        INSERT INTO workspaces
                            (id, name, type, host, port, username, path, auth_type,
                             password_enc, key_id, is_active, user_id, project_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            new_workspace_id,
                            "SSH Workspace" if legacy_host else "Local Workspace",
                            workspace_type,
                            legacy_host or None,
                            project.get("ssh_port") or 22,
                            project.get("ssh_username") or None,
                            legacy_path or None,
                            "key" if key_id else None,
                            None,
                            key_id,
                            1 if project.get("is_active") else 0,
                            user_id,
                            project_id,
                        ),
                    )

            if new_workspace_id:
                conn.execute(
                    "UPDATE projects SET workspace_id=? WHERE id=? AND user_id=?",
                    (new_workspace_id, project_id, user_id),
                )

        conn.commit()

    def claim_legacy_anonymous(self, user_id: str):
        if not user_id or user_id == "anonymous":
            return
        conn = self.db.get_connection()
        cur = conn.cursor()
        tables = [
            "workspaces", "sessions", "provider_keys",
            "ssh_keys", "command_audit", "model_telemetry", "model_scores"
        ]
        for table in tables:
            try:
                cur.execute(f"UPDATE {table} SET user_id = ? WHERE user_id = 'anonymous'", (user_id,))
            except Exception as e:
                logger.debug(f"Claim legacy table {table} skipped: {e}")
        conn.commit()

    def get_all_workspaces(self, user_id: str, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        self.claim_legacy_anonymous(user_id)
        conn = self.db.get_connection()
        cur = conn.cursor()
        
        target_pid = (project_id or "").strip()
        if target_pid:
            cur.execute(
                """
                SELECT * FROM workspaces 
                WHERE user_id = ? AND project_id = ?
                ORDER BY is_active DESC, created_at DESC
                """,
                (user_id, target_pid)
            )
        else:
            return []

        rows = [dict(r) for r in cur.fetchall()]
        seen = set()
        deduped = []
        for r in rows:
            key = (r.get("project_id", ""), r.get("path", ""), r.get("host", ""), r.get("username", ""))
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped

    def get_workspace_by_id(self, wid: str, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM workspaces WHERE id=? AND user_id=?", (wid, user_id))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_workspace_by_project_id(self, project_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        if not project_id:
            return None
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM workspaces WHERE project_id=? AND user_id=? ORDER BY is_active DESC LIMIT 1", (project_id, user_id))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_active_workspace(self, user_id: str, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        self.claim_legacy_anonymous(user_id)
        conn = self.db.get_connection()
        cur = conn.cursor()
        if project_id and project_id.strip():
            cur.execute("SELECT * FROM workspaces WHERE is_active=1 AND user_id=? AND project_id=? LIMIT 1", (user_id, project_id.strip()))
        else:
            cur.execute("SELECT * FROM workspaces WHERE is_active=1 AND user_id=? LIMIT 1", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def create_workspace(self, workspace_id: str, user_id: str, **kwargs) -> bool:
        try:
            conn = self.db.get_connection()
            cur = conn.cursor()
            proj_id = kwargs.get("project_id", "").strip()
            path = kwargs.get("path", "")
            host = kwargs.get("host", "")
            username = kwargs.get("username", "")

            if not proj_id:
                logger.warning(f"Cannot create workspace without valid project_id for user {user_id}")
                return False

            cur.execute(
                """
                SELECT id FROM workspaces 
                WHERE user_id=? AND project_id=? AND path=? AND host=? AND username=?
                """,
                (user_id, proj_id, path, host, username)
            )
            existing = cur.fetchone()
            if existing:
                if kwargs.get("is_active"):
                    conn.execute("UPDATE workspaces SET is_active=0 WHERE user_id=? AND project_id=?", (user_id, proj_id))
                conn.execute(
                    "UPDATE workspaces SET is_active=?, name=? WHERE id=?",
                    (1 if kwargs.get("is_active") else 0, kwargs.get("name"), existing["id"])
                )
                conn.commit()
                return True

            if kwargs.get("is_active"):
                conn.execute("UPDATE workspaces SET is_active=0 WHERE user_id=? AND project_id=?", (user_id, proj_id))

            conn.execute(
                """
                INSERT INTO workspaces
                    (id, name, type, host, port, username, path, auth_type,
                     password_enc, key_id, is_active, user_id, project_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workspace_id, kwargs.get("name"), kwargs.get("type"),
                    kwargs.get("host"), kwargs.get("port", 22),
                    kwargs.get("username"), kwargs.get("path"),
                    kwargs.get("auth_type"), kwargs.get("password_enc"),
                    kwargs.get("key_id"), 1 if kwargs.get("is_active") else 0, user_id,
                    proj_id
                )
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to create workspace: {e}")
            return False

    def bind_workspace_to_project(self, wid: str, project_id: str, user_id: str) -> bool:
        conn = self.db.get_connection()
        conn.execute("UPDATE workspaces SET project_id=? WHERE id=? AND user_id=?", (project_id, wid, user_id))
        conn.commit()
        return True

    def set_active_workspace(self, wid: str, user_id: str) -> bool:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT project_id FROM workspaces WHERE id=? AND user_id=?", (wid, user_id))
        row = cur.fetchone()
        proj_id = row["project_id"] if row else ""

        if proj_id:
            conn.execute("UPDATE workspaces SET is_active=0 WHERE user_id=? AND project_id=?", (user_id, proj_id))
        else:
            conn.execute("UPDATE workspaces SET is_active=0 WHERE user_id=?", (user_id,))

        conn.execute("UPDATE workspaces SET is_active=1 WHERE id=? AND user_id=?", (wid, user_id))
        conn.commit()
        return True

    def delete_workspace(self, wid: str, user_id: str) -> bool:
        conn = self.db.get_connection()
        conn.execute("DELETE FROM workspaces WHERE id=? AND user_id=?", (wid, user_id))
        conn.commit()
        return True
