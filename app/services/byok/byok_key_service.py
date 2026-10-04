"""
BYOK Key Management Service using AES-256-GCM encryption with automatic migration for legacy keys.
"""
import logging
from typing import Dict, Optional
from app.repository.provider_keys_db_repository import ProviderKeysDBRepository
from app.core.security.aes_crypto_service import AESCryptoService
from app.services.billing.license_service import LicenseService

logger = logging.getLogger("runtimeforce.service.byok")

PLAINTEXT_PREFIXES = ("sk-", "gsk_", "AIza", "pplx-", "xai-", "http://", "https://")

class ByokKeyService:
    def __init__(self, keys_repo: ProviderKeysDBRepository, license_service: LicenseService):
        self.keys_repo = keys_repo
        self.license_service = license_service

    def save_key(self, provider: str, plain_key: str, user_id: str, jwt_token: Optional[str] = None):
        encrypted = AESCryptoService.encrypt(plain_key, jwt_token)
        self.keys_repo.save_provider_key(provider, encrypted, user_id)
        logger.info(f"[BYOK] Saved and encrypted API key for provider '{provider}' (User: {user_id})")

    def get_decrypted_keys(self, user_id: str, jwt_token: Optional[str] = None) -> Dict[str, str]:
        encrypted_keys = self.keys_repo.get_all_provider_keys(user_id)
        decrypted = {}

        for provider, enc_key in encrypted_keys.items():
            if not enc_key or not enc_key.strip():
                continue

            if provider in ("ollama", "lm_studio"):
                decrypted[provider] = enc_key
                continue

            is_plaintext = any(enc_key.startswith(p) for p in PLAINTEXT_PREFIXES) or len(enc_key) < 64
            if is_plaintext:
                logger.info(f"[BYOK] Legacy plaintext key detected for provider '{provider}'. Auto-migrating...")
                try:
                    re_encrypted = AESCryptoService.encrypt(enc_key)
                    self.keys_repo.save_provider_key(provider, re_encrypted, user_id)
                    decrypted[provider] = enc_key
                    continue
                except Exception as e:
                    logger.error(f"[BYOK] Auto-migration failed for '{provider}': {e}")
                    continue

            try:
                decrypted_key = AESCryptoService.decrypt(enc_key, jwt_token)
                if decrypted_key:
                    decrypted[provider] = decrypted_key
            except Exception as e:
                logger.error(f"[BYOK] Key for provider '{provider}' is corrupted or decryption failed: {e}")

        return decrypted

    def reencrypt_all_keys(self, user_id: str) -> Dict[str, str]:
        keys = self.get_decrypted_keys(user_id)
        migrated_count = 0
        for provider, plain_key in keys.items():
            if plain_key and provider not in ("ollama", "lm_studio"):
                self.save_key(provider, plain_key, user_id)
                migrated_count += 1
        logger.info(f"[BYOK] Re-encrypted {migrated_count} keys for user {user_id}")
        return {"status": "success", "reencrypted": migrated_count}
