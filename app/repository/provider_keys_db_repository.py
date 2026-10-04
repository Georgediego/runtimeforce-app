"""
Isolated Repository for Provider API Keys and Selected Models with Database Cleanup.
"""
import logging
from typing import Dict, List
from app.repository.db_connection import DatabaseConnectionManager

logger = logging.getLogger("runtimeforce.repository.provider_keys")

class ProviderKeysDBRepository:
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db = db_manager
        self._cleanup_synthetic_models()

    def _cleanup_synthetic_models(self):
        try:
            conn = self.db.get_connection()
            conn.execute("""
                DELETE FROM provider_selected_models 
                WHERE model_id LIKE '%gemini-3%' 
                   OR model_id LIKE '%customtools%' 
                   OR model_id LIKE '%gpt-5%' 
                   OR model_id LIKE '%claude-sonnet-5%' 
                   OR model_id LIKE '%claude-opus-5%'
                   OR model_id LIKE '%claude-haiku-4%'
                   OR model_id LIKE '%grok-4%'
            """)
            conn.commit()
        except Exception as e:
            logger.debug(f"Synthetic models cleanup skipped: {e}")

    def save_provider_key(self, provider: str, key_enc: str, user_id: str):
        conn = self.db.get_connection()
        conn.execute(
            """
            INSERT INTO provider_keys (provider, key_enc, updated_at, user_id)
            VALUES (?, ?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(provider, user_id) DO UPDATE SET
                key_enc=excluded.key_enc,
                updated_at=CURRENT_TIMESTAMP
            """,
            (provider, key_enc, user_id)
        )
        conn.commit()

    def get_all_provider_keys(self, user_id: str) -> Dict[str, str]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT provider, key_enc FROM provider_keys 
            WHERE user_id = ? OR user_id = 'anonymous' OR user_id = 'default_user'
            ORDER BY CASE WHEN user_id = ? THEN 0 ELSE 1 END
            """,
            (user_id, user_id)
        )
        result = {}
        for r in cur.fetchall():
            p = r["provider"]
            if p not in result:
                result[p] = r["key_enc"]
        return result

    def delete_provider_key(self, provider: str, user_id: str):
        conn = self.db.get_connection()
        conn.execute(
            "DELETE FROM provider_keys WHERE provider = ? AND (user_id = ? OR user_id = 'anonymous' OR user_id = 'default_user')",
            (provider, user_id)
        )
        conn.execute(
            "DELETE FROM provider_selected_models WHERE provider_id = ? AND (user_id = ? OR user_id = 'anonymous' OR user_id = 'default_user')",
            (provider, user_id)
        )
        conn.commit()

    def save_selected_models(self, provider_id: str, model_ids: List[str], user_id: str):
        conn = self.db.get_connection()
        p_clean = provider_id.lower().strip()
        conn.execute(
            "DELETE FROM provider_selected_models WHERE provider_id=? AND (user_id=? OR user_id='anonymous' OR user_id='default_user')",
            (p_clean, user_id)
        )
        for mid in model_ids:
            if mid and mid.strip():
                m_clean = mid.strip()
                # Do not insert invalid/synthetic model names
                if "gemini-3" in m_clean.lower() or "customtools" in m_clean.lower():
                    continue
                conn.execute(
                    """
                    INSERT INTO provider_selected_models (user_id, provider_id, model_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, provider_id, model_id) DO NOTHING
                    """,
                    (user_id, p_clean, m_clean)
                )
        conn.commit()

    def get_selected_models(self, provider_id: str, user_id: str) -> List[str]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        p_clean = provider_id.lower().strip()
        cur.execute(
            """
            SELECT model_id FROM provider_selected_models 
            WHERE provider_id=? AND (user_id=? OR user_id='anonymous' OR user_id='default_user')
            """,
            (p_clean, user_id)
        )
        return [r["model_id"] for r in cur.fetchall() if "gemini-3" not in r["model_id"].lower()]

    def get_all_selected_models(self, user_id: str) -> Dict[str, List[str]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT provider_id, model_id FROM provider_selected_models 
            WHERE user_id=? OR user_id='anonymous' OR user_id='default_user'
            """,
            (user_id,)
        )
        res: Dict[str, List[str]] = {}
        for r in cur.fetchall():
            mid = r["model_id"]
            if "gemini-3" not in mid.lower() and "customtools" not in mid.lower():
                res.setdefault(r["provider_id"], []).append(mid)
        return res
