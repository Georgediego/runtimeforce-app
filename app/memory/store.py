import sqlite3
import threading
import logging
import os
from typing import List, Dict, Any, Optional

logger = logging.getLogger("ai_runtime.memory.store")

SCHEMA = """
CREATE TABLE IF NOT EXISTS command_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    command TEXT NOT NULL, exit_code INTEGER,
    stdout TEXT, stderr TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, title TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL, role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY, name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('local', 'ssh')),
    host TEXT, port INTEGER DEFAULT 22, username TEXT, path TEXT,
    auth_type TEXT CHECK(auth_type IN ('password', 'key')),
    password_enc TEXT, key_id TEXT,
    is_active INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (key_id) REFERENCES ssh_keys(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS ssh_keys (
    id TEXT PRIMARY KEY, name TEXT NOT NULL,
    private_key_enc TEXT NOT NULL, passphrase_enc TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS provider_keys (
    provider TEXT PRIMARY KEY,
    key_enc TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_workspaces_active ON workspaces(is_active);
"""


class RuntimeStore:
    """Thread-safe persistent SQLite with WAL mode and in-memory caching."""

    def __init__(self, db_path: str = "app/memory/runtime.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._lock = threading.Lock()
        self._local = threading.local()
        # Caches
        self._workspaces_cache: Optional[List[Dict[str, Any]]] = None
        self._active_ws_cache: Optional[Dict[str, Any]] = None
        self._provider_keys_cache: Optional[Dict[str, str]] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA cache_size=-8000;")
            conn.execute("PRAGMA temp_store=MEMORY;")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            # Check existing tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            existing = {row[0] for row in cursor.fetchall()}
            # Create missing tables
            if "sessions" not in existing:
                cursor.executescript(SCHEMA)
                conn.commit()
                logger.info("Fresh database created.")
            else:
                # Add missing tables incrementally
                if "workspaces" not in existing:
                    cursor.execute("""CREATE TABLE workspaces (
                        id TEXT PRIMARY KEY, name TEXT NOT NULL,
                        type TEXT NOT NULL CHECK(type IN ('local','ssh')),
                        host TEXT, port INTEGER DEFAULT 22, username TEXT, path TEXT,
                        auth_type TEXT CHECK(auth_type IN ('password','key')),
                        password_enc TEXT, key_id TEXT,
                        is_active INTEGER DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (key_id) REFERENCES ssh_keys(id) ON DELETE SET NULL
                    );""")
                if "ssh_keys" not in existing:
                    cursor.execute("""CREATE TABLE ssh_keys (
                        id TEXT PRIMARY KEY, name TEXT NOT NULL,
                        private_key_enc TEXT NOT NULL, passphrase_enc TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    );""")
                if "provider_keys" not in existing:
                    cursor.execute("""CREATE TABLE provider_keys (
                        provider TEXT PRIMARY KEY,
                        key_enc TEXT NOT NULL,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    );""")
                    logger.info("Added provider_keys table.")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_workspaces_active ON workspaces(is_active);")
                conn.commit()
            # Pre-warm caches
            self._invalidate_ws_cache()
            self._invalidate_keys_cache()

    def _invalidate_ws_cache(self):
        self._workspaces_cache = None
        self._active_ws_cache = None

    def _invalidate_keys_cache(self):
        self._provider_keys_cache = None

    # ── PROVIDER KEYS (encrypted in DB) ──────────────
    def save_provider_key(self, provider: str, key_enc: str):
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO provider_keys (provider, key_enc, updated_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(provider) DO UPDATE SET key_enc=excluded.key_enc, updated_at=CURRENT_TIMESTAMP",
                (provider, key_enc),
            )
            conn.commit()
            self._invalidate_keys_cache()

    def get_all_provider_keys(self) -> Dict[str, str]:
        """Returns all provider keys (already encrypted). Cached."""
        if self._provider_keys_cache is not None:
            return self._provider_keys_cache
        with self._lock:
            cursor = self._get_conn().cursor()
            cursor.execute("SELECT provider, key_enc FROM provider_keys")
            result = {row["provider"]: row["key_enc"] for row in cursor.fetchall()}
            self._provider_keys_cache = result
            return result

    def delete_provider_key(self, provider: str):
        with self._lock:
            conn = self._get_conn()
            conn.execute("DELETE FROM provider_keys WHERE provider = ?", (provider,))
            conn.commit()
            self._invalidate_keys_cache()

    def clear_all_provider_keys(self):
        with self._lock:
            conn = self._get_conn()
            conn.execute("DELETE FROM provider_keys")
            conn.commit()
            self._invalidate_keys_cache()

    # ── COMMAND AUDIT ────────────────────────────────
    def log_command(self, command, exit_code, stdout, stderr, status):
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute(
                    "INSERT INTO command_audit (command,exit_code,stdout,stderr,status) VALUES (?,?,?,?,?)",
                    (command, exit_code, stdout[:10000], stderr[:10000], status),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Audit log failed: {e}")

    # ── SESSIONS ─────────────────────────────────────
    def get_all_sessions(self) -> List[Dict[str, Any]]:
        try:
            with self._lock:
                cur = self._get_conn().cursor()
                cur.execute("SELECT * FROM sessions ORDER BY updated_at DESC")
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Sessions fetch failed: {e}")
            return []

    def create_session(self, session_id: str, title: str) -> bool:
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute(
                    "INSERT INTO sessions (id,title) VALUES (?,?) "
                    "ON CONFLICT(id) DO UPDATE SET title=excluded.title, updated_at=CURRENT_TIMESTAMP",
                    (session_id, title),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Session create failed: {e}")
            return False

    def get_session_messages(self, session_id: str) -> List[Dict[str, str]]:
        try:
            with self._lock:
                cur = self._get_conn().cursor()
                cur.execute("SELECT role,content FROM messages WHERE session_id=? ORDER BY id", (session_id,))
                return [{"role": r["role"], "content": r["content"]} for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Messages fetch failed: {e}")
            return []

    def append_message(self, session_id: str, role: str, content: str):
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute("INSERT INTO messages (session_id,role,content) VALUES (?,?,?)",
                             (session_id, role, content))
                conn.execute("UPDATE sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (session_id,))
                conn.commit()
        except Exception as e:
            logger.error(f"Message append failed: {e}")

    # ── WORKSPACES (cached) ──────────────────────────
    def get_all_workspaces(self) -> List[Dict[str, Any]]:
        if self._workspaces_cache is not None:
            return self._workspaces_cache
        try:
            with self._lock:
                cur = self._get_conn().cursor()
                cur.execute("SELECT * FROM workspaces ORDER BY is_active DESC, created_at DESC")
                self._workspaces_cache = [dict(r) for r in cur.fetchall()]
                return self._workspaces_cache
        except Exception as e:
            logger.error(f"Workspaces fetch failed: {e}")
            return []

    def get_workspace(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        if self._workspaces_cache:
            for ws in self._workspaces_cache:
                if ws["id"] == workspace_id:
                    return ws
        try:
            with self._lock:
                cur = self._get_conn().cursor()
                cur.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Workspace get failed: {e}")
            return None

    def get_active_workspace(self) -> Optional[Dict[str, Any]]:
        if self._active_ws_cache is not None:
            return self._active_ws_cache or None
        try:
            with self._lock:
                cur = self._get_conn().cursor()
                cur.execute("SELECT * FROM workspaces WHERE is_active=1 LIMIT 1")
                row = cur.fetchone()
                self._active_ws_cache = dict(row) if row else {}
                return self._active_ws_cache or None
        except Exception as e:
            logger.error(f"Active workspace fetch failed: {e}")
            return None

    def create_workspace(self, workspace_id: str, **kwargs) -> bool:
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute(
                    "INSERT INTO workspaces (id,name,type,host,port,username,path,"
                    "auth_type,password_enc,key_id,is_active) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (workspace_id, kwargs.get("name"), kwargs.get("type"),
                     kwargs.get("host"), kwargs.get("port", 22), kwargs.get("username"),
                     kwargs.get("path"), kwargs.get("auth_type"), kwargs.get("password_enc"),
                     kwargs.get("key_id"), 1 if kwargs.get("is_active") else 0),
                )
                conn.commit()
                self._invalidate_ws_cache()
                return True
        except Exception as e:
            logger.error(f"Workspace create failed: {e}")
            return False

    def set_active_workspace(self, workspace_id: str) -> bool:
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute("UPDATE workspaces SET is_active=0")
                conn.execute("UPDATE workspaces SET is_active=1 WHERE id=?", (workspace_id,))
                conn.commit()
                self._invalidate_ws_cache()
                return True
        except Exception as e:
            logger.error(f"Workspace activate failed: {e}")
            return False

    def delete_workspace(self, workspace_id: str) -> bool:
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute("DELETE FROM workspaces WHERE id=?", (workspace_id,))
                conn.commit()
                self._invalidate_ws_cache()
                return True
        except Exception as e:
            logger.error(f"Workspace delete failed: {e}")
            return False

    # ── SSH KEYS ─────────────────────────────────────
    def save_ssh_key(self, key_id, name, private_key_enc, passphrase_enc=None):
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute("INSERT INTO ssh_keys (id,name,private_key_enc,passphrase_enc) VALUES (?,?,?,?)",
                             (key_id, name, private_key_enc, passphrase_enc))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"SSH key save failed: {e}")
            return False

    def get_ssh_key(self, key_id):
        try:
            with self._lock:
                cur = self._get_conn().cursor()
                cur.execute("SELECT * FROM ssh_keys WHERE id=?", (key_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"SSH key get failed: {e}")
            return None

    def delete_ssh_key(self, key_id):
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute("DELETE FROM ssh_keys WHERE id=?", (key_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"SSH key delete failed: {e}")
            return False

    # Backward compat alias
    def _get_connection(self):
        return self._get_conn()


store = RuntimeStore()
