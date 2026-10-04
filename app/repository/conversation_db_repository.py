"""
Isolated Repository for Session, Message, Trace, Tools & Terminal Persistence with Clean Truncation.
"""
import logging
from typing import List, Dict, Any, Optional
from app.repository.db_connection import DatabaseConnectionManager

logger = logging.getLogger("runtimeforce.repository.conversation")

SCHEMA = """
CREATE TABLE IF NOT EXISTS session_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    badge TEXT NOT NULL,
    text TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS session_tools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    status TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS session_terminal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_traces_session ON session_traces(session_id);
CREATE INDEX IF NOT EXISTS idx_tools_session ON session_tools(session_id);
CREATE INDEX IF NOT EXISTS idx_terminal_session ON session_terminal(session_id);
"""

class ConversationDBRepository:
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db = db_manager
        self.init_schema()

    def init_schema(self):
        conn = self.db.get_connection()
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN project_id TEXT DEFAULT ''")
            conn.commit()
        except Exception:
            pass
        conn.executescript(SCHEMA)
        conn.commit()

    def claim_legacy_anonymous(self, user_id: str):
        if not user_id or user_id == "anonymous":
            return
        try:
            conn = self.db.get_connection()
            conn.execute("UPDATE sessions SET user_id=? WHERE user_id='anonymous' OR user_id='default_user'", (user_id,))
            conn.commit()
        except Exception as e:
            logger.debug(f"Session claim skipped: {e}")

    def get_session_project(self, session_id: str) -> str:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT project_id FROM sessions WHERE id=?", (session_id,))
        row = cur.fetchone()
        return row["project_id"] if row and row["project_id"] else ""

    def ensure_session_exists(
        self, session_id: str, user_id: str = "anonymous", title: str = "New Chat", project_id: str = ""
    ):
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM sessions WHERE id=?", (session_id,))
        if not cur.fetchone():
            try:
                conn.execute(
                    "INSERT INTO sessions (id, title, user_id, project_id) VALUES (?, ?, ?, ?)",
                    (session_id, title, user_id, project_id)
                )
                conn.commit()
            except Exception as e:
                logger.debug(f"Session collision ignored: {e}")

    def get_all_sessions(self, user_id: str, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        self.claim_legacy_anonymous(user_id)
        conn = self.db.get_connection()
        cur = conn.cursor()
        if project_id and project_id.strip():
            cur.execute(
                """
                SELECT s.*, p.name as project_name
                FROM sessions s
                LEFT JOIN projects p ON s.project_id = p.id
                WHERE (s.user_id = ? OR s.user_id = 'anonymous' OR s.user_id = 'default_user') AND s.project_id = ?
                ORDER BY s.updated_at DESC
                """,
                (user_id, project_id)
            )
        else:
            cur.execute(
                """
                SELECT s.*, p.name as project_name
                FROM sessions s
                LEFT JOIN projects p ON s.project_id = p.id
                WHERE s.user_id = ? OR s.user_id = 'anonymous' OR s.user_id = 'default_user'
                ORDER BY s.updated_at DESC
                """,
                (user_id,)
            )
        return [dict(r) for r in cur.fetchall()]

    def create_session(self, session_id: str, title: str, user_id: str, project_id: str = "") -> bool:
        try:
            conn = self.db.get_connection()
            conn.execute(
                """
                INSERT INTO sessions (id, title, user_id, project_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    project_id=CASE WHEN excluded.project_id != '' THEN excluded.project_id ELSE sessions.project_id END,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (session_id, title, user_id, project_id)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to create session {session_id}: {e}")
            return False

    def get_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, role, content FROM messages
            WHERE session_id=? AND role IN ('user', 'assistant')
            ORDER BY id ASC
            """,
            (session_id,)
        )
        return [{"id": r["id"], "role": r["role"], "content": r["content"]} for r in cur.fetchall()]

    def append_message(self, session_id: str, role: str, content: str, user_id: str = "anonymous", project_id: str = ""):
        self.ensure_session_exists(session_id, user_id=user_id, project_id=project_id)
        conn = self.db.get_connection()
        conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content)
        )
        conn.execute(
            "UPDATE sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (session_id,)
        )
        conn.commit()

    def get_message_by_id(self, message_id: int) -> Optional[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM messages WHERE id=?", (message_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def update_message(self, message_id: int, new_content: str) -> bool:
        conn = self.db.get_connection()
        cur = conn.execute(
            "UPDATE messages SET content=? WHERE id=?",
            (new_content, message_id)
        )
        conn.commit()
        return cur.rowcount > 0

    def truncate_from_message(self, message_id: int) -> Optional[str]:
        """Delete target message and all subsequent messages to allow fresh resend without duplicates."""
        msg = self.get_message_by_id(message_id)
        if not msg:
            return None
        session_id = msg["session_id"]
        conn = self.db.get_connection()
        conn.execute(
            "DELETE FROM messages WHERE session_id=? AND id >= ?",
            (session_id, message_id)
        )
        conn.commit()
        return session_id

    def truncate_after_message(self, message_id: int) -> bool:
        msg = self.get_message_by_id(message_id)
        if not msg:
            return False
        session_id = msg["session_id"]
        conn = self.db.get_connection()
        conn.execute(
            "DELETE FROM messages WHERE session_id=? AND id > ?",
            (session_id, message_id)
        )
        conn.commit()
        return True

    def delete_message_and_subsequent(self, message_id: int) -> bool:
        return bool(self.truncate_from_message(message_id))

    def append_trace(self, session_id: str, badge: str, text: str):
        self.ensure_session_exists(session_id)
        try:
            conn = self.db.get_connection()
            conn.execute(
                "INSERT INTO session_traces (session_id, badge, text) VALUES (?, ?, ?)",
                (session_id, badge, text)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to append trace: {e}")

    def get_session_traces(self, session_id: str) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, badge, text, timestamp FROM session_traces WHERE session_id=? ORDER BY id ASC", (session_id,))
        return [dict(r) for r in cur.fetchall()]

    def save_tool_execution(self, session_id: str, tool_id: str, tool_name: str, status: str):
        self.ensure_session_exists(session_id)
        try:
            conn = self.db.get_connection()
            conn.execute(
                """
                INSERT INTO session_tools (session_id, tool_id, tool_name, status)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, tool_id, tool_name, status)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to save tool execution: {e}")

    def get_session_tools(self, session_id: str) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, tool_id, tool_name, status, timestamp FROM session_tools WHERE session_id=? ORDER BY id ASC", (session_id,))
        return [dict(r) for r in cur.fetchall()]

    def append_terminal(self, session_id: str, entry_type: str, content: str):
        self.ensure_session_exists(session_id)
        try:
            conn = self.db.get_connection()
            conn.execute(
                "INSERT INTO session_terminal (session_id, entry_type, content) VALUES (?, ?, ?)",
                (session_id, entry_type, content)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to save terminal entry: {e}")

    def get_session_terminal(self, session_id: str) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, entry_type, content, timestamp FROM session_terminal WHERE session_id=? ORDER BY id ASC", (session_id,))
        return [dict(r) for r in cur.fetchall()]

    def delete_session(self, session_id: str) -> bool:
        conn = self.db.get_connection()
        conn.execute("DELETE FROM session_traces WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM session_tools WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM session_terminal WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        conn.commit()
        return True
