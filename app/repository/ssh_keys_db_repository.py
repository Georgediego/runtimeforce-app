"""
Isolated Repository for SSH Keys Database Persistence.
"""
import logging
from typing import Optional, Dict, Any
from app.repository.db_connection import DatabaseConnectionManager

logger = logging.getLogger("runtimeforce.repository.ssh_keys")

class SSHKeysDBRepository:
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db = db_manager

    def save_ssh_key(
        self, kid: str, name: str, pk_enc: str, pp_enc: Optional[str], user_id: str
    ):
        conn = self.db.get_connection()
        conn.execute(
            """
            INSERT INTO ssh_keys (id, name, private_key_enc, passphrase_enc, user_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (kid, name, pk_enc, pp_enc, user_id)
        )
        conn.commit()

    def get_ssh_key(self, kid: str, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM ssh_keys WHERE id=? AND user_id=?",
            (kid, user_id)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def delete_ssh_key(self, kid: str, user_id: str) -> bool:
        conn = self.db.get_connection()
        conn.execute("DELETE FROM ssh_keys WHERE id=? AND user_id=?", (kid, user_id))
        conn.commit()
        return True
