"""
Isolated Repository for Caching User Subscription Status locally.
"""
import logging
import json
from typing import Optional, Dict, Any, List
from app.repository.db_connection import DatabaseConnectionManager
from app.core.interfaces.storage_repository_interface import IStorageRepository

logger = logging.getLogger("runtimeforce.repository.subscription")

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscription_cache (
    user_id TEXT PRIMARY KEY,
    plan TEXT NOT NULL DEFAULT 'free',
    valid_until DATETIME,
    cached_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    entitlements_json TEXT NOT NULL DEFAULT '{}'
);
"""

class SubscriptionDBRepository(IStorageRepository):
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db = db_manager
        self.init_schema()

    def init_schema(self):
        conn = self.db.get_connection()
        conn.executescript(SCHEMA)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(subscription_cache)").fetchall()}
        if "entitlements_json" not in columns:
            conn.execute("ALTER TABLE subscription_cache ADD COLUMN entitlements_json TEXT NOT NULL DEFAULT '{}'" )
        conn.commit()

    def save_subscription(self, user_id: str, plan: str, valid_until: Optional[str] = None, entitlements: Optional[Dict[str, Any]] = None) -> bool:
        try:
            conn = self.db.get_connection()
            conn.execute(
                """
                INSERT INTO subscription_cache (user_id, plan, valid_until, cached_at, entitlements_json)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    plan=excluded.plan,
                    valid_until=excluded.valid_until,
                    cached_at=CURRENT_TIMESTAMP,
                    entitlements_json=COALESCE(excluded.entitlements_json, subscription_cache.entitlements_json)
                """,
                (user_id, plan, valid_until, json.dumps(entitlements) if entitlements is not None else None)
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
