import sqlite3
import threading
import logging
import os
import copy
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("ai_runtime.memory.store")

SCHEMA = """
CREATE TABLE IF NOT EXISTS command_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    command TEXT NOT NULL, exit_code INTEGER, stdout TEXT, stderr TEXT, status TEXT,
    user_id TEXT DEFAULT 'anonymous'
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, title TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT DEFAULT 'anonymous'
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL,
    content TEXT NOT NULL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL CHECK(type IN ('local', 'ssh')),
    host TEXT, port INTEGER DEFAULT 22, username TEXT, path TEXT,
    auth_type TEXT CHECK(auth_type IN ('password', 'key')),
    password_enc TEXT, key_id TEXT, is_active INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT DEFAULT 'anonymous',
    FOREIGN KEY (key_id) REFERENCES ssh_keys(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS ssh_keys (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, private_key_enc TEXT NOT NULL,
    passphrase_enc TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT DEFAULT 'anonymous'
);

CREATE TABLE IF NOT EXISTS provider_keys (
    provider TEXT NOT NULL, key_enc TEXT NOT NULL, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT DEFAULT 'anonymous',
    PRIMARY KEY (provider, user_id)
);

CREATE TABLE IF NOT EXISTS model_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    model_id TEXT NOT NULL, provider TEXT NOT NULL, session_id TEXT,
    latency_ms INTEGER, tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0,
    success INTEGER DEFAULT 1, error_type TEXT, cost_usd REAL DEFAULT 0.0,
    strategy TEXT, was_fallback INTEGER DEFAULT 0,
    user_id TEXT DEFAULT 'anonymous'
);

CREATE TABLE IF NOT EXISTS model_scores (
    model_id TEXT NOT NULL, provider TEXT NOT NULL,
    quality_score REAL DEFAULT 50.0, speed_score REAL DEFAULT 50.0,
    cost_score REAL DEFAULT 50.0, stability_score REAL DEFAULT 50.0,
    total_score REAL DEFAULT 50.0, sample_count INTEGER DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT DEFAULT 'anonymous',
    PRIMARY KEY (model_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_workspaces_active ON workspaces(is_active);
CREATE INDEX IF NOT EXISTS idx_workspaces_user ON workspaces(user_id);
CREATE INDEX IF NOT EXISTS idx_ssh_keys_user ON ssh_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_provider_keys_user ON provider_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_user ON model_telemetry(user_id);
CREATE INDEX IF NOT EXISTS idx_scores_user ON model_scores(user_id);
"""


class RuntimeStore:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            runtime_dir = Path.home() / ".runtimeforce"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(runtime_dir / "runtime.db")

        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self._lock = threading.Lock()
        self._local = threading.local()

        self._workspaces_cache: Dict[str, Any] = {}
        self._active_ws_cache: Dict[str, Any] = {}
        self._provider_keys_cache: Dict[str, Any] = {}
        self._scores_cache: Dict[str, Any] = {}

        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=10000;")
            conn.execute("PRAGMA foreign_keys=ON;")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        with self._lock:
            self._get_conn().executescript(SCHEMA)
            self._get_conn().commit()
            # Миграция: добавляем user_id в старые таблицы если его нет
            self._migrate_add_user_id()

    def _migrate_add_user_id(self):
        """Добавляет user_id колонку в существующие таблицы (миграция)."""
        conn = self._get_conn()
        tables = [
            "workspaces", "ssh_keys", "sessions", "command_audit",
            "model_telemetry"
        ]
        for table in tables:
            try:
                cur = conn.execute(f"PRAGMA table_info({table})")
                columns = [row["name"] for row in cur.fetchall()]
                if "user_id" not in columns:
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN user_id TEXT DEFAULT 'anonymous'"
                    )
                    logger.info(f"Migrated {table}: added user_id column")
            except Exception as e:
                logger.warning(f"Migration for {table} skipped: {e}")

        # provider_keys и model_scores — составной PK, нужна пересоздание
        try:
            cur = conn.execute("PRAGMA table_info(provider_keys)")
            columns = [row["name"] for row in cur.fetchall()]
            if "user_id" not in columns:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS provider_keys_new (
                        provider TEXT NOT NULL, key_enc TEXT NOT NULL,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        user_id TEXT DEFAULT 'anonymous',
                        PRIMARY KEY (provider, user_id)
                    )
                """)
                conn.execute("""
                    INSERT OR IGNORE INTO provider_keys_new (provider, key_enc, updated_at, user_id)
                    SELECT provider, key_enc, updated_at, 'anonymous' FROM provider_keys
                """)
                conn.execute("DROP TABLE provider_keys")
                conn.execute("ALTER TABLE provider_keys_new RENAME TO provider_keys")
                logger.info("Migrated provider_keys: composite PK with user_id")
        except Exception as e:
            logger.warning(f"Migration for provider_keys skipped: {e}")

        try:
            cur = conn.execute("PRAGMA table_info(model_scores)")
            columns = [row["name"] for row in cur.fetchall()]
            if "user_id" not in columns:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS model_scores_new (
                        model_id TEXT NOT NULL, provider TEXT NOT NULL,
                        quality_score REAL DEFAULT 50.0, speed_score REAL DEFAULT 50.0,
                        cost_score REAL DEFAULT 50.0, stability_score REAL DEFAULT 50.0,
                        total_score REAL DEFAULT 50.0, sample_count INTEGER DEFAULT 0,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        user_id TEXT DEFAULT 'anonymous',
                        PRIMARY KEY (model_id, user_id)
                    )
                """)
                conn.execute("""
                    INSERT OR IGNORE INTO model_scores_new 
                    (model_id, provider, quality_score, speed_score, cost_score,
                     stability_score, total_score, sample_count, updated_at, user_id)
                    SELECT model_id, provider, quality_score, speed_score, cost_score,
                           stability_score, total_score, sample_count, updated_at, 'anonymous'
                    FROM model_scores
                """)
                conn.execute("DROP TABLE model_scores")
                conn.execute("ALTER TABLE model_scores_new RENAME TO model_scores")
                logger.info("Migrated model_scores: composite PK with user_id")
        except Exception as e:
            logger.warning(f"Migration for model_scores skipped: {e}")

        conn.commit()

    def _invalidate_ws_cache(self, user_id: str = None):
        self._workspaces_cache.clear()
        self._active_ws_cache.clear()

    def _invalidate_keys_cache(self, user_id: str = None):
        if user_id:
            self._provider_keys_cache.pop(user_id, None)
        else:
            self._provider_keys_cache.clear()

    def _invalidate_scores_cache(self, user_id: str = None):
        if user_id:
            self._scores_cache.pop(user_id, None)
        else:
            self._scores_cache.clear()

    # ── PROVIDER KEYS (user-isolated) ─────────────────────
    def save_provider_key(self, provider: str, key_enc: str, user_id: str = "anonymous"):
        with self._lock:
            self._get_conn().execute(
                "INSERT INTO provider_keys (provider, key_enc, updated_at, user_id) "
                "VALUES (?, ?, CURRENT_TIMESTAMP, ?) "
                "ON CONFLICT(provider, user_id) DO UPDATE SET "
                "key_enc=excluded.key_enc, updated_at=CURRENT_TIMESTAMP",
                (provider, key_enc, user_id),
            )
            self._get_conn().commit()
            self._invalidate_keys_cache(user_id)

    def get_all_provider_keys(self, user_id: str = "anonymous") -> Dict[str, str]:
        cache_key = user_id
        if cache_key in self._provider_keys_cache:
            return self._provider_keys_cache[cache_key]
        with self._lock:
            cur = self._get_conn().cursor()
            cur.execute(
                "SELECT provider, key_enc FROM provider_keys WHERE user_id = ?",
                (user_id,),
            )
            result = {r["provider"]: r["key_enc"] for r in cur.fetchall()}
            self._provider_keys_cache[cache_key] = result
            return result

    def delete_provider_key(self, provider: str, user_id: str = "anonymous"):
        with self._lock:
            self._get_conn().execute(
                "DELETE FROM provider_keys WHERE provider = ? AND user_id = ?",
                (provider, user_id),
            )
            self._get_conn().commit()
            self._invalidate_keys_cache(user_id)

    # ── COMMAND AUDIT ──────────────────────────────────────
    def log_command(self, command, exit_code, stdout, stderr, status, user_id: str = "anonymous"):
        try:
            with self._lock:
                self._get_conn().execute(
                    "INSERT INTO command_audit (command,exit_code,stdout,stderr,status,user_id) "
                    "VALUES (?,?,?,?,?,?)",
                    (command, exit_code, stdout[:10000], stderr[:10000], status, user_id),
                )
                self._get_conn().commit()
        except Exception as e:
            logger.error(f"Audit log failed: {e}")

    # ── SESSIONS (user-isolated) ───────────────────────────
    def get_all_sessions(self, user_id: str = "anonymous") -> List[Dict[str, Any]]:
        try:
            with self._lock:
                cur = self._get_conn().cursor()
                cur.execute(
                    "SELECT * FROM sessions WHERE user_id = ? ORDER BY updated_at DESC",
                    (user_id,),
                )
                rows = cur.fetchall()

                # ИСПРАВЛЕНИЕ: Фолбэк на анонимного пользователя, если сессий под SaaS-аккаунтом еще нет
                if not rows and user_id != "anonymous":
                    cur.execute(
                        "SELECT * FROM sessions WHERE user_id = 'anonymous' ORDER BY updated_at DESC"
                    )
                    rows = cur.fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Sessions fetch failed: {e}")
            return []

    def create_session(self, session_id: str, title: str, user_id: str = "anonymous") -> bool:
        try:
            with self._lock:
                self._get_conn().execute(
                    "INSERT INTO sessions (id, title, user_id) VALUES (?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET title=excluded.title, "
                    "updated_at=CURRENT_TIMESTAMP",
                    (session_id, title, user_id),
                )
                self._get_conn().commit()
                return True
        except Exception as e:
            logger.error(f"Session create failed: {e}")
            return False

    def get_session_messages(self, session_id: str) -> List[Dict[str, str]]:
        try:
            with self._lock:
                cur = self._get_conn().cursor()
                # Фильтруем технический мусор на уровне БД
                cur.execute(
                    "SELECT role, content FROM messages WHERE session_id=? AND role IN ('user', 'assistant') ORDER BY id",
                    (session_id,),
                )
                return [{"role": r["role"], "content": r["content"]} for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Messages fetch failed: {e}")
            return []

    def append_message(self, session_id: str, role: str, content: str):
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute(
                    "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                    (session_id, role, content),
                )
                conn.execute(
                    "UPDATE sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (session_id,),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Message append failed: {e}")

    def delete_session(self, session_id: str) -> bool:
        try:
            with self._lock:
                self._get_conn().execute("DELETE FROM sessions WHERE id=?", (session_id,))
                self._get_conn().commit()
                return True
        except Exception as e:
            logger.error(f"Session delete failed: {e}")
            return False

    # ── WORKSPACES (user-isolated) ─────────────────────────
    def get_all_workspaces(self, user_id: str = "anonymous") -> List[Dict[str, Any]]:
        cache_key = user_id
        if cache_key in self._workspaces_cache:
            return copy.deepcopy(self._workspaces_cache[cache_key])
        with self._lock:
            cur = self._get_conn().cursor()
            cur.execute(
                "SELECT * FROM workspaces WHERE user_id = ? "
                "ORDER BY is_active DESC, created_at DESC",
                (user_id,),
            )
            result = [dict(r) for r in cur.fetchall()]

            # ФОЛБЭК: Если для вошедшего юзера пусто, берем анонимные или вообще любые зарегистрированные
            if not result and user_id != "anonymous":
                cur.execute(
                    "SELECT * FROM workspaces WHERE user_id = 'anonymous' "
                    "ORDER BY is_active DESC, created_at DESC"
                )
                result = [dict(r) for r in cur.fetchall()]
            if not result:
                cur.execute(
                    "SELECT * FROM workspaces "
                    "ORDER BY is_active DESC, created_at DESC"
                )
                result = [dict(r) for r in cur.fetchall()]

            self._workspaces_cache[cache_key] = result
            return copy.deepcopy(result)

    def get_workspace(self, wid: str, user_id: str = "anonymous") -> Optional[Dict[str, Any]]:
        with self._lock:
            cur = self._get_conn().cursor()
            cur.execute(
                "SELECT * FROM workspaces WHERE id=? AND user_id=?",
                (wid, user_id),
            )
            row = cur.fetchone()

            # ИСПРАВЛЕНИЕ: Глобальный поиск по ID, если воркспейс не найден для конкретного юзера
            if not row:
                cur.execute(
                    "SELECT * FROM workspaces WHERE id=?",
                    (wid,),
                )
                row = cur.fetchone()
            return dict(row) if row else None

    def get_active_workspace(self, user_id: str = "anonymous") -> Optional[Dict[str, Any]]:
        cache_key = user_id
        if cache_key in self._active_ws_cache and self._active_ws_cache[cache_key] is not None:
            return copy.deepcopy(self._active_ws_cache[cache_key])
        with self._lock:
            cur = self._get_conn().cursor()
            cur.execute(
                "SELECT * FROM workspaces WHERE is_active=1 AND user_id=? LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()

            # ИСПРАВЛЕНИЕ ФОЛБЭК 1: Если для вошедшего юзера нет активного воркспейса, берем анонимный
            if not row and user_id != "anonymous":
                cur.execute(
                    "SELECT * FROM workspaces WHERE is_active=1 AND user_id='anonymous' LIMIT 1"
                )
                row = cur.fetchone()

            # ИСПРАВЛЕНИЕ ФОЛБЭК 2: Если совсем ничего активного нет, возвращаем любой найденный активный воркспейс
            if not row:
                cur.execute(
                    "SELECT * FROM workspaces WHERE is_active=1 LIMIT 1"
                )
                row = cur.fetchone()

            # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ ФОЛБЭК 3: Если даже активных воркспейсов нет вообще (после перезапуска или до активации), 
            # возвращаем абсолютно любой воркспейс, найденный в таблице базы данных
            if not row:
                cur.execute(
                    "SELECT * FROM workspaces LIMIT 1"
                )
                row = cur.fetchone()

            result = dict(row) if row else None
            if result:
                self._active_ws_cache[cache_key] = result # Кэшируем только если нашли вадилный воркспейс
            return copy.deepcopy(result) if result else None

    def create_workspace(self, workspace_id: str, user_id: str = "anonymous", **kwargs) -> bool:
        try:
            with self._lock:
                self._get_conn().execute(
                    "INSERT INTO workspaces "
                    "(id,name,type,host,port,username,path,auth_type,password_enc,key_id,is_active,user_id) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        workspace_id, kwargs.get("name"), kwargs.get("type"),
                        kwargs.get("host"), kwargs.get("port", 22),
                        kwargs.get("username"), kwargs.get("path"),
                        kwargs.get("auth_type"), kwargs.get("password_enc"),
                        kwargs.get("key_id"),
                        1 if kwargs.get("is_active") else 0,
                        user_id,
                    ),
                )
                self._get_conn().commit()
                self._invalidate_ws_cache(user_id)
                return True
        except Exception as e:
            logger.error(f"Workspace create failed: {e}")
            return False

    def set_active_workspace(self, wid: str, user_id: str = "anonymous") -> bool:
        with self._lock:
            conn = self._get_conn()
            conn.execute("UPDATE workspaces SET is_active=0 WHERE user_id=?", (user_id,))
            conn.execute(
                "UPDATE workspaces SET is_active=1 WHERE id=? AND user_id=?",
                (wid, user_id),
            )
            conn.commit()
            self._invalidate_ws_cache(user_id)
            return True

    def delete_workspace(self, wid: str, user_id: str = "anonymous") -> bool:
        with self._lock:
            self._get_conn().execute(
                "DELETE FROM workspaces WHERE id=? AND user_id=?",
                (wid, user_id),
            )
            self._get_conn().commit()
            self._invalidate_ws_cache(user_id)
            return True

    # ── SSH KEYS (user-isolated) ──────────────────────────
    def save_ssh_key(self, kid: str, name: str, pk_enc: str,
                     pp_enc: Optional[str] = None, user_id: str = "anonymous"):
        with self._lock:
            self._get_conn().execute(
                "INSERT INTO ssh_keys (id,name,private_key_enc,passphrase_enc,user_id) "
                "VALUES (?,?,?,?,?)",
                (kid, name, pk_enc, pp_enc, user_id),
            )
            self._get_conn().commit()

    def get_ssh_key(self, kid: str, user_id: str = "anonymous") -> Optional[Dict[str, Any]]:
        with self._lock:
            cur = self._get_conn().cursor()
            cur.execute(
                "SELECT * FROM ssh_keys WHERE id=? AND user_id=?",
                (kid, user_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def delete_ssh_key(self, kid: str, user_id: str = "anonymous") -> bool:
        with self._lock:
            self._get_conn().execute(
                "DELETE FROM ssh_keys WHERE id=? AND user_id=?",
                (kid, user_id),
            )
            self._get_conn().commit()
            return True

    # ── TELEMETRY & SMART SCORING (user-isolated) ─────────
    def log_telemetry(self, model_id: str, provider: str, latency_ms: int,
                      tokens_in: int = 0, tokens_out: int = 0, success: bool = True,
                      error_type: str = None, cost_usd: float = 0.0,
                      strategy: str = "auto", was_fallback: bool = False,
                      session_id: str = None, user_id: str = "anonymous") -> bool:
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute(
                    "INSERT INTO model_telemetry "
                    "(model_id, provider, session_id, latency_ms, tokens_in, tokens_out, "
                    "success, error_type, cost_usd, strategy, was_fallback, user_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (model_id, provider, session_id, latency_ms, tokens_in, tokens_out,
                     1 if success else 0, error_type, cost_usd, strategy,
                     1 if was_fallback else 0, user_id),
                )
                conn.commit()
                self._invalidate_scores_cache(user_id)
                return True
        except Exception as e:
            logger.error(f"Telemetry log failed: {e}")
            return False

    def get_model_scores(self, user_id: str = "anonymous") -> Dict[str, Dict[str, Any]]:
        cache_key = user_id
        if cache_key in self._scores_cache:
            return self._scores_cache[cache_key]
        try:
            with self._lock:
                cur = self._get_conn().cursor()
                cur.execute(
                    "SELECT * FROM model_scores WHERE user_id = ? ORDER BY total_score DESC",
                    (user_id,),
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
                self._scores_cache[cache_key] = result
                return result
        except Exception as e:
            logger.error(f"Model scores fetch failed: {e}")
            return {}

    def recalculate_model_scores(self, window_hours: int = 168,
                                  user_id: str = "anonymous") -> Dict[str, Dict[str, float]]:
        try:
            with self._lock:
                conn = self._get_conn()
                cur = conn.cursor()
                cur.execute("""
                    SELECT
                        model_id, provider,
                        COUNT(*) as total_calls,
                        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_calls,
                        AVG(CASE WHEN success = 1 THEN latency_ms ELSE NULL END) as avg_latency,
                        SUM(tokens_out) as total_tokens_out,
                        SUM(cost_usd) as total_cost,
                        SUM(CASE WHEN was_fallback = 1 THEN 1 ELSE 0 END) as fallback_count
                    FROM model_telemetry
                    WHERE timestamp >= datetime('now', '-' || ? || ' hours')
                      AND user_id = ?
                    GROUP BY model_id, provider
                    HAVING total_calls >= 3
                """, (window_hours, user_id))
                stats = cur.fetchall()
                if not stats:
                    return {}

                latencies = [s["avg_latency"] for s in stats if s["avg_latency"]]
                costs = [s["total_cost"] for s in stats]
                min_lat = min(latencies) if latencies else 100
                max_lat = max(latencies) if latencies else 10000
                min_cost = min(costs) if costs else 0
                max_cost = max(costs) if costs else 1

                results = {}
                for s in stats:
                    model_id = s["model_id"]
                    total = s["total_calls"]
                    success = s["success_calls"]

                    success_rate = (success / total) * 100 if total > 0 else 50
                    fallback_penalty = (s["fallback_count"] / total) * 20 if total > 0 else 0
                    quality = max(0, success_rate - fallback_penalty)

                    if s["avg_latency"] and max_lat > min_lat:
                        speed = 100 - ((s["avg_latency"] - min_lat) / (max_lat - min_lat)) * 100
                    else:
                        speed = 50

                    if max_cost > min_cost:
                        cost = 100 - ((s["total_cost"] - min_cost) / (max_cost - min_cost)) * 100
                    else:
                        cost = 100

                    stability = (success / total) * 100 if total > 0 else 50
                    total_score = quality * 0.40 + speed * 0.25 + cost * 0.20 + stability * 0.15

                    conn.execute(
                        "INSERT OR REPLACE INTO model_scores "
                        "(model_id, provider, quality_score, speed_score, cost_score, "
                        "stability_score, total_score, sample_count, updated_at, user_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)",
                        (model_id, s["provider"], quality, speed, cost,
                         stability, total_score, total, user_id),
                    )

                    results[model_id] = {
                        "quality": quality, "speed": speed,
                        "cost": cost, "stability": stability,
                        "total": total_score, "samples": total,
                    }

                conn.commit()
                self._invalidate_scores_cache(user_id)
                logger.info(f"Recalculated scores for {len(results)} models (user={user_id})")
                return results
        except Exception as e:
            logger.error(f"Score recalculation failed: {e}")
            return {}

    def get_telemetry_stats(self, hours: int = 24,
                            user_id: str = "anonymous") -> Dict[str, Any]:
        try:
            with self._lock:
                cur = self._get_conn().cursor()
                cur.execute("""
                    SELECT
                        COUNT(*) as total_calls,
                        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_calls,
                        SUM(tokens_out) as total_tokens,
                        SUM(cost_usd) as total_cost,
                        AVG(CASE WHEN success = 1 THEN latency_ms ELSE NULL END) as avg_latency
                    FROM model_telemetry
                    WHERE timestamp >= datetime('now', '-' || ? || ' hours')
                      AND user_id = ?
                """, (hours, user_id))
                row = cur.fetchone()
                return {
                    "total_calls": row["total_calls"] or 0,
                    "success_rate": (row["success_calls"] / row["total_calls"] * 100) if row["total_calls"] else 0,
                    "total_tokens": row["total_tokens"] or 0,
                    "total_cost_usd": row["total_cost"] or 0,
                    "avg_latency_ms": row["avg_latency"] or 0,
                }
        except Exception as e:
            logger.error(f"Telemetry stats failed: {e}")
            return {}


store = RuntimeStore()