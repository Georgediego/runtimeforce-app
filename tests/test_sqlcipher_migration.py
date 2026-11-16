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


def _read_encrypted_value(path: Path, key: bytes, table: str, column: str):
    conn = sqlcipher3.connect(str(path))
    try:
        conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
        return conn.execute(f"SELECT {column} FROM {table}").fetchone()[0]
    finally:
        conn.close()


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


def test_plain_database_is_migrated_and_all_legacy_tables_are_preserved(tmp_path):
    database = tmp_path / "runtime.db"
    legacy = sqlite3.connect(str(database))
    legacy_tables = (
        "legacy_private_data",
        "project_oauth_tokens",
        "social_post_drafts",
        "social_feedback_items",
    )
    for table in legacy_tables:
        legacy.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        legacy.execute(f"INSERT INTO {table}(value) VALUES (?)", (f"preserved-{table}",))
    legacy.commit()
    legacy.close()

    manager = DatabaseConnectionManager(str(database), master_key=TEST_MASTER_KEY)
    conn = manager.get_connection()

    for table in legacy_tables:
        row = conn.execute(f"SELECT value FROM {table} WHERE id=1").fetchone()
        assert row[0] == f"preserved-{table}"

    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    manager.close()

    backups = list(tmp_path.glob("runtime.db.pre-sqlcipher-*.enc"))
    assert len(backups) == 1
    _assert_not_readable_as_plain_sqlite(database)
    _assert_not_readable_as_plain_sqlite(backups[0])
    assert _read_encrypted_value(
        backups[0], TEST_MASTER_KEY, "legacy_private_data", "value"
    ) == "preserved-legacy_private_data"


def test_encrypted_database_reopens_with_same_key(tmp_path):
    database = tmp_path / "runtime.db"
    manager = DatabaseConnectionManager(str(database), master_key=TEST_MASTER_KEY)
    conn = manager.get_connection()
    conn.execute(
        "INSERT INTO sessions (id, title, user_id) VALUES (?, ?, ?)",
        ("session-1", "Persisted session", "test-user"),
    )
    conn.commit()
    manager.close()

    reopened = DatabaseConnectionManager(str(database), master_key=TEST_MASTER_KEY)
    assert reopened.get_connection().execute(
        "SELECT title FROM sessions WHERE id='session-1'"
    ).fetchone()[0] == "Persisted session"
    reopened.close()


def test_wrong_master_key_does_not_replace_encrypted_database(tmp_path):
    database = tmp_path / "runtime.db"
    manager = DatabaseConnectionManager(str(database), master_key=TEST_MASTER_KEY)
    manager.get_connection().execute(
        "INSERT INTO sessions (id, title, user_id) VALUES (?, ?, ?)",
        ("session-1", "Keep this data", "test-user"),
    )
    manager.get_connection().commit()
    manager.close()
    original = database.read_bytes()

    with pytest.raises(RuntimeError, match="original database was preserved"):
        DatabaseConnectionManager(str(database), master_key=b"wrong-master-key-32-bytes-long!!")

    assert database.read_bytes() == original


def test_corrupt_legacy_database_is_not_replaced(tmp_path):
    database = tmp_path / "runtime.db"
    original = b"not a valid sqlite database"
    database.write_bytes(original)

    with pytest.raises(RuntimeError, match="original database was preserved"):
        DatabaseConnectionManager(str(database), master_key=TEST_MASTER_KEY)

    assert database.read_bytes() == original
    assert not list(tmp_path.glob("runtime.db.pre-sqlcipher-*.enc"))
