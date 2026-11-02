# RuntimeForce App Context

This repository contains the local RuntimeForce IDE. The hosted control plane is maintained in the separate `runtimeforce-server` repository. GitHub `dev` is the source of truth for development.

## Runtime and privacy

The IDE is a local FastAPI application with a Vanilla JavaScript browser UI and SQLite storage. It manages local/SSH workspaces, projects, prompts, source code, local memory, Git operations, terminal sessions, model discovery, and local BYOK credentials.

All user data stays on the user's computer: project source, prompts, workspace data, SSH credentials, provider API keys, and memory. The app sends authentication and entitlement checks to `runtimeforce-server`; it does not upload project data or prompts to the control plane. AI inference is sent directly from the local app to a user-configured provider or local runtime.

## Authentication and dynamic entitlements

- The server owns account authentication, subscription state, Creem billing, plan records, and entitlement policy.
- The app must not treat locally decoded JWT claims as proof of a paid plan.
- Verify access tokens through the official `GET https://runtimeforce.dev/api/v1/auth/me` endpoint; never decode JWT claims locally as identity.
- Use `GET https://runtimeforce.dev/api/v1/billing/entitlements` as the authoritative source of the current plan's feature map and limits.
- Keep the SaaS control-plane URL fixed to `https://runtimeforce.dev`; do not allow an environment variable or local setting to redirect authentication or entitlement checks to another backend.
- Plan codes are dynamic strings. Never hard-code a closed plan enum or special-case Enterprise/Expert/Studio as the only valid tiers.
- Admin can create any plan and add/remove any feature key on each plan independently. New feature keys must not require a code release just to appear in plan configuration.
- Keep local feature enforcement fail-closed when fresh entitlements are unavailable; only a previously server-verified in-memory entitlement may be used during the bounded grace period defined by the plan. Never authorize from user-editable SQLite cache data.

## Local AI configuration

- BYOK provider keys are stored locally using AES-256-GCM. The master key is generated and stored locally in the user's `.env`; PBKDF2-HMAC-SHA256 derives per-record encryption keys. Do not derive encryption keys from unverified JWT claims or send the master key to the SaaS server.
- Model discovery, selected model allowlists, autoselection, runtime validation, and model rotation are local responsibilities.
- Do not call or depend on a server Managed AI Proxy, server AI Providers page, server provider keys, or server model allowlists.
- Do not send provider credentials, prompts, model request bodies, source files, or chat content to the server.
- Social account OAuth tokens are managed by the SaaS. Do not reintroduce local OAuth token repositories, local OAuth callback routers, or browser localStorage token storage.

## Work conventions

- Check GitHub `dev` before changing code. Preserve the user's local working copy and never assume a local folder is the source of truth.
- The app repository is `Georgediego/runtimeforce-app`; the server repository is `Georgediego/runtimeforce-server`.
- Keep local BYOK functionality; only server-managed AI provider administration/proxy functionality is removed.
- The public installer and website download must always target the IDE `main` branch. `dev` is for integration and user testing only.
- The IDE source is licensed under BUSL-1.1; production use of account, subscription, entitlement, and license operations must use the official RuntimeForce backend. BYOK requests still go directly to user-selected AI providers.
- Keep code, UI labels, comments, and logs in English; project documentation and user communication in Russian.
- Never read or print secret values. Never commit secrets or local databases.
- Run tests from the repository root with `python -m pytest -q`. Use `python -m` so the repository root is on `sys.path` and the `app` package resolves consistently.
- After deploying/updating the local IDE, restart with `sudo systemctl restart runtimeforce-app.service`.
