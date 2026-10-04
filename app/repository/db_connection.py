"""
Single Source of Truth for SQLite Connection, Schema Migrations, and Context Transactions.
"""
import sqlite3
import threading
import logging
import os
import sys
import stat
from contextlib import contextmanager
from typing import Optional, Generator

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

CREATE TABLE IF NOT EXISTS project_oauth_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    provider TEXT NOT NULL CHECK(provider IN ('github', 'x', 'reddit')),
    token_data TEXT NOT NULL,
    expires_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT DEFAULT 'anonymous',
    UNIQUE(project_id, provider)
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
CREATE INDEX IF NOT EXISTS idx_oauth_project ON project_oauth_tokens(project_id, user_id);
CREATE INDEX IF NOT EXISTS idx_oauth_provider ON project_oauth_tokens(provider);
"""

def get_default_db_path() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        db_dir = os.path.join(base, "RuntimeForce")
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        db_dir = os.path.join(base, "runtimeforce")
    return os.path.join(db_dir, "runtime.db")

class DatabaseConnectionManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_default_db_path()
        db_dir = os.path.dirname(self.db_path)
        os.makedirs(db_dir, exist_ok=True)
        try:
            os.chmod(db_dir, stat.S_IRWXU)
        except OSError:
            pass

        self._lock = threading.Lock()
        self._local = threading.local()
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                self.db_path, check_same_thread=False, timeout=10.0
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=10000;")
            conn.execute("PRAGMA foreign_keys=ON;")
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction rolled back due to error: {e}")
            raise

    def init_db(self):
        with self._lock:
            conn = self.get_connection()
            conn.executescript(SCHEMA)
            conn.commit()
        try:
            os.chmod(self.db_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
