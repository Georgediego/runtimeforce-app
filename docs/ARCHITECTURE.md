# RuntimeForce Architecture

## Components

RuntimeForce has two separate applications and Git repositories.

### Local IDE — runtimeforce-app

The local IDE is a FastAPI application with a browser-based interface. It owns local project state and coordinates:

- Local filesystem workspaces
- Project-specific SSH workspaces
- Editor and terminal operations
- Git operations in the selected project workspace
- Project context and local memory
- Local model runtimes and direct BYOK provider requests
- Agent workflows, including Auto, Manual, Local and ATM

The local IDE stores application state in a local SQLCipher-encrypted SQLite database. The database key is derived from the local MASTER_KEY; supported credential fields retain additional AES-256-GCM encryption. Existing plaintext databases are integrity-checked, exported, verified, and atomically replaced on first startup after the SQLCipher upgrade. An encrypted pre-migration backup is retained.

### Hosted control plane — runtimeforce-server

The hosted service provides:

- Account registration and authentication
- Google and GitHub account OAuth flows
- Subscription checkout and billing
- Plan definitions, feature entitlements and usage limits
- Website, account pages and administration

The hosted service is not the user's project filesystem and does not execute commands on the user's VPS.

## Data flow

```text
Local IDE
  ├── Local project files and SQLite
  ├── Local shell and terminal
  ├── Project-specific SSH workspace
  ├── Local model runtime (Ollama / LM Studio)
  ├── Direct BYOK requests ───────────────> Selected AI provider
  └── HTTPS account / entitlement calls ──> RuntimeForce SaaS
```

For cloud inference, prompts and the context selected for a request leave the local machine and are sent directly to the configured provider. Local model inference stays on the configured local runtime.

## Project boundaries

A project is the boundary for its workspace and Git configuration.

- Workspace records are associated with a project ID and local user ID.
- Project-specific workspace resolution does not fall back to another project's active workspace.
- Git API requests carry a project ID and resolve the driver for that project.
- Repository remotes, branch preferences and versioning settings are stored on the project record.
- A new project is created disconnected. Workspace, SSH and GitHub configuration is added afterward.

### Existing project migration

Legacy shared workspace references are migrated into separate project-owned database records while preserving their configured path and SSH target. The migration does not copy files or remote directories. Projects that previously referenced the same physical path continue to share that path until the owner changes one project's workspace location.
## Authentication and entitlements

The hosted service is authoritative for account identity, plan status, feature flags and limits. Protected operations verify the account and entitlements against the hosted service. Locally decoded token claims are not an independent source of subscription authority.

## Protocols

The local chat UI communicates with the local app using WebSockets. App-to-server authentication and entitlement requests use HTTPS. Direct cloud model requests use the selected provider's API protocol.
