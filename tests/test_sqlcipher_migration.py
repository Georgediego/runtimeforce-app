import multiprocessing
import sqlite3
from pathlib import Path

import pytest
import sqlcipher3

from app.core.security import aes_crypto_service

from app.repository.db_connection import DatabaseConnectionManager, _derive_database_key


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
        database_key = _derive_database_key(key)
        conn.execute(f"PRAGMA key = \"x'{database_key.hex()}'\"")
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



def _concurrent_migration_worker(database: str, row_id: str, barrier) -> None:
    barrier.wait(timeout=15)
    manager = DatabaseConnectionManager(database, master_key=TEST_MASTER_KEY)
    try:
        connection = manager.get_connection()
        connection.execute(
            "INSERT INTO sessions (id, title, user_id) VALUES (?, ?, ?)",
            (row_id, f"Concurrent {row_id}", "test-user"),
        )
        connection.commit()
    finally:
        manager.close()


def test_two_processes_cannot_race_database_migration(tmp_path):
    database = tmp_path / "runtime.db"
    legacy = sqlite3.connect(str(database))
    legacy.execute(
        "CREATE TABLE legacy_data (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
    )
    legacy.execute("INSERT INTO legacy_data(value) VALUES ('must-survive')")
    legacy.commit()
    legacy.close()

    context = multiprocessing.get_context("fork")
    barrier = context.Barrier(2)
    processes = [
        context.Process(
            target=_concurrent_migration_worker,
            args=(str(database), f"process-{index}", barrier),
        )
        for index in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)

    for process in processes:
        if process.is_alive():
            process.terminate()
            process.join()
        assert process.exitcode == 0

    manager = DatabaseConnectionManager(str(database), master_key=TEST_MASTER_KEY)
    try:
        connection = manager.get_connection()
        assert connection.execute(
            "SELECT value FROM legacy_data WHERE id=1"
        ).fetchone()[0] == "must-survive"
        rows = connection.execute(
            "SELECT id FROM sessions WHERE id LIKE 'process-%' ORDER BY id"
        ).fetchall()
        assert [row[0] for row in rows] == ["process-0", "process-1"]
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        manager.close()



def test_master_key_comes_from_app_root_env_not_inherited_environment(tmp_path, monkeypatch):
    master_key = b"0123456789abcdef0123456789abcdef"
    inherited_key = b"fedcba9876543210fedcba9876543210"
    encoded = __import__("base64").b64encode(master_key).decode("ascii")
    env_file = tmp_path / ".env"
    env_file.write_text(f"MASTER_KEY={encoded}\n", encoding="utf-8")
    monkeypatch.setattr(aes_crypto_service, "ENV_PATH", env_file)
    monkeypatch.setattr(aes_crypto_service, "_legacy_env_paths", lambda: [])
    monkeypatch.setenv(
        "MASTER_KEY",
        __import__("base64").b64encode(inherited_key).decode("ascii"),
    )

    assert aes_crypto_service.AESCryptoService._get_or_create_master_key() == master_key


def test_master_key_is_created_once_when_app_root_env_has_no_key(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER_SETTING=preserved\n", encoding="utf-8")
    monkeypatch.setattr(aes_crypto_service, "ENV_PATH", env_file)
    monkeypatch.setattr(aes_crypto_service, "_legacy_env_paths", lambda: [])
    monkeypatch.delenv("MASTER_KEY", raising=False)

    first = aes_crypto_service.AESCryptoService._get_or_create_master_key()
    second = aes_crypto_service.AESCryptoService._get_or_create_master_key()

    assert len(first) == 32
    assert second == first
    assert "OTHER_SETTING=preserved" in env_file.read_text(encoding="utf-8")



def test_master_key_migrates_from_legacy_user_install_without_changing_key(tmp_path, monkeypatch):
    import base64

    key = b"0123456789abcdef0123456789abcdef"
    legacy = tmp_path / "legacy" / ".env"
    target = tmp_path / "config" / "runtimeforce" / ".env"
    legacy.parent.mkdir()
    legacy.write_text(
        f"MASTER_KEY={base64.b64encode(key).decode('ascii')}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(aes_crypto_service, "ENV_PATH", target)
    monkeypatch.setattr(aes_crypto_service, "_legacy_env_paths", lambda: [legacy])

    assert aes_crypto_service.AESCryptoService._get_or_create_master_key() == key
    assert base64.b64decode(
        __import__("dotenv").dotenv_values(target)["MASTER_KEY"]
    ) == key
    assert legacy.exists()
    assert target.stat().st_mode & 0o777 == 0o600


def test_conflicting_legacy_master_keys_fail_closed(tmp_path, monkeypatch):
    import base64

    first_key = b"0123456789abcdef0123456789abcdef"
    second_key = b"fedcba9876543210fedcba9876543210"
    legacy_a = tmp_path / "old-a.env"
    legacy_b = tmp_path / "old-b.env"
    target = tmp_path / "config" / ".env"
    legacy_a.write_text(f"MASTER_KEY={base64.b64encode(first_key).decode('ascii')}\n")
    legacy_b.write_text(f"MASTER_KEY={base64.b64encode(second_key).decode('ascii')}\n")
    monkeypatch.setattr(aes_crypto_service, "ENV_PATH", target)
    monkeypatch.setattr(
        aes_crypto_service, "_legacy_env_paths", lambda: [legacy_a, legacy_b]
    )

    with pytest.raises(RuntimeError, match="Conflicting RuntimeForce MASTER_KEY"):
        aes_crypto_service.AESCryptoService._get_or_create_master_key()

    assert not target.exists()

