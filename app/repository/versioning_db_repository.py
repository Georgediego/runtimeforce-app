"""
Isolated Repository for Project SemVer/CalVer Versioning and Changelogs.
"""
import logging
from typing import Optional, Dict, Any, List
from app.repository.db_connection import DatabaseConnectionManager

logger = logging.getLogger("runtimeforce.repository.versioning")

SCHEMA = """
CREATE TABLE IF NOT EXISTS project_version_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    version TEXT NOT NULL,
    changelog_entry TEXT NOT NULL,
    commit_hash TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_version_project ON project_version_logs(project_id);
"""

class VersioningDBRepository:
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db = db_manager
        self.init_schema()

    def init_schema(self):
        conn = self.db.get_connection()
        conn.executescript(SCHEMA)
        conn.commit()

    def record_version(self, project_id: str, user_id: str, version: str, changelog: str, commit_hash: Optional[str] = None) -> bool:
        try:
            conn = self.db.get_connection()
            conn.execute(
                "INSERT INTO project_version_logs (project_id, user_id, version, changelog_entry, commit_hash) VALUES (?, ?, ?, ?, ?)",
                (project_id, user_id, version, changelog, commit_hash)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to record version log for project {project_id}: {e}")
            return False

    def get_version_history(self, project_id: str, user_id: str) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM project_version_logs WHERE project_id=? AND user_id=? ORDER BY id DESC", (project_id, user_id))
        return [dict(r) for r in cur.fetchall()]
