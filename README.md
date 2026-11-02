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

## Authentication and entitlements

- The SaaS server is the authority for account identity, subscription status, plan features, and limits.
- The IDE does not treat locally decoded JWT claims or locally edited plan values as proof of entitlement. The server verifies the bearer token and returns current entitlements through `GET /api/v1/billing/entitlements`.
- When the server cannot verify a session, protected operations fail closed. A bounded offline grace period may use only previously server-verified entitlement data.
- The current implementation verifies sessions online through the official `/api/v1/auth/me` endpoint and obtains entitlements from `/api/v1/billing/entitlements`. Offline use relies on a bounded in-memory cache of previously verified entitlements.
- A local user can modify software running on their own computer. Protected account, subscription, and SaaS operations are therefore verified server-side.

## Installation

Public installers and the website download install the stable `main` branch.

### Linux / macOS

```bash
curl -fsSL https://runtimeforce.dev/install.sh | bash
```

### Windows (PowerShell)

```powershell
irm https://runtimeforce.dev/install.ps1 | iex
```

The IDE runs locally and is available at `http://127.0.0.1:8000`.

## Requirements

- Python 3.11+
- Git
- Linux, macOS, or Windows
- Internet connection for RuntimeForce account authentication and online entitlement checks
- An AI provider API key (BYOK) or a configured local model runtime to use AI features

## License

RuntimeForce IDE is distributed under the **Business Source License 1.1 (BUSL-1.1)**. It is source-available, not an OSI-approved open-source license. See [LICENSE](LICENSE) for the complete terms.
