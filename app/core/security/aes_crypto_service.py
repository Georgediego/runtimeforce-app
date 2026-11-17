"""
AES-256-GCM encryption service for sensitive credentials (SSH keys, provider API keys).
Uses a per-user master key stored outside the application installation directory.
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
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")).expanduser()
ENV_PATH = CONFIG_HOME / "runtimeforce" / ".env"


def _legacy_env_paths() -> list[Path]:
    """Locations used by older per-user installs before config moved to XDG."""
    candidates = (REPO_ROOT / ".env", Path.home() / ".runtimeforce" / ".env")
    result = []
    for candidate in candidates:
        candidate = candidate.expanduser()
        if candidate != ENV_PATH and candidate not in result:
            result.append(candidate)
    return result


def _decode_master_key(value: str, source: Path) -> bytes:
    try:
        key = base64.b64decode(value, validate=True)
        if len(key) != 32:
            raise ValueError("MASTER_KEY must decode to exactly 32 bytes")
        return key
    except Exception as exc:
        logger.error("Invalid MASTER_KEY in %s: %s", source, type(exc).__name__)
        raise RuntimeError(
            f"Invalid RuntimeForce MASTER_KEY in {source}. "
            "The existing key was not replaced."
        ) from exc


class AESCryptoService:
    @staticmethod
    def _get_or_create_master_key() -> bytes:
        ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(ENV_PATH.parent, 0o700)
        except OSError:
            pass

        lock_path = ENV_PATH.with_name(ENV_PATH.name + ".master-key.lock")
        try:
            with FileLock(str(lock_path), timeout=30):
                os.chmod(lock_path, 0o600)

                # The XDG config file is authoritative. Never use an inherited
                # MASTER_KEY environment variable to select a database key.
                values = dotenv_values(ENV_PATH)
                master_b64 = values.get("MASTER_KEY")
                if master_b64:
                    master_key = _decode_master_key(str(master_b64), ENV_PATH)
                    os.chmod(ENV_PATH, 0o600)
                    return master_key

                # Migrate keys from old source-tree and install.sh locations.
                # If old locations disagree, stop rather than risk the wrong key.
                legacy_keys = []
                for legacy_path in _legacy_env_paths():
                    if not legacy_path.is_file():
                        continue
                    legacy_value = dotenv_values(legacy_path).get("MASTER_KEY")
                    if legacy_value:
                        legacy_keys.append(
                            (legacy_path, _decode_master_key(str(legacy_value), legacy_path))
                        )

                if legacy_keys:
                    first_key = legacy_keys[0][1]
                    if any(key != first_key for _, key in legacy_keys[1:]):
                        raise RuntimeError(
                            "Conflicting RuntimeForce MASTER_KEY values were found in "
                            "legacy locations. No key was changed; resolve the conflict "
                            "before starting RuntimeForce."
                        )
                    master_key = first_key
                else:
                    master_key = AESGCM.generate_key(bit_length=256)

                # Preserve unrelated values already present in the new config file.
                if not ENV_PATH.exists():
                    ENV_PATH.touch(mode=0o600)
                set_key(
                    str(ENV_PATH),
                    "MASTER_KEY",
                    base64.b64encode(master_key).decode("ascii"),
                )
                os.chmod(ENV_PATH, 0o600)
                return master_key
        except FileLockTimeout as exc:
            raise RuntimeError(
                "Timed out waiting for the local master-key lock."
            ) from exc

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
