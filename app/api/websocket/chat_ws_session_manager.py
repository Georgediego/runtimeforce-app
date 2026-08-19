"""
Manager for tracking and cancelling active WebSocket Chat Tasks.
"""
import asyncio
from typing import Dict

class ChatWSSessionManager:
    def __init__(self):
        self._sessions: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str, task: asyncio.Task) -> None:
        async with self._lock:
            prev = self._sessions.get(session_id)
            if prev and not prev.done():
                prev.cancel()
            self._sessions[session_id] = task

    async def cancel(self, session_id: str) -> bool:
        async with self._lock:
            task = self._sessions.get(session_id)
            if not task or task.done():
                return False
            task.cancel()
            return True

    def unregister(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

session_manager = ChatWSSessionManager()
