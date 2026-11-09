"""Fail-closed, local command approval gate for local and SSH workspace drivers."""
import asyncio
import hashlib
import secrets
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Optional

class CommandApprovalService:
    def __init__(self, db):
        self.db = db
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._session_grants = set()
        self._lock = asyncio.Lock()
        self._context = ContextVar("rf_command_approval_context", default={})
        conn = self.db.get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS command_approval_grants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                command_hash TEXT NOT NULL,
                target TEXT NOT NULL,
                scope TEXT NOT NULL CHECK(scope IN ('always','workspace','project')),
                scope_id TEXT NOT NULL DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, command_hash, target, scope, scope_id)
            )
        """)
        conn.commit()

    @contextmanager
    def context(self, **values):
        token = self._context.set({**self._context.get(), **values})
        try:
            yield
        finally:
            self._context.reset(token)

    @staticmethod
    def _hash(command: str) -> str:
        return hashlib.sha256(command.encode("utf-8")).hexdigest()

    def _has_persistent_grant(self, user_id, digest, target, workspace_id, project_id):
        conn = self.db.get_connection()
        row = conn.execute("""
            SELECT 1 FROM command_approval_grants
            WHERE user_id=? AND command_hash=? AND target=? AND (
                (scope='always' AND scope_id='') OR
                (scope='workspace' AND scope_id=?) OR
                (scope='project' AND scope_id=?)
            ) LIMIT 1
        """, (user_id, digest, target, workspace_id or "", project_id or "")).fetchone()
        return row is not None

    async def require_approval(self, command: str, metadata: Optional[dict] = None, cwd: Optional[str] = None):
        if not isinstance(command, str) or not command.strip():
            raise PermissionError("Empty shell command is not allowed.")
        details = {**(metadata or {}), **self._context.get()}
        user_id = str(details.get("user_id") or "anonymous")
        session_id = str(details.get("session_id") or "")
        project_id = str(details.get("project_id") or "")
        workspace_id = str(details.get("workspace_id") or "")
        target = str(details.get("target") or "local")
        digest = self._hash(command)

        if self._has_persistent_grant(user_id, digest, target, workspace_id, project_id):
            return
        session_key = (user_id, session_id, digest, target)
        if session_id and session_key in self._session_grants:
            return

        loop = asyncio.get_running_loop()
        pending_id = secrets.token_urlsafe(18)
        future = loop.create_future()
        record = {
            "pending_id": pending_id, "user_id": user_id, "session_id": session_id,
            "project_id": project_id, "workspace_id": workspace_id, "target": target,
            "command": command, "command_hash": digest, "cwd": cwd or details.get("cwd") or "",
            "future": future,
        }
        async with self._lock:
            duplicate = any(
                item["user_id"] == user_id
                and item["session_id"] == session_id
                and item["command_hash"] == digest
                and item["target"] == target
                for item in self._pending.values()
            )
            if duplicate:
                raise PermissionError("This exact command is already awaiting approval.")
            self._pending[pending_id] = record
        try:
            approved = await asyncio.wait_for(future, timeout=300)
        except asyncio.TimeoutError:
            async with self._lock:
                self._pending.pop(pending_id, None)
            raise PermissionError("Command approval timed out. The command was not executed.")
        if not approved:
            raise PermissionError("Command execution was denied by the user.")

    async def list_pending(self, user_id: str):
        async with self._lock:
            return [{
                key: value for key, value in item.items()
                if key not in ("future", "command_hash", "user_id")
            } for item in self._pending.values() if item["user_id"] == user_id]

    async def decide(self, pending_id: str, user_id: str, choice: str):
        allowed = {"once", "session", "workspace", "project", "always", "deny"}
        if choice not in allowed:
            raise ValueError("Invalid approval choice.")
        async with self._lock:
            item = self._pending.get(pending_id)
            if not item or item["user_id"] != user_id:
                raise KeyError("Pending command approval not found.")
            if item["future"].done():
                raise KeyError("This command approval has already been decided.")
            if choice == "session":
                if not item["session_id"]:
                    raise ValueError("Session scope is unavailable for this command.")
                self._session_grants.add((user_id, item["session_id"], item["command_hash"], item["target"]))
            elif choice in ("workspace", "project", "always"):
                scope_id = item["workspace_id"] if choice == "workspace" else item["project_id"] if choice == "project" else ""
                if choice != "always" and not scope_id:
                    raise ValueError(f"{choice.title()} scope is unavailable for this command.")
                conn = self.db.get_connection()
                conn.execute("""
                    INSERT OR IGNORE INTO command_approval_grants
                    (user_id, command_hash, target, scope, scope_id) VALUES (?, ?, ?, ?, ?)
                """, (user_id, item["command_hash"], item["target"], choice, scope_id or ""))
                conn.commit()
            item["future"].set_result(choice != "deny")
            self._pending.pop(pending_id, None)
        return {"status": "approved" if choice != "deny" else "denied"}

    async def close_session(self, session_id: str):
        async with self._lock:
            self._session_grants = {g for g in self._session_grants if g[1] != session_id}
            for key, item in list(self._pending.items()):
                if item["session_id"] == session_id:
                    if not item["future"].done():
                        item["future"].set_result(False)
                    self._pending.pop(key, None)

    async def close_all(self):
        async with self._lock:
            for item in self._pending.values():
                if not item["future"].done():
                    item["future"].set_result(False)
            self._pending.clear()
            self._session_grants.clear()
