# Development Rules

## Scope and safety

- Read the relevant source and repository status before making changes.
- Preserve existing user changes. Do not overwrite `.env`, local databases, credentials, or virtual environments.
- Do not change branches, commit, push, restart services, or deploy unless the user explicitly asks.
- Do not introduce unrelated refactors, new dependencies, unused code, or duplicate state stores.

## Language and implementation

- Write code, comments, logs, API fields, and user-interface text in English.
- Write project documentation and user communication in Russian unless the document is a public-facing English README.
- Prefer existing routers, repositories, services, dependency injection, and interface patterns. Add an abstraction only when it has a real caller and a clear purpose.
- Use the local database and API as the source of truth for persisted user and model-selection state.

## Verification

- Run only the checks relevant to the requested change. When a task explicitly requests tests, run them and report actual output/results.
- Do not claim a security property based on documentation alone; verify it in the implementation.
- Keep generated exports, caches, local secrets, and deployment snapshots out of source changes unless the task is specifically about them.

The shared architecture and current server API contract are documented in [Project_Context.md](../Project_Context.md).
