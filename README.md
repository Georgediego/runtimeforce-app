# RuntimeForce IDE

RuntimeForce is a local-first development environment for coding with AI models, editing local or SSH workspaces, and using Git and a guarded terminal from one interface. The local application runs on your machine; the hosted server provides accounts, subscription state, and the optional Managed AI Proxy.

## Requirements

- Python 3.10 or newer
- Git
- A supported desktop operating system (Linux, macOS, or Windows)

## Run locally

```bash
git clone https://github.com/Georgediego/runtimeforce-app.git
cd runtimeforce-app
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On Windows PowerShell, create and activate the environment with `python -m venv venv` and `venv\Scripts\Activate.ps1`, then run the same `python -m pip` and `python -m uvicorn` commands.

Open <http://127.0.0.1:8000>. The app creates its SQLite database in the operating system's user data directory. It stores workspace metadata, chat history, local preferences, and encrypted provider/SSH credentials there. Back up the database and its local encryption key together; losing the key makes stored credentials unreadable.

## Main capabilities

- Local and SSH workspaces with file, Git, and terminal tools.
- Direct BYOK calls to configured model providers and local model runtimes.
- Optional server Managed AI Proxy for supported plans.
- Browser chat, project context and rules, model selection, local memory, and usage views.

The selected-model allowlist is persisted in the local database and enforced by the app's backend routing path. Provider model IDs and model availability can change independently of this README.

## Project documentation

- [Workspace project context](../Project_Context.md) is the canonical cross-repository architecture and API reference.
- [App-specific context](Project_Context.md) summarizes the local client.
- [Roadmap](Roadmap.md) separates current priorities from implemented behavior.
- [Changelog](CHANGELOG.md) records released and unreleased changes.

## Development checks

Run the relevant tests from this repository:

```bash
pytest tests/ -q
```

Do not commit, push, or deploy automatically. Keep code, UI text, comments, and logs in English; use Russian for project documentation and user communication.
