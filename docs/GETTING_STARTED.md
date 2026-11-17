# Getting Started

RuntimeForce IDE is a local-first AI development environment for Linux, macOS and Windows.

## Requirements

- Python 3.11 or newer
- Git
- A supported desktop operating system
- An internet connection for account sign-in, entitlement refresh and cloud AI providers
- Optional: Ollama or LM Studio for local inference
- Optional: API credentials for supported cloud providers

## Install

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

The installers use the stable `main` branch. Python 3.11+ and Git are required.

- **Linux:** installs a per-user systemd service with automatic startup at login.
- **macOS:** installs a `launchd` LaunchAgent with automatic startup at login.
- **Windows:** runs in the PowerShell session; keep the terminal open while using the IDE.

Review the installer source before running it if you want to inspect every installation step.

## First launch

1. Open RuntimeForce IDE and sign in to your RuntimeForce account.
2. Create a project. New projects start without a workspace, SSH host or GitHub remote.
3. Open Project Settings → Workspace and connect a local folder or configure an SSH workspace.
4. Open Project Settings → Git and select the repository remote and branch preferences for this project.
5. Choose an AI mode and configure a local model runtime or a supported BYOK provider.
6. Start with a small task, inspect the agent trace and review file changes before running commands that affect important environments.

## Local models

Install Ollama or LM Studio separately, download a model compatible with your machine, then configure the local runtime in RuntimeForce. Model performance depends on model size, quantization, available memory and hardware.

## BYOK

Add an API key for a provider supported by your plan. RuntimeForce stores supported credentials locally using its credential-encryption service. Cloud prompts and selected context are sent directly to the provider you choose. Provider pricing, quotas and data-retention policies are controlled by that provider.

## Project isolation

Each project has its own Workspace / SSH configuration and Git / GitHub repository settings. Switching projects changes the workspace context used by editor, terminal and Git operations. See [Workspaces & SSH](WORKSPACES_AND_SSH.md) and [Git & GitHub](GIT_AND_GITHUB.md).

## Help

- [Architecture](ARCHITECTURE.md)
- [Security & Data Handling](SECURITY.md)
- [Workspaces & SSH](WORKSPACES_AND_SSH.md)
- [Git & GitHub](GIT_AND_GITHUB.md)
- [Roadmap](ROADMAP.md)
- [FAQ](https://runtimeforce.dev/faq)
