import os
import tempfile
import pytest

from app.repository.db_connection import DatabaseConnectionManager
from app.repository.provider_keys_db_repository import ProviderKeysDBRepository
from app.services.byok.byok_key_service import ByokKeyService

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_manager = DatabaseConnectionManager(db_path=path)
    db_manager.init_db()
    yield db_manager
    try:
        os.remove(path)
    except Exception:
        pass

def test_byok_persistence_and_restart(temp_db):
    repo1 = ProviderKeysDBRepository(temp_db)
    service1 = ByokKeyService(repo1)

    user_id = "user_test_1"
    raw_key = "sk-proj-testkey123456789"
    service1.save_key("openai", raw_key, user_id)

    # Simulate restart by creating new repository and service instances
    repo2 = ProviderKeysDBRepository(temp_db)
    service2 = ByokKeyService(repo2)

    decrypted = service2.get_decrypted_keys(user_id)
    assert decrypted.get("openai") == raw_key

def test_byok_user_isolation(temp_db):
    repo = ProviderKeysDBRepository(temp_db)
    service = ByokKeyService(repo)

    user_a = "user_alice"
    user_b = "user_bob"

    service.save_key("anthropic", "sk-ant-alice-key-9999", user_a)
    service.save_key("anthropic", "sk-ant-bob-key-1111", user_b)

    keys_a = service.get_decrypted_keys(user_a)
    keys_b = service.get_decrypted_keys(user_b)

    assert keys_a.get("anthropic") == "sk-ant-alice-key-9999"
    assert keys_b.get("anthropic") == "sk-ant-bob-key-1111"

def test_legacy_plaintext_migration(temp_db):
    repo = ProviderKeysDBRepository(temp_db)
    service = ByokKeyService(repo)

    user_id = "user_legacy"
    legacy_key = "sk-or-v1-plaintextlegacykey"

    # Manually insert plaintext into DB (simulating legacy database entry)
    conn = temp_db.get_connection()
    conn.execute(
        "INSERT INTO provider_keys (provider, key_enc, user_id) VALUES (?, ?, ?)",
        ("openrouter", legacy_key, user_id)
    )
    conn.commit()

    # Getting decrypted keys should trigger auto-migration to encrypted storage
    decrypted = service.get_decrypted_keys(user_id)
    assert decrypted.get("openrouter") == legacy_key

    # Check that in DB it is no longer plaintext
    raw_db_keys = repo.get_all_provider_keys(user_id)
    stored_enc = raw_db_keys.get("openrouter")
    assert stored_enc != legacy_key
