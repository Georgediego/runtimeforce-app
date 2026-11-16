# Security & Data Handling

This document describes the current architecture and its boundaries. It does not claim that every local database page or file is encrypted.

## What stays local

The RuntimeForce SaaS service does not receive or store:

- Project source files and local workspace contents
- Local chat history and project memory
- SSH private keys and local SSH workspace configuration
- BYOK provider API keys stored by the local IDE

The local IDE is responsible for local filesystem access, terminal execution and SSH sessions.

## What leaves the local machine

- Account authentication and plan-entitlement requests go to `https://runtimeforce.dev`.
- When you use a cloud model, the prompt and selected context for that request are sent directly to the AI provider configured in the IDE.
- When you use GitHub account integration, the authorization flow involves the RuntimeForce account service and GitHub.

Do not send confidential material to a cloud model unless the provider's terms and your organization's policy allow it. Use a local model when a task must remain on the local machine.

## Credential encryption

The local app's credential-encryption service uses AES-256-GCM for supported credential values. The encryption key is derived from the local `MASTER_KEY` configuration in the app's environment.

Important distinctions:

- The SQLite database file is **not encrypted as a whole**.
- Chat history, project metadata and audit records are not automatically protected by SQLite-level encryption.
- The master key is stored in local environment configuration; it is not derived from the SaaS JWT signing key.
- Protect the local app directory and environment file with operating-system permissions.
- Use full-disk encryption and a protected operating-system account on machines containing sensitive projects.

## SSH safety

SSH connections are configured per project. A project without a configured workspace does not inherit another project's active SSH host. Review the target host and command before approving destructive operations. Do not store SSH passwords in shell history or project notes.

## Cloud provider data

BYOK means the IDE sends cloud inference requests directly to the provider using the configured API key. The provider's data retention, training, privacy, pricing and quota policies apply. RuntimeForce does not control those provider policies.

## Recommended production hygiene

- Keep the local `.env` file private and out of Git.
- Use a unique, high-entropy `MASTER_KEY` and keep a secure backup.
- Restrict filesystem access to the RuntimeForce data directory.
- Enable operating-system full-disk encryption.
- Use separate SSH accounts and least-privilege permissions for production hosts.
- Review agent commands before approving production changes.
- Never paste credentials into prompts, issue reports or screenshots.

## Known limitations

- SQLite is not encrypted at the file level.
- Local credential encryption depends on protecting the local master key.
- Cloud inference necessarily sends request content to the selected provider.
- Local-first architecture does not prevent a user, malware or another process with access to the same OS account from reading local project files.

Report suspected security issues privately through the contact details on the RuntimeForce website rather than publishing credentials or exploit details in a public issue.
