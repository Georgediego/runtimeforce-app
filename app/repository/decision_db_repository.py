"""
Repository for Storing and Querying Architectural & Technical Decision Memory.
"""
import uuid
import logging
from typing import Optional, Dict, Any, List
from app.repository.db_connection import DatabaseConnectionManager
from app.core.interfaces.decision_memory_interface import IDecisionMemory

logger = logging.getLogger("runtimeforce.repository.decision")

SCHEMA = """
CREATE TABLE IF NOT EXISTS decision_memory (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    decision TEXT NOT NULL,
    rationale TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_decisions_proj ON decision_memory(project_id, user_id);
"""

class DecisionDBRepository(IDecisionMemory):
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db = db_manager
        self.init_schema()

    def init_schema(self):
        conn = self.db.get_connection()
        conn.executescript(SCHEMA)
        conn.commit()

    def record_decision(
        self,
        project_id: str,
        user_id: str,
        topic: str,
        decision: str,
        rationale: str
    ) -> Dict[str, Any]:
        decision_id = f"dec-{uuid.uuid4().hex[:8]}"
        try:
            conn = self.db.get_connection()
            conn.execute(
                "INSERT INTO decision_memory (id, project_id, user_id, topic, decision, rationale) VALUES (?, ?, ?, ?, ?, ?)",
                (decision_id, project_id, user_id, topic, decision, rationale)
            )
            conn.commit()
            return {"id": decision_id, "topic": topic, "decision": decision, "rationale": rationale}
        except Exception as e:
            logger.error(f"Failed to record decision for project {project_id}: {e}")
            return {"error": str(e)}

    def get_decisions(self, project_id: str, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM decision_memory WHERE project_id=? AND user_id=? ORDER BY created_at DESC LIMIT ?",
            (project_id, user_id, limit)
        )
        return [dict(r) for r in cur.fetchall()]
