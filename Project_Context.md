# RuntimeForce App Context

This file summarizes the local IDE repository. The [workspace-level Project Context](../Project_Context.md) is the canonical source for shared architecture, current server API contracts, security findings, and cross-repository decisions.

## Runtime

`runtimeforce-app` is a local FastAPI application with a Vanilla JavaScript browser UI and a SQLite database. It manages local and SSH workspaces, project context and rules, file and Git operations, terminal sessions, chats, model configuration, BYOK credentials, and local memory. It can call local model runtimes or configured providers; Managed AI requests are sent to `runtimeforce-server`.

The database path is selected by the app's OS-specific data-directory helper in `app/repository/db_connection.py`. Model allowlists are persisted in `provider_selected_models`; the keys API and agent coordinator read that stored selection. LLM requests use LiteLLM. The agent coordinator invokes `RoleRouterService`, but its returned route is currently unused; do not document the classifier as a decision source until that is fixed.

## Security facts to preserve in future edits

- `JWTAuthService` currently extracts claims by decoding the JWT payload and does not verify its signature. Do not treat those claims as proof of paid entitlement.
- `LicenseService` currently has a seven-day in-memory cache for Studio claims, not the 48-hour grace period described in earlier design proposals.
- `AESCryptoService` uses a local `MASTER_KEY` from the app's working-directory `.env`; its `jwt_token` parameter is not used by key derivation.
- Keep `.env`, databases, provider keys, SSH credentials, and virtual environments private and out of source control.

## Work conventions

- Check `git status` before editing and preserve existing user changes.
- Code, UI labels, comments, and logs are in English; project documentation and user communication are in Russian.
- Reuse the current DI container, repositories, API routes, and UI event patterns where applicable. Do not introduce unused abstractions or duplicate model-selection storage.
- Never read or print secret values. Never commit, push, or deploy without an explicit request.
- Run relevant tests with `pytest tests/ -q` when requested by the task.
