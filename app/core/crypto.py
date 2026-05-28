"""
AES-256-GCM encryption for sensitive data (SSH keys, passwords).
Master key is auto-generated and stored in .env with 600 permissions.
"""
import os
import base64
import logging
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import load_dotenv, set_key

logger = logging.getLogger("ai_runtime.crypto")

ENV_PATH = Path(".env")


def _get_or_create_master_key() -> bytes:
    """Returns master key from .env or generates a new one."""
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
    logger.info("Generated new MASTER_KEY and saved to .env")
    return new_key


def _derive_key(master_key: bytes, salt: bytes) -> bytes:
    """Derive encryption key from master key + salt via PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    return kdf.derive(master_key)


def encrypt(plaintext: str) -> str:
    """Encrypts a string and returns base64(salt:nonce:ciphertext)."""
    if not plaintext:
        return ""
    master_key = _get_or_create_master_key()
    salt = os.urandom(16)
    nonce = os.urandom(12)
    derived = _derive_key(master_key, salt)
    aesgcm = AESGCM(derived)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    payload = salt + nonce + ciphertext
    return base64.b64encode(payload).decode("utf-8")


def decrypt(encoded: str) -> str:
    """Decrypts a string encrypted by encrypt()."""
    if not encoded:
        return ""
    try:
        master_key = _get_or_create_master_key()
        payload = base64.b64decode(encoded)
        salt = payload[:16]
        nonce = payload[16:28]
        ciphertext = payload[28:]
        derived = _derive_key(master_key, salt)
        aesgcm = AESGCM(derived)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        raise ValueError("Failed to decrypt data (wrong master key or corrupted)")


def encrypt_password(password: str) -> str:
    return encrypt(password)


def decrypt_password(encoded: str) -> str:
    return decrypt(encoded)


def encrypt_private_key(key_content: str) -> str:
    return encrypt(key_content)


def decrypt_private_key(encoded: str) -> str:
    return decrypt(encoded)
