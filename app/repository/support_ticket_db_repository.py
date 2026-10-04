"""
Isolated Repository for Local Support Ticket & Diagnostic Intake Persistence.
"""
import json
import logging
import uuid
from typing import Optional, Dict, Any, List
from app.repository.db_connection import DatabaseConnectionManager
from app.core.interfaces.support_ticket_service_interface import ISupportTicketService

logger = logging.getLogger("runtimeforce.repository.support")

SCHEMA = """
CREATE TABLE IF NOT EXISTS support_tickets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    diagnostics_json TEXT,
    status TEXT DEFAULT 'open',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tickets_user ON support_tickets(user_id);
"""

class SupportTicketDBRepository(ISupportTicketService):
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db = db_manager
        self.init_schema()

    def init_schema(self):
        conn = self.db.get_connection()
        conn.executescript(SCHEMA)
        conn.commit()

    def create_ticket(self, user_id: str, subject: str, description: str, diagnostics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ticket_id = f"ticket-{uuid.uuid4().hex[:8]}"
        diag_str = json.dumps(diagnostics, ensure_ascii=False) if diagnostics else "{}"
        try:
            conn = self.db.get_connection()
            conn.execute(
                "INSERT INTO support_tickets (id, user_id, subject, description, diagnostics_json) VALUES (?, ?, ?, ?, ?)",
                (ticket_id, user_id, subject, description, diag_str)
            )
            conn.commit()
            return {"id": ticket_id, "subject": subject, "status": "open"}
        except Exception as e:
            logger.error(f"Failed to create support ticket: {e}")
            return {"error": str(e)}

    def list_tickets(self, user_id: str) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM support_tickets WHERE user_id=? ORDER BY created_at DESC", (user_id,))
        return [dict(r) for r in cur.fetchall()]
