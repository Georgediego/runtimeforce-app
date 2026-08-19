"""
Isolated Repository for Caching User Subscription Status locally.
"""
import logging
from typing import Optional, Dict, Any, List
from app.repository.db_connection import DatabaseConnectionManager
from app.core.interfaces.storage_repository_interface import IStorageRepository

logger = logging.getLogger("runtimeforce.repository.subscription")

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscription_cache (
    user_id TEXT PRIMARY KEY,
    plan TEXT NOT NULL DEFAULT 'free',
    valid_until DATETIME,
    cached_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

class SubscriptionDBRepository(IStorageRepository):
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db = db_manager
        self.init_schema()

    def init_schema(self):
        conn = self.db.get_connection()
        conn.executescript(SCHEMA)
        conn.commit()

    def save_subscription(self, user_id: str, plan: str, valid_until: Optional[str] = None) -> bool:
        try:
            conn = self.db.get_connection()
            conn.execute(
                """
                INSERT INTO subscription_cache (user_id, plan, valid_until, cached_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    plan=excluded.plan,
                    valid_until=excluded.valid_until,
                    cached_at=CURRENT_TIMESTAMP
                """,
                (user_id, plan, valid_until)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to cache subscription for {user_id}: {e}")
            return False

    def get_by_id(self, entity_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM subscription_cache WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def list_all(self, user_id: str) -> List[Dict[str, Any]]:
        res = self.get_by_id("", user_id)
        return [res] if res else []

    def delete(self, entity_id: str, user_id: str) -> bool:
        conn = self.db.get_connection()
        conn.execute("DELETE FROM subscription_cache WHERE user_id=?", (user_id,))
        conn.commit()
        return True
