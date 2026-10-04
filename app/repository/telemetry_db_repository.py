"""
Isolated Repository for Telemetry, Audit Logging, and Smart Scoring.
"""
import logging
from typing import Dict, Any, Optional
from app.repository.db_connection import DatabaseConnectionManager

logger = logging.getLogger("runtimeforce.repository.telemetry")

class TelemetryDBRepository:
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db = db_manager

    def log_command(
        self, command: str, exit_code: int, stdout: str, stderr: str, status: str, user_id: str
    ):
        try:
            conn = self.db.get_connection()
            conn.execute(
                """
                INSERT INTO command_audit
                    (command, exit_code, stdout, stderr, status, user_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (command, exit_code, stdout[:10000], stderr[:10000], status, user_id)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Audit log failed: {e}")

    def log_telemetry(
        self,
        model_id: str,
        provider: str,
        latency_ms: int,
        tokens_in: int = 0,
        tokens_out: int = 0,
        success: bool = True,
        error_type: Optional[str] = None,
        cost_usd: float = 0.0,
        strategy: str = "auto",
        was_fallback: bool = False,
        session_id: Optional[str] = None,
        user_id: str = "anonymous",
    ) -> bool:
        try:
            conn = self.db.get_connection()
            conn.execute(
                """
                INSERT INTO model_telemetry
                    (model_id, provider, session_id, latency_ms,
                     tokens_in, tokens_out, success, error_type,
                     cost_usd, strategy, was_fallback, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_id, provider, session_id, latency_ms,
                    tokens_in, tokens_out, 1 if success else 0,
                    error_type, cost_usd, strategy,
                    1 if was_fallback else 0, user_id
                )
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Telemetry log failed: {e}")
            return False

    def get_model_scores(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM model_scores WHERE user_id = ? ORDER BY total_score DESC",
            (user_id,)
        )
        result = {}
        for row in cur.fetchall():
            result[row["model_id"]] = {
                "provider": row["provider"],
                "quality": row["quality_score"],
                "speed": row["speed_score"],
                "cost": row["cost_score"],
                "stability": row["stability_score"],
                "total": row["total_score"],
                "samples": row["sample_count"],
            }
        return result

    def get_telemetry_stats(self, hours: int = 24, user_id: str = "anonymous") -> Dict[str, Any]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COUNT(*) as total_calls,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_calls,
                SUM(tokens_out) as total_tokens,
                SUM(cost_usd) as total_cost,
                AVG(CASE WHEN success = 1 THEN latency_ms ELSE NULL END) as avg_latency
            FROM model_telemetry
            WHERE timestamp >= datetime('now', '-' || ? || ' hours')
              AND user_id = ?
            """,
            (hours, user_id)
        )
        row = cur.fetchone()
        return {
            "total_calls": row["total_calls"] or 0,
            "success_rate": (
                (row["success_calls"] / row["total_calls"] * 100)
                if row["total_calls"] else 0
            ),
            "total_tokens": row["total_tokens"] or 0,
            "total_cost_usd": row["total_cost"] or 0,
            "avg_latency_ms": row["avg_latency"] or 0,
        }
