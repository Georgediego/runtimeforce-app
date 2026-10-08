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

For the full legal text, please see the LICENSE file in this repository.
