import sqlite3
import json
from typing import Optional, Dict, Any
from datetime import datetime
from app.core.interfaces.oauth_repository_interface import IOAuthRepository
from app.repository.db_connection import DatabaseConnectionManager
from app.core.security.aes_crypto_service import AESCryptoService

ENCRYPTED_PREFIX = "enc:v1:"

class OAuthDBRepository(IOAuthRepository):
    """SQLite implementation for OAuth token storage."""

    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db_manager = db_manager

    async def save_token(self, project_id: str, provider: str, token_data: Dict[str, Any]) -> bool:
        """Save or update OAuth token data for a project."""
        conn = None
        try:
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()

            serialized = json.dumps(token_data, separators=(",", ":"), ensure_ascii=False)
            encrypted_data = ENCRYPTED_PREFIX + AESCryptoService.encrypt(serialized)
            
            cursor.execute("""
                INSERT OR REPLACE INTO project_oauth_tokens 
                (project_id, provider, token_data, expires_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                project_id,
                provider,
                encrypted_data,
                token_data.get('expires_at'),
                datetime.utcnow().isoformat(),
                datetime.utcnow().isoformat()
            ))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"[OAuthDBRepository] Error saving token: {e}")
            return False
        finally:
            if conn:
                conn.close()

    async def get_token(self, project_id: str, provider: str) -> Optional[Dict[str, Any]]:
        """Retrieve OAuth token data for a project."""
        conn = None
        try:
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT token_data, expires_at FROM project_oauth_tokens
                WHERE project_id = ? AND provider = ?
            """, (project_id, provider))
            
            row = cursor.fetchone()
            if row:
                stored = row[0]
                if stored.startswith(ENCRYPTED_PREFIX):
                    plaintext = AESCryptoService.decrypt(stored[len(ENCRYPTED_PREFIX):])
                    token_data = json.loads(plaintext)
                else:
                    # Migrate legacy plaintext records on first successful read.
                    token_data = json.loads(stored)
                    serialized = json.dumps(token_data, separators=(",", ":"), ensure_ascii=False)
                    encrypted = ENCRYPTED_PREFIX + AESCryptoService.encrypt(serialized)
                    cursor.execute(
                        "UPDATE project_oauth_tokens SET token_data=?, updated_at=? WHERE project_id=? AND provider=?",
                        (encrypted, datetime.utcnow().isoformat(), project_id, provider)
                    )
                    conn.commit()
                # Check expiration
                if token_data.get('expires_at'):
                    expires_at = datetime.fromisoformat(token_data['expires_at'])
                    if expires_at < datetime.utcnow():
                        return None  # Token expired
                return token_data
            return None
        except Exception as e:
            print(f"[OAuthDBRepository] Error getting token: {e}")
            return None
        finally:
            if conn:
                conn.close()

    async def delete_token(self, project_id: str, provider: str) -> bool:
        """Revoke and delete OAuth token data."""
        conn = None
        try:
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                DELETE FROM project_oauth_tokens
                WHERE project_id = ? AND provider = ?
            """, (project_id, provider))
            
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"[OAuthDBRepository] Error deleting token: {e}")
            return False
        finally:
            if conn:
                conn.close()

    async def is_connected(self, project_id: str, provider: str) -> bool:
        """Check if a provider is connected."""
        token = await self.get_token(project_id, provider)
        return token is not None
