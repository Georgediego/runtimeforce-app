"""
Single source of truth for encrypted SQLite connections, schema migrations,
and context transactions.
"""
import base64
import logging
import os
import sqlite3 as stdlib_sqlite3
import stat
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

try:
    import sqlcipher3 as sqlite3
except ImportError as exc:
    raise RuntimeError(
        "RuntimeForce requires the SQLCipher driver. Install requirements.txt; "
        "refusing to open the local database without encryption."
    ) from exc

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from app.core.security.aes_crypto_service import AESCryptoService

logger = logging.getLogger("runtimeforce.repository.db_connection")

SCHEMA = """
CREATE TABLE IF NOT EXISTS command_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    command TEXT NOT NULL,
    exit_code INTEGER,
    stdout TEXT,
    stderr TEXT,
    status TEXT,
    user_id TEXT DEFAULT 'anonymous'
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT DEFAULT 'anonymous'
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('local', 'ssh')),
    host TEXT,
    port INTEGER DEFAULT 22,
    username TEXT,
    path TEXT,
    auth_type TEXT CHECK(auth_type IN ('password', 'key')),
    password_enc TEXT,
    key_id TEXT,
    is_active INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT DEFAULT 'anonymous',
    FOREIGN KEY (key_id) REFERENCES ssh_keys(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS ssh_keys (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    private_key_enc TEXT NOT NULL,
    passphrase_enc TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT DEFAULT 'anonymous'
);
CREATE TABLE IF NOT EXISTS provider_keys (
    provider TEXT NOT NULL,
    key_enc TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT DEFAULT 'anonymous',
    PRIMARY KEY (provider, user_id)
);
CREATE TABLE IF NOT EXISTS provider_selected_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    orchestrator_role TEXT NOT NULL DEFAULT 'AUTO',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, provider_id, model_id)
);
CREATE TABLE IF NOT EXISTS model_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    session_id TEXT,
    latency_ms INTEGER,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    success INTEGER DEFAULT 1,
    error_type TEXT,
    cost_usd REAL DEFAULT 0.0,
    strategy TEXT,
    was_fallback INTEGER DEFAULT 0,
    user_id TEXT DEFAULT 'anonymous'
);
CREATE TABLE IF NOT EXISTS model_scores (
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    quality_score REAL DEFAULT 50.0,
    speed_score REAL DEFAULT 50.0,
    cost_score REAL DEFAULT 50.0,
    stability_score REAL DEFAULT 50.0,
    total_score REAL DEFAULT 50.0,
    sample_count INTEGER DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT DEFAULT 'anonymous',
    PRIMARY KEY (model_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_workspaces_active ON workspaces(is_active);
CREATE INDEX IF NOT EXISTS idx_workspaces_user ON workspaces(user_id);
CREATE INDEX IF NOT EXISTS idx_ssh_keys_user ON ssh_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_provider_keys_user ON provider_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_selected_models_user ON provider_selected_models(user_id, provider_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_user ON model_telemetry(user_id);
CREATE INDEX IF NOT EXISTS idx_scores_user ON model_scores(user_id);
"""


def get_default_db_path() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        db_dir = os.path.join(base, "RuntimeForce")
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        db_dir = os.path.join(base, "runtimeforce")
    return os.path.join(db_dir, "runtime.db")


def _derive_database_key(master_key: bytes) -> bytes:
    if len(master_key) != 32:
        raise ValueError("RuntimeForce MASTER_KEY must decode to exactly 32 bytes.")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"runtimeforce-sqlcipher-v1",
        info=b"runtimeforce-local-database-encryption",
    ).derive(master_key)


def _sqlcipher_key_clause(key: bytes) -> str:
    # The value is generated locally and hex-encoded; no user input is interpolated.
    return f'"x\'{key.hex()}\'"'


def _attach_sqlcipher_database(conn, path: str, schema: str, key: bytes) -> None:
    escaped_path = os.path.abspath(path).replace("'", "''")
    conn.execute(
        f"ATTACH DATABASE '{escaped_path}' AS {schema} KEY {_sqlcipher_key_clause(key)}"
    )


class DatabaseConnectionManager:
    def __init__(self, db_path: Optional[str] = None, master_key: Optional[bytes] = None):
        self.db_path = os.path.abspath(db_path or get_default_db_path())
        self._master_key = master_key or AESCryptoService._get_or_create_master_key()
        self._database_key = _derive_database_key(self._master_key)
        db_dir = os.path.dirname(self.db_path)
        os.makedirs(db_dir, exist_ok=True)
        try:
            os.chmod(db_dir, stat.S_IRWXU)
        except OSError:
            pass

        self._lock = threading.Lock()
        self._local = threading.local()
        self._migrate_or_initialize_encryption()

    def _connect_encrypted(self, path: Optional[str] = None):
        conn = sqlite3.connect(path or self.db_path, check_same_thread=False, timeout=10.0)
        conn.execute(f"PRAGMA key = {_sqlcipher_key_clause(self._database_key)}")
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        version = conn.execute("PRAGMA cipher_version").fetchone()
        if not version or not version[0]:
            conn.close()
            raise RuntimeError("The installed SQLite driver does not provide SQLCipher.")
        return conn

    def _is_currently_encrypted(self) -> bool:
        if not os.path.exists(self.db_path) or os.path.getsize(self.db_path) == 0:
            return False
        try:
            conn = self._connect_encrypted()
            conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            return True
        except Exception:
            return False

    def _migrate_or_initialize_encryption(self) -> None:
        if not os.path.exists(self.db_path) or os.path.getsize(self.db_path) == 0:
            return
        if self._is_currently_encrypted():
            return

        # Never modify the source database until both encrypted exports pass validation.
        stamp = time.strftime("%Y%m%d-%H%M%S")
        temp_path = f"{self.db_path}.sqlcipher-tmp"
        backup_path = f"{self.db_path}.pre-sqlcipher-{stamp}.enc"
        for candidate in (temp_path, backup_path):
            if os.path.exists(candidate):
                raise RuntimeError(f"Refusing to overwrite existing migration artifact: {candidate}")

        source = None
        try:
            # Checkpoint any legacy WAL before exporting its contents.
            checkpoint = stdlib_sqlite3.connect(self.db_path, timeout=10.0)
            try:
                checkpoint.execute("PRAGMA wal_checkpoint(FULL)")
                check = checkpoint.execute("PRAGMA integrity_check").fetchone()
                if not check or check[0] != "ok":
                    raise RuntimeError(f"Legacy SQLite integrity check failed: {check}")
            finally:
                checkpoint.close()

            source = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
            source.execute("PRAGMA key = ''")
            source.execute("SELECT count(*) FROM sqlite_master").fetchone()

            _attach_sqlcipher_database(source, temp_path, "encrypted", self._database_key)
            source.execute("SELECT sqlcipher_export('encrypted')").fetchone()
            source.execute("DETACH DATABASE encrypted")

            _attach_sqlcipher_database(source, backup_path, "encrypted_backup", self._database_key)
            source.execute("SELECT sqlcipher_export('encrypted_backup')").fetchone()
            source.execute("DETACH DATABASE encrypted_backup")
            source.close()
            source = None

            for candidate in (temp_path, backup_path):
                verify = self._connect_encrypted(candidate)
                result = verify.execute("PRAGMA integrity_check").fetchone()
                verify.close()
                if not result or result[0] != "ok":
                    raise RuntimeError(f"SQLCipher export integrity check failed for {candidate}: {result}")

            # Atomic replacement: the plaintext source remains untouched until this point.
            os.replace(temp_path, self.db_path)
            for suffix in ("-wal", "-shm"):
                sidecar = self.db_path + suffix
                if os.path.exists(sidecar):
                    os.remove(sidecar)
            logger.info("SQLite database encrypted with SQLCipher; encrypted backup saved at %s", backup_path)
        except Exception as exc:
            if source is not None:
                source.close()
            for candidate in (temp_path, backup_path):
                try:
                    if os.path.exists(candidate):
                        os.remove(candidate)
                except OSError:
                    logger.exception("Could not remove incomplete SQLCipher migration artifact: %s", candidate)
            raise RuntimeError(
                "SQLCipher migration failed. The original database was preserved; "
                "RuntimeForce will not start with an unencrypted database."
            ) from exc

    def get_connection(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = self._connect_encrypted()
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=10000;")
            conn.execute("PRAGMA foreign_keys=ON;")
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def transaction(self) -> Generator:
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.error("Transaction rolled back due to error: %s", exc)
            raise

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def init_db(self):
        with self._lock:
            conn = self.get_connection()
            conn.execute("DROP TABLE IF EXISTS project_oauth_tokens")
            conn.execute("DROP TABLE IF EXISTS social_post_drafts")
            conn.execute("DROP TABLE IF EXISTS social_feedback_items")
            conn.executescript(SCHEMA)
            conn.commit()
        try:
            os.chmod(self.db_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
