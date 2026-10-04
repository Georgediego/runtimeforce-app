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
from dotenv import load_dotenv, set_key

logger = logging.getLogger("runtimeforce.security.crypto")
ENV_PATH = Path(".env")

class AESCryptoService:
    @staticmethod
    def _get_or_create_master_key() -> bytes:
        load_dotenv(ENV_PATH)
        master_b64 = os.getenv("MASTER_KEY")
        if master_b64:
            try:
                return base64.b64decode(master_b64)
            except Exception as e:
                logger.error(f"Failed to decode MASTER_KEY: {e}")
                raise
        new_key = AESGCM.generate_key(bit_length=256)
        new_key_b64 = base64.b64encode(new_key).decode("utf-8")
        if not ENV_PATH.exists():
            ENV_PATH.touch(mode=0o600)
        set_key(str(ENV_PATH), "MASTER_KEY", new_key_b64)
        try:
            os.chmod(ENV_PATH, 0o600)
        except Exception:
            pass
        return new_key

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
