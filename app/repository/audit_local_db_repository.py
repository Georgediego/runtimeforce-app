"""
Isolated Repository for Local Audit Events Persistence.
"""
import json
import logging
from typing import Optional, Dict, Any, List
from app.repository.db_connection import DatabaseConnectionManager
from app.core.interfaces.audit_logger_interface import IAuditLogger

logger = logging.getLogger("runtimeforce.repository.audit")

SCHEMA = """
CREATE TABLE IF NOT EXISTS local_audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,
    payload_json TEXT,
    user_id TEXT DEFAULT 'anonymous'
);
CREATE INDEX IF NOT EXISTS idx_audit_user ON local_audit_events(user_id);
"""

class AuditLocalDBRepository(IAuditLogger):
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db = db_manager
        self.init_schema()

    def init_schema(self):
        conn = self.db.get_connection()
        conn.executescript(SCHEMA)
        conn.commit()

    def log_event(self, event_type: str, payload: Dict[str, Any], user_id: str = "anonymous") -> bool:
        try:
            conn = self.db.get_connection()
            conn.execute(
                "INSERT INTO local_audit_events (event_type, payload_json, user_id) VALUES (?, ?, ?)",
                (event_type, json.dumps(payload, ensure_ascii=False), user_id)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to log audit event '{event_type}': {e}")
            return False

    def query_logs(self, user_id: str, limit: int = 50, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        if event_type:
            cur.execute(
                "SELECT * FROM local_audit_events WHERE user_id=? AND event_type=? ORDER BY id DESC LIMIT ?",
                (user_id, event_type, limit)
            )
        else:
            cur.execute(
                "SELECT * FROM local_audit_events WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit)
            )
        rows = cur.fetchall()
        result = []
        for r in rows:
            item = dict(r)
            if item.get("payload_json"):
                try:
                    item["payload"] = json.loads(item["payload_json"])
                except Exception:
                    item["payload"] = {}
            result.append(item)
        return result
