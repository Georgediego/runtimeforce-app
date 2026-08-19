# 🚀 RuntimeForce IDE

**RuntimeForce** is a lightweight, specialized AI development environment and orchestration runtime designed for local and remote SSH engineering workflows.

An intelligent, unified AI interface handles coding, refactoring, terminal execution, and Git operations directly inside your local environment.

---

## 💡 Key Features

* **Unified AI Experience:** Interact with RuntimeForce logic while models (OpenAI, Anthropic, Gemini, Groq, Ollama, xAI) act as interchangeable execution backends.
* **Local & SSH Workspaces:** Edit files locally or execute commands over remote SSH connections with built-in connection pooling.
* **Terminal & Git Integration:** Native terminal command execution (SafeShell filtered) and Git change inspection, diffing, and commits.
* **Data Sovereignty (Zero Trust):** Source code, chat histories, SSH credentials, and API keys are stored **strictly locally** on your machine in encrypted SQLite (`~/.local/share/runtimeforce/runtime.db`).
* **Multi-Model Orchestration:** Support for AUTO, PROGRAMMING, LOCAL, MANUAL, and CONSILIUM execution strategies.

---

## ⚡ Quick Start & Installation

Install and run `runtimeforce-app` on your local machine or private dev VPS.

### System Requirements
* **Python:** 3.11 or higher
* **Git:** Installed and available in system PATH
* **OS:** Windows 10/11, macOS 12+, Linux (Ubuntu 20.04+, Debian, Fedora, Arch)

---

### 🐧 Linux & 🍎 macOS Installation

1. Clone the latest release:
   ```bash
   git clone -b latest https://github.com/Georgediego/runtimeforce-app.git
   cd runtimeforce-app

2.  Create virtual environment and install dependencies:

    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

3.  Launch RuntimeForce IDE:

    python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

4.  Open http://localhost:8000 in your web browser.

🪟 Windows Installation (PowerShell)

1.  Clone the latest release:

    git clone -b latest https://github.com/Georgediego/runtimeforce-app.git
    cd runtimeforce-app

2.  Create virtual environment and install dependencies:

    python -m venv venv
    .\venv\Scripts\Activate.ps1
    pip install -r requirements.txt

3.  Launch RuntimeForce IDE:

    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

4.  Open http://localhost:8000 in your web browser.

🔒 Security & Data Sovereignty

  - AES-256-GCM Local Encryption: Sensitive credentials (SSH keys, provider API
    keys) are encrypted using AES-256-GCM with JWT signature key derivation.
  - Zero Source Code Upload: Your code, context, and prompts are processed
    locally or sent directly to BYOK providers without centralized logging.

📄 License

RuntimeForce is distributed under the Business Source License (BSL) 1.1.

This is a Source-Available license, not a traditional Open Source license. It is
designed to provide full transparency for our Zero Trust architecture while
protecting the commercial viability of the project.

What you CAN do:

  - Read the source code to verify security, data privacy, and architecture.
  - Build and run the application locally for your own personal, non-commercial
    use in accordance with our terms.
  - Contribute to the project (bug reports, pull requests).

What you CANNOT do:

  - Modify the code to bypass billing, subscription checks, or tier restrictions
    (e.g., unlocking the Studio tier for free).
  - Host, distribute, or offer RuntimeForce (or modified versions of it) as a
    commercial service or a competing product.
  - Remove or obfuscate any licensing and copyright notices.

For the full legal text, please see the LICENSE file in this repository. EOF

cat << 'EOF' > /home/dm/ai-runtime/app/core/security/aes_crypto_service.py """
AES-256-GCM encryption service for sensitive credentials (SSH keys, provider API
keys). Binds key derivation to valid server JWT tokens for BYOK protection. """
import os import base64 import logging from pathlib import Path from typing
import Optional from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes from
cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC from dotenv import
load_dotenv, set_key

logger = logging.getLogger("runtimeforce.security.crypto") ENV_PATH =
Path(".env")

class AESCryptoService: @staticmethod def _get_or_create_master_key() -> bytes:
load_dotenv(ENV_PATH) master_b64 = os.getenv("MASTER_KEY") if master_b64: try:
return base64.b64decode(master_b64) except Exception as e: logger.error(f"Failed
to decode MASTER_KEY: {e}") raise new_key = AESGCM.generate_key(bit_length=256)
new_key_b64 = base64.b64encode(new_key).decode("utf-8") if not
ENV_PATH.exists(): ENV_PATH.touch(mode=0o600) set_key(str(ENV_PATH),
"MASTER_KEY", new_key_b64) try: os.chmod(ENV_PATH, 0o600) except Exception: pass
return new_key

@staticmethod
def _derive_key(master_key: bytes, salt: bytes, jwt_token: Optional[str] = None) -> bytes:
    token_entropy = b""
    if jwt_token and "." in jwt_token:
        try:
            parts = jwt_token.split(".")
            if len(parts) == 3:
                token_entropy = parts[2].encode("utf-8")
        except Exception:
            pass

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt + token_entropy[:16],
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
        salt = payload[:16]
        nonce = payload[16:28]
        ciphertext = payload[28:]
        derived = cls._derive_key(master_key, salt, jwt_token)
        aesgcm = AESGCM(derived)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        raise ValueError("Failed to decrypt data: invalid license or corrupted key")

