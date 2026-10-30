# RuntimeForce App Roadmap

Roadmap items are planned work, not promises about existing behavior. Shared architecture and current server contracts live in the [workspace Project Context](../Project_Context.md).

## Current product

The local app provides local and SSH workspaces, project context/rules, file and Git tools, terminal execution, AI chat, provider configuration, model allowlists, local memory, and optional server-backed Managed AI. The server owns accounts, plan and billing state, Creem checkout/webhooks, and the Managed AI Proxy.

The current server seeds Free, Pro, Studio, and Enterprise rows, while app-side entitlement checks and server tier names are not fully aligned. Plan-name changes require a compatibility review before release.

## Priority 1 — close correctness and security gaps

- Verify JWT signatures in the local app before trusting user or plan claims.
- Align license cache expiry with the documented grace period and derive entitlements from verified claims.
- Make local credential encryption configuration explicit, stable, and recoverable; remove any misleading JWT-derived-key claims.
- Align app and server plan names, especially `expert` versus `enterprise`, and define safe behavior for admin-created plans.
- Consume the result of `RoleRouterService` or remove the unused routing call after confirming intended behavior.
- Continue security tests for auth, license expiry, data isolation, credential encryption, and terminal boundaries.

## Priority 2 — improve operations

- Document backup and recovery for the local SQLite database and its encryption key.
- Improve error reporting for provider discovery, SSH reconnect, and Managed AI streaming.
- Verify the server-managed catalog UI and streaming route against live subscription/provider configuration; keep local BYOK allowlists and server Admin allowlists as separate authorities.
- Add targeted coverage for workspace isolation, persistence, and model selection regressions.

## Later

- Evaluate richer model capability metadata and routing signals from actual telemetry.
- Assess packaging and update distribution before a public desktop release.
- Revisit team features only after the single-user local workflow and hosted billing lifecycle are stable.

## Excluded from current scope

- The removed support bot.
- New interface layers without multiple implementations.
- Duplicated plan prices or user model selections in browser storage.
- Automatic commits, pushes, service restarts, or deployment as part of routine local edits.
