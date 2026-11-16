"""
AES-256-GCM encryption service for sensitive credentials (SSH keys, provider API keys).
Uses master key derivation with random salt to guarantee deterministic decryption.
"""
import os
import base64
import logging
from pathlib import Path
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import dotenv_values, set_key
from filelock import FileLock, Timeout as FileLockTimeout

logger = logging.getLogger("runtimeforce.security.crypto")
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = REPO_ROOT / ".env"

class AESCryptoService:
    @staticmethod
    def _get_or_create_master_key() -> bytes:
        ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        lock_path = ENV_PATH.with_name(ENV_PATH.name + ".master-key.lock")
        try:
            with FileLock(str(lock_path), timeout=30):
                os.chmod(lock_path, 0o600)
                # The app-root .env is authoritative; inherited shell variables
                # must never silently select a different database key.
                values = dotenv_values(ENV_PATH)
                master_b64 = values.get("MASTER_KEY")
                if master_b64:
                    try:
                        master_key = base64.b64decode(master_b64, validate=True)
                        if len(master_key) != 32:
                            raise ValueError("MASTER_KEY must decode to exactly 32 bytes")
                        if ENV_PATH.is_file():
                            os.chmod(ENV_PATH, 0o600)
                        return master_key
                    except Exception as exc:
                        logger.error("Failed to load MASTER_KEY: %s", type(exc).__name__)
                        raise
                new_key = AESGCM.generate_key(bit_length=256)
                new_key_b64 = base64.b64encode(new_key).decode("utf-8")
                if not ENV_PATH.exists():
                    ENV_PATH.touch(mode=0o600)
                set_key(str(ENV_PATH), "MASTER_KEY", new_key_b64)
                os.chmod(ENV_PATH, 0o600)
                return new_key
        except FileLockTimeout as exc:
            raise RuntimeError("Timed out waiting for the local master-key lock.") from exc

    @staticmethod
    def _derive_key(master_key: bytes, salt: bytes, jwt_token: Optional[str] = None) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        return kdf.derive(master_key)

    @classmethod
    def encrypt(cls, plaintext: str, jwt_token: Optional[str] = None) -> str:
        if not plaintext:
            return ""
        master_key = cls._get_or_create_master_key()
        salt = os.urandom(16)
        nonce = os.urandom(12)
        derived = cls._derive_key(master_key, salt, jwt_token)
        aesgcm = AESGCM(derived)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        payload = salt + nonce + ciphertext
        return base64.b64encode(payload).decode("utf-8")

    @classmethod
    def decrypt(cls, encoded: str, jwt_token: Optional[str] = None) -> str:
        if not encoded:
            return ""
        try:
            master_key = cls._get_or_create_master_key()
            payload = base64.b64decode(encoded)
            if len(payload) < 28:
                raise ValueError(f"Ciphertext payload too short ({len(payload)} bytes)")
            salt = payload[:16]
            nonce = payload[16:28]
            ciphertext = payload[28:]
            derived = cls._derive_key(master_key, salt, jwt_token)
            aesgcm = AESGCM(derived)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode("utf-8")
        except Exception as e:
            logger.error(f"AES-256-GCM Decryption failed (Payload Len={len(encoded)}): {e}")
            raise ValueError(f"Failed to decrypt credential: {e}")
