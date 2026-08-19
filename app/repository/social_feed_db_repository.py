"""
Isolated Repository for Studio Plan Build-in-Public Social Posts and Feedback Loop.
"""
import logging
from typing import Optional, Dict, Any, List
from app.repository.db_connection import DatabaseConnectionManager

logger = logging.getLogger("runtimeforce.repository.social")

SCHEMA = """
CREATE TABLE IF NOT EXISTS social_post_drafts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    changelog_entry TEXT NOT NULL,
    post_content TEXT NOT NULL,
    platform TEXT DEFAULT 'x.com',
    status TEXT DEFAULT 'draft',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS social_feedback_items (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    source_platform TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    structured_task TEXT,
    status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_social_drafts_proj ON social_post_drafts(project_id);
CREATE INDEX IF NOT EXISTS idx_social_feedback_proj ON social_feedback_items(project_id);
"""

class SocialFeedDBRepository:
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db = db_manager
        self.init_schema()

    def init_schema(self):
        conn = self.db.get_connection()
        conn.executescript(SCHEMA)
        conn.commit()

    def save_draft(self, draft_id: str, project_id: str, user_id: str, changelog: str, content: str, platform: str = "x.com") -> bool:
        try:
            conn = self.db.get_connection()
            conn.execute(
                "INSERT INTO social_post_drafts (id, project_id, user_id, changelog_entry, post_content, platform) VALUES (?, ?, ?, ?, ?, ?)",
                (draft_id, project_id, user_id, changelog, content, platform)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save social draft {draft_id}: {e}")
            return False

    def get_drafts(self, project_id: str, user_id: str) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM social_post_drafts WHERE project_id=? AND user_id=? ORDER BY created_at DESC", (project_id, user_id))
        return [dict(r) for r in cur.fetchall()]

    def update_draft_status(self, draft_id: str, user_id: str, status: str) -> bool:
        conn = self.db.get_connection()
        conn.execute("UPDATE social_post_drafts SET status=? WHERE id=? AND user_id=?", (status, draft_id, user_id))
        conn.commit()
        return True

    def save_feedback(self, feedback_id: str, project_id: str, user_id: str, platform: str, raw_text: str, task: str) -> bool:
        try:
            conn = self.db.get_connection()
            conn.execute(
                "INSERT INTO social_feedback_items (id, project_id, user_id, source_platform, raw_text, structured_task) VALUES (?, ?, ?, ?, ?, ?)",
                (feedback_id, project_id, user_id, platform, raw_text, task)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save feedback item: {e}")
            return False

    def get_feedback_items(self, project_id: str, user_id: str) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM social_feedback_items WHERE project_id=? AND user_id=? ORDER BY created_at DESC", (project_id, user_id))
        return [dict(r) for r in cur.fetchall()]
