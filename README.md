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
- Google and GitHub account OAuth connections are managed by the RuntimeForce SaaS control plane.

## Authentication and entitlements

- The SaaS server is the authority for account identity, subscription status, plan features, and limits.
- The IDE does not treat locally decoded JWT claims or locally edited plan values as proof of entitlement. The server verifies the bearer token and returns current entitlements through `GET /api/v1/billing/entitlements`.
- When the server cannot verify a session, protected operations fail closed. During the configured Offline Grace period, the IDE may use only previously server-verified entitlements stored in its local SQLite subscription cache.
- The local entitlement cache refreshes from `/api/v1/billing/entitlements` and applies the server-provided feature flags and limits to HTTP APIs, WebSocket chat orchestration, agent tools, and UI controls. Offline access expires when the plan's `offline_grace_hours` window ends.
- Offline authentication is tied to a previously server-verified token fingerprint and the account email stored with the entitlement cache; the cached identity is accepted only while the cached plan remains inside its Offline Grace window.
- Custom admin-created plans fail closed: an omitted feature flag is treated as disabled. Built-in Free/Pro plans retain their legacy defaults unless an administrator explicitly overrides them.
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

On Linux, the installer creates and enables the per-user `runtimeforce-app.service` systemd service. It starts automatically after login. The installer selects the first available port from `8000`–`8010` and prints the local URL. On macOS and Windows, the installer selects an available port and runs the IDE in the current terminal.

## Requirements

- Python 3.11+
- Git
- Linux, macOS, or Windows
- Internet connection for RuntimeForce account authentication and online entitlement checks
- An AI provider API key (BYOK) or a configured local model runtime to use AI features

## License

RuntimeForce IDE is distributed under the **Business Source License 1.1 (BUSL-1.1)**. It is source-available, not an OSI-approved open-source license. See [LICENSE](LICENSE) for the complete terms.
