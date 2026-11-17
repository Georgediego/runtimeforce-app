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

The local app uses two encryption layers:

- SQLCipher 4 encrypts the complete local SQLite database, including chat history, project metadata, audit records, graph memory, embeddings, settings, and credential ciphertext.
- AES-256-GCM continues to encrypt supported credential values before they are stored in the database.
- A dedicated database key is derived from the local 256-bit `MASTER_KEY` using HKDF-SHA256 with a database-specific context. The database key is not the SaaS JWT signing key and is not stored in plaintext.
- SQLCipher is mandatory. The app fails closed rather than silently opening or creating a plaintext database if the SQLCipher driver is unavailable.

On first startup after this upgrade, an existing plaintext SQLite database is integrity-checked, exported to SQLCipher, and verified before atomic replacement. A cross-process file lock serializes migration so two RuntimeForce instances cannot export or replace the same database concurrently. A separately encrypted pre-migration backup is retained beside the database. If migration fails, the original database is left in place and the app does not start with plaintext storage.

The per-user `MASTER_KEY` is stored in `$XDG_CONFIG_HOME/runtimeforce/.env` (normally `~/.config/runtimeforce/.env`) with directory permissions `0700` and file permissions `0600`. The key is required to open the database. On first startup after this change, RuntimeForce migrates the existing key from the legacy source-tree `.env` or `~/.runtimeforce/.env` location without generating a replacement. Conflicting or invalid legacy keys stop startup; the application never silently replaces them. Keep a secure offline backup of the key: losing it makes the encrypted database unrecoverable. Use full-disk encryption on machines containing sensitive projects.

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

- Database encryption protects data at rest, not data while RuntimeForce is running and the database is unlocked.
- Local database and credential encryption depend on protecting and backing up the local master key.
- SQLCipher does not encrypt project files, workspace files, application logs, downloaded model files, or operating-system swap outside the database.
- Cloud inference necessarily sends request content to the selected provider.
- Local-first architecture does not prevent a user, malware or another process with access to the same OS account from reading data available to that account.

Report suspected security issues privately through the contact details on the RuntimeForce website rather than publishing credentials or exploit details in a public issue.
