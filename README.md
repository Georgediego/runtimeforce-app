# RuntimeForce IDE

RuntimeForce is a local-first AI development environment for software engineering, local and SSH workspaces, terminal operations, Git workflows, and project memory.

## Privacy and architecture

RuntimeForce IDE runs on the user's computer. The RuntimeForce SaaS at [runtimeforce.dev](https://runtimeforce.dev) is the official control plane for account authentication, subscriptions, billing, and dynamic feature entitlements.

**Data that stays on the user's computer**
- Source code, project files, workspace contents, prompts, chat history, and project memory.
- SSH credentials and local workspace configuration.
- BYOK provider API keys and local-model configuration.
- Local SQLite database and encryption master key.

**Network boundaries**
- Authentication and subscription/entitlement checks are sent to the official `https://runtimeforce.dev` service over HTTPS.
- AI prompts and context are sent directly from the IDE to the AI provider selected by the user, using the user's own API key (BYOK), or to a local model runtime.
- RuntimeForce SaaS does not receive project source code, prompts, workspace files, SSH credentials, or BYOK provider API keys.
- Social OAuth credentials connected through RuntimeForce accounts are stored by the SaaS in encrypted form, as described in the RuntimeForce Privacy Policy.

## Authentication, entitlements, and local encryption

- The SaaS server is the authority for account identity, subscription status, plan features, and limits.
- The IDE must not treat locally decoded JWT claims or locally edited plan values as proof of entitlement. The server verifies the bearer token and returns current entitlements through `GET /api/v1/billing/entitlements`.
- When the server cannot verify a session, protected operations fail closed. A bounded offline grace period may use only previously server-verified entitlement data, according to the plan's configured limit.
- Local credentials are encrypted with AES-256-GCM. The encryption master key is generated and stored locally; it is not sent to RuntimeForce.
- A local user can modify software running on their own computer. The security boundary is therefore server-side verification of protected account, subscription, and SaaS operations—not a claim that local files are impossible to patch.

## Plans

Plan codes, features, and limits are dynamic and managed from the RuntimeForce Admin panel. The IDE reads the authoritative feature map and limits from the entitlements API; it does not rely on hardcoded tier names.

## Installation

Public installers and the website download always install the stable `main` branch.

### Linux / macOS

```bash
curl -fsSL https://runtimeforce.dev/install.sh | bash
```

### Windows (PowerShell)

```powershell
irm https://runtimeforce.dev/install.ps1 | iex
```

The IDE is started locally and is available at `http://127.0.0.1:8000`.

## Requirements

- Python 3.11+
- Git
- Linux, macOS, or Windows
- Internet connection for RuntimeForce account authentication and online entitlement checks
- An AI provider API key (BYOK) or a configured local model runtime to use AI features

## Development

The current integration branch is `dev`. The public installer must remain pinned to `main`.

```bash
git clone --branch dev https://github.com/Georgediego/runtimeforce-app.git
cd runtimeforce-app
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On Windows, activate the environment with `venv\\Scripts\\Activate.ps1`.

See [DEVELOPMENT.md](DEVELOPMENT.md) and [Project_Context.md](Project_Context.md).

## License

RuntimeForce IDE is distributed under the **Business Source License 1.1 (BUSL-1.1)**. It is source-available, not an OSI-approved open-source license. The license permits inspection and non-production use under its terms, with a limited Additional Use Grant for production use through the official RuntimeForce backend. Competing hosted/embedded offerings are not permitted under that grant.

The Additional Use Grant does not route AI traffic through RuntimeForce: BYOK requests go directly to the provider selected by the user, and local models remain local. See the complete [LICENSE](LICENSE) file.
