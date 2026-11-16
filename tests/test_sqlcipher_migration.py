import sqlite3
from pathlib import Path

import pytest
import sqlcipher3

from app.repository.db_connection import DatabaseConnectionManager


TEST_MASTER_KEY = b"runtimeforce-test-master-key-32!"


def _assert_not_readable_as_plain_sqlite(path: Path) -> None:
    plain = sqlite3.connect(str(path))
    try:
        with pytest.raises(sqlite3.DatabaseError):
            plain.execute("SELECT name FROM sqlite_master").fetchall()
    finally:
        plain.close()


def test_new_database_is_created_with_sqlcipher(tmp_path):
    database = tmp_path / "runtime.db"
    manager = DatabaseConnectionManager(str(database), master_key=TEST_MASTER_KEY)

    conn = manager.get_connection()
    conn.execute(
        "INSERT INTO sessions (id, title, user_id) VALUES (?, ?, ?)",
        ("session-1", "Encrypted session", "test-user"),
    )
    conn.commit()

    assert conn.execute("PRAGMA cipher_version").fetchone()[0]
    assert conn.execute("SELECT title FROM sessions WHERE id='session-1'").fetchone()[0] == "Encrypted session"
    manager.close()
    _assert_not_readable_as_plain_sqlite(database)


def test_plain_database_is_migrated_without_losing_data(tmp_path):
    database = tmp_path / "runtime.db"
    legacy = sqlite3.connect(str(database))
    legacy.execute(
        "CREATE TABLE legacy_private_data (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
    )
    legacy.execute(
        "INSERT INTO legacy_private_data(value) VALUES (?)",
        ("preserve-this-user-data",),
    )
    legacy.commit()
    legacy.close()

    manager = DatabaseConnectionManager(str(database), master_key=TEST_MASTER_KEY)
    conn = manager.get_connection()

    row = conn.execute("SELECT value FROM legacy_private_data WHERE id=1").fetchone()
    assert row[0] == "preserve-this-user-data"
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    manager.close()

    backups = list(tmp_path.glob("runtime.db.pre-sqlcipher-*.enc"))
    assert len(backups) == 1
    _assert_not_readable_as_plain_sqlite(database)
    _assert_not_readable_as_plain_sqlite(backups[0])


def test_corrupt_legacy_database_is_not_replaced(tmp_path):
    database = tmp_path / "runtime.db"
    original = b"not a valid sqlite database"
    database.write_bytes(original)

    with pytest.raises(RuntimeError, match="original database was preserved"):
        DatabaseConnectionManager(str(database), master_key=TEST_MASTER_KEY)

    assert database.read_bytes() == original
    assert not list(tmp_path.glob("runtime.db.pre-sqlcipher-*.enc"))
