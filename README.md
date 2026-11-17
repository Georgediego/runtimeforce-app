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
- When the server cannot verify a session, protected operations fail closed. A bounded offline grace period may use only previously server-verified entitlement data.
- The current implementation verifies sessions online through the official `/api/v1/auth/me` endpoint and obtains entitlements from `/api/v1/billing/entitlements`. Offline use relies on a bounded in-memory cache of previously verified entitlements.
- A local user can modify software running on their own computer. Protected account, subscription, and SaaS operations are therefore verified server-side.

## Installation

Public installers and the website download install the stable `main` branch.

### Linux

```bash
curl -fsSL https://runtimeforce.dev/install.sh | bash
```

### macOS

```bash
curl -fsSL https://runtimeforce.dev/install-macos.sh | bash
```

### Windows (PowerShell)

```powershell
irm https://runtimeforce.dev/install.ps1 | iex
```

All installers use the stable `main` branch and select an available local port from `8000`–`8010`.

- **Linux:** creates a per-user `runtimeforce-app.service` systemd service and starts it automatically at login.
- **macOS:** creates a `launchd` LaunchAgent and starts RuntimeForce automatically at login.
- **Windows:** starts the IDE in the PowerShell session; keep that terminal open while using RuntimeForce.

Python 3.11+ and Git are required on all platforms. Review the installer source before running it.

## Requirements

- Python 3.11+
- Git
- Linux, macOS, or Windows
- Internet connection for RuntimeForce account authentication and online entitlement checks
- An AI provider API key (BYOK) or a configured local model runtime to use AI features

## License

RuntimeForce IDE is distributed under the **Business Source License 1.1 (BUSL-1.1)**. It is source-available, not an OSI-approved open-source license. See [LICENSE](LICENSE) for the complete terms.


## Developer documentation

The public technical documentation lives in [docs/](docs/):

- [Getting Started](docs/GETTING_STARTED.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security & Data Handling](docs/SECURITY.md)
- [Workspaces & SSH — Project Isolation](docs/WORKSPACES_AND_SSH.md)
- [Git & GitHub — Project Isolation](docs/GIT_AND_GITHUB.md)
- [Roadmap](docs/ROADMAP.md)

Each project owns its Workspace / SSH configuration and Git / GitHub repository settings. New projects start disconnected and must be configured explicitly. The IDE does not fall back to another project's workspace when the selected project has no connection.
