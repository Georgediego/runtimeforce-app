import asyncio
import sqlite3

import pytest

from app.services.terminal.command_approval_service import CommandApprovalService


class SQLiteDB:
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row

    def get_connection(self):
        return self.connection


def test_missing_approval_is_reported_as_expired():
    service = CommandApprovalService(SQLiteDB())

    result = asyncio.run(service.decide("stale-id", "user@example.com", "once"))

    assert result == {"status": "expired"}


def test_duplicate_decision_is_idempotent():
    service = CommandApprovalService(SQLiteDB())
    future = asyncio.get_event_loop_policy().new_event_loop().create_future()
    service._pending["pending-1"] = {
        "pending_id": "pending-1",
        "user_id": "user@example.com",
        "session_id": "session-1",
        "project_id": "project-1",
        "workspace_id": "workspace-1",
        "target": "local",
        "command": "pwd",
        "command_hash": "hash",
        "cwd": "/workspace",
        "future": future,
    }

    async def decide_twice():
        first = await service.decide("pending-1", "user@example.com", "once")
        second = await service.decide("pending-1", "user@example.com", "once")
        return first, second

    try:
        first, second = asyncio.run(decide_twice())
    finally:
        future.get_loop().close()

    assert first == {"status": "approved"}
    assert second == {"status": "expired"}


def test_approval_cannot_be_decided_by_another_user():
    service = CommandApprovalService(SQLiteDB())
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    service._pending["pending-2"] = {
        "pending_id": "pending-2",
        "user_id": "owner@example.com",
        "session_id": "session-2",
        "project_id": "",
        "workspace_id": "",
        "target": "local",
        "command": "pwd",
        "command_hash": "hash",
        "cwd": "",
        "future": future,
    }

    async def decide_as_other_user():
        with pytest.raises(KeyError):
            await service.decide("pending-2", "other@example.com", "once")

    try:
        loop.run_until_complete(decide_as_other_user())
    finally:
        loop.close()
