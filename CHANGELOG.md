# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Add a shared frontend plan-access state for feature flags, model eligibility, and project/SSH/Git repository limits.
- Add regression tests for Free-plan feature gates, model provider classification, quotas, ATM coordinator denial, and admin feature-key normalization.

### Changed
- Normalize admin Plan Features labels into canonical entitlement keys and fail closed for unspecified features on custom plans.
- Include configured trial days in the server entitlement payload and retain the complete entitlement object in the local SQLite cache.
- Lock Editor, Terminal, Git, Pro BYOK, Local LLM, and Software Updates controls from the same verified plan state.

### Fixed
- Block ATM at both the chat WebSocket and agent-coordinator layers when the plan excludes it.
- Correct model entitlement classification so OpenRouter and other free-cloud providers do not inherit a Pro restriction from a generic catalog tier.
- Enforce Git plan access before GitHub OAuth linking or integration-token storage; a positive Git Repos quota never overrides a disabled Git feature.
- Preserve only the project records inside the current Active Projects allowance after a plan downgrade, while keeping over-limit records deletable.
- Correct the WebSocket model-denial guard indentation and feature-specific error reporting.

## [1.1.17] - 2026-11-13

### Changed
- Replace purple and magenta Runtime Graph accents with a cohesive neon emerald and lime palette.
- Replace placeholder graph markers with distinct hand-drawn vector icons for each object type.
- Keep real graph relationships highlighted after a run completes until the next run begins.
- Remove the LIVE MEMORY OPERATIONS overlay so the 3D graph has the full widget area.

### Fixed
- Delete session-owned graph nodes, their relationships and embeddings, and invalidate the session context cache when a chat is deleted.

## [1.1.16] - 2026-11-10

### Added
- Add a live 3D Runtime Graph sphere built from real SQLite memory nodes and relationships, workspace topology, providers, models, chat modes, and agent roles.
- Add live host resource monitoring and command-approval safeguards for shell execution.
- Add IDE error reporting and developer inbox feedback with remote resolution notifications.

### Changed
- Keep the graph continuously rotating, accelerate it during assistant generation, and visualize real agent and memory activity throughout the full response lifecycle.
- Preserve the assigned color of every activated graph node while keeping untouched nodes green.
- Improve workspace navigation, editor language detection, and agent execution visibility.

### Fixed
- Improve cancellation and Stop acknowledgement so pending approvals, running commands, and chat WebSocket state are cleaned up reliably.
- Improve memory graph retrieval, persistence, live event delivery, and graph refresh behavior.

## [1.1.15] - 2026-11-07

### Changed
- Remove the bottom border from the centered workspace toolbar.

### Fixed
- Start stable update checks independently of authentication completion so slow or failed sign-in initialization cannot block update detection.


## [1.1.14] - 2026-11-07

### Changed
- Restore the Chat, Editor, and Terminal toolbar between the left and right sidebars.
- Keep the active workspace tab emerald with a compact pill treatment.
- Darken chat message surfaces for more comfortable reading.
- Apply translucent emerald glass styling to confirmation, prompt, and settings dialogs.
- Limit Agent Trace to 160px and scroll its event list internally.

### Fixed
- Remove the extra focus frame around the chat composer.
- Persist database message IDs in the live chat UI so edit and delete actions target the correct records.
- Edit user messages in place, remove the later conversation branch, and regenerate without inserting a duplicate user message.
- Cascade message edits/deletions through SQLite history, session-scoped graph summaries, embeddings, and context cache.
- Restrict message read/edit/delete operations to the authenticated session owner.


## [1.1.13] - 2026-11-07

### Changed
- Align the workspace sidebar toggles with the Explorer and right-sidebar columns in the global header.
- Restyle the selected Chat/Editor/Terminal tab with a soft emerald neon glow and remove the visual divider beneath the active tab.
- Unify Projects and Sessions card borders with the Agent Workflow glass-card treatment.
- Replace near-black dark-theme surfaces with a restrained forest-green palette.

### Fixed
- Disable clipped hover tooltips on sidebar navigation and panel controls.


## [1.1.12] - 2026-11-06

### Fixed
- Preserve the original dark and light base gradients beneath the restored subtle aurora highlights on workflow, trace, tools, and glass cards.


## [1.1.11] - 2026-11-06

### Changed
- Move the complete workspace navigation bar, including both sidebar toggles and Chat/Editor/Terminal tabs, into the global header.
- Restore Agent Trace to its dedicated card in the right sidebar.
- Restore a subtle emerald aurora wash across glass cards while preserving each card's theme surface.


## [1.1.10] - 2026-11-06

### Changed
- Move Agent Trace into the global header and render its five latest events in a compact emerald glass strip capped at 160px.
- Restyle Chat, Editor, and Terminal tabs as rounded translucent emerald controls in both themes.


## [1.1.9] - 2026-11-06

### Changed
- Limit Agent Trace to the five most recent events and align timeline dots slightly left.
- Standardize structural interface card borders with the emerald glass border tokens in dark and light themes.


## [1.1.8] - 2026-11-06

### Fixed
- Keep the icon-led empty Active Tools state visible after session changes and tool cleanup.
- Avoid CSS selector escaping for tool IDs when updating existing activity rows.
- Pause Agent Trace and active-tool animations while the document is hidden.


## [1.1.7] - 2026-11-06

### Changed
- Add color-matched animated timeline dots to Agent Trace entries and refine the vertical event line.
- Replace the empty Active Tools message with a clear icon-led state and show a semantic icon for each active tool.
- Prevent Agent Workflow, Agent Trace, and Active Tools cards from shrinking when Manual or ATM controls expand.


## [1.1.6] - 2026-11-06

### Changed
- Restore AGENT TRACE as a standalone glass card with its heading and LIVE EVENTS label inside the card, separate from AGENT WORKFLOW.
- Apply the translucent emerald glass treatment to the AUTO, ATM, LOCAL, and MANUAL strategy selector in dark and light themes.


## [1.1.5] - 2026-11-06

### Changed
- Restyle MANUAL and ATM model dropdowns with translucent emerald glass surfaces in dark and light themes.
- Move AGENT TRACE and LIVE EVENTS inside the Agent Workflow card.
- Give trace event badges consistent widths and distinct colors for phases, model attempts, tools, completion, errors, and other states.
- Log the start of model reasoning and response streaming once per generation without exposing private reasoning content.
- Replace the empty Active Tools message with a quiet, styled waiting state.


## [1.1.4] - 2026-11-06

### Changed
- Combine Agent Workflow and Model Control into one panel and remove the redundant outer wrapper.
- Hide duplicate role/model metadata and graph tool events already represented by Agent Trace and Active Tools.
- Keep existing workflow, model selection, progress, and live trace hooks intact.


## [1.1.3] - 2026-11-06

### Changed
- Move Free/Pro filters, Manual model selection, ATM role model controls, orchestration status, and progress into Agent Workflow.
- Replace the standalone Orchestrator card with an integrated workflow control surface.
- Restyle Agent Trace and Active Tools with matching emerald glass panels while preserving their live data hooks.


## [1.1.2] - 2026-11-06

### Fixed
- Prevent the Agent Workflow panel from being clipped and overlapped by Agent Trace.
- Give the workflow and trace log separate vertical space while preserving existing element IDs and behavior.

## [1.1.1] - 2026-11-06

### Changed
- Establish the first RuntimeForce neon-glass design foundation with shared visual tokens, a restrained aurora background, and reusable glass surfaces.
- Keep the existing layout, DOM hooks, frontend behavior, and backend unchanged.

## [1.1.0] - 2026-11-06

### Added
- Add a live Agent Workflow graph to the IDE sidebar, showing the real execution lifecycle across Context, Plan, Build, Verify, and Result stages.
- Stream actual chat orchestration events into the graph, including the active agent role, selected model, and running/completed tool calls.
- Add an emerald glass visual layer with translucent panels, backdrop blur, subtle green glow, animated stage indicators, and responsive layout.

### Changed
- Refresh the Agent Trace controller to render execution events safely through DOM text nodes and reset graph state when the active session changes.
- Improve dark-theme surfaces and focus/hover states with the RuntimeForce emerald accent while retaining a readable light-theme graph.

### Accessibility
- Respect the operating system's reduced-motion preference by disabling decorative graph animations.


## [1.0.9] - 2026-11-06

### Fixed
- Replace Git-based automatic updates with public HTTPS release downloads, so updates work on any local branch without a GitHub account, SSH key, or configured Git remote.
- Validate downloaded release archives and preserve local environment files, virtual environments, databases, projects, and runtime data during installation.
- Restore replaced application files if dependency installation fails, then restart the IDE after a successful update.
- Align FastAPI version metadata with the current IDE release.


## [1.0.8] - 2026-11-06

### Fixed
- Isolate chat state by active project. Switching projects now clears the previous project's messages, traces, tools, terminal session, and selected chat before loading the new project's sessions.
- Prevent stale asynchronous session-list and chat-history responses from a previously active project from overwriting the currently selected project's interface.
- Clear the chat view when a project has no sessions or when no project is selected, instead of leaving messages from the previous project visible.
- Refresh the active chat immediately after deleting the selected project and switch the interface to the next available project.
- Keep project deletion scoped to project-owned database records, including project settings, workspace database bindings, chat sessions and related history, while preserving shared workspace resources and other projects' data.
- Keep shared physical workspace folders, local files, and Git repositories untouched when a project is deleted.
- Restrict project graph-memory relationships to the owning project so one project's memory does not leak into another project's context.

### Security
- Preserve project isolation when multiple projects share the same physical workspace: deleting one project's database binding does not remove the shared folder or the remaining projects' workspace access.
- Keep global provider settings, API keys, SSH credentials, account authentication, and external GitHub repositories outside project-deletion cleanup.


## [1.0.6] - 2026-11-05

### Added
- Add a one-click stable IDE updater that checks the local Git checkout, applies only a fast-forward update from GitHub main, installs dependencies, and restarts the running Uvicorn process.

### Fixed
- Translate the remaining manual update-check progress message to English.
- Explain the automatic update action in the release notification while retaining manual commands as a fallback.

## [1.0.5] - 2026-11-05

### Fixed
- Allow public IDE version checks without requiring a live SaaS authentication request.

## [1.0.4] - 2026-11-05

### Fixed
- Use English for the GitHub update-check failure status in Settings.

## [1.0.3] - 2026-11-05

### Fixed
- Fall back to the GitHub Contents API when the raw GitHub changelog endpoint is unreachable.
- Keep the stable IDE version check independent from the SaaS server version.

## [1.0.2] - 2026-11-05

### Fixed
- Remove the duplicate Software Updates heading in Settings.
- Use English consistently for update-check labels, status messages, and actions.

## [1.0.1] - 2026-11-05

### Fixed
- Keep the installed IDE version visible when the remote stable-version lookup is unavailable.
- Show an explicit unavailable state instead of leaving both version fields blank or presenting an unverified latest version.

## [1.0.0] - 2026-11-05

### Added
- Release the local-first RuntimeForce IDE with local and SSH workspaces, AI-assisted coding, project memory, terminal, Git/GitHub workflows, and configurable cloud or local model providers.
- Add server-verified account authentication and dynamic plan entitlements while keeping projects, prompts, local database, and BYOK credentials on the user's computer.
- Add manual stable-release update checks, twice-daily notifications, and four-hour snoozing without interrupting active work or modifying local project data.

### Fixed
- Allow MANUAL mode with `auto` to use automatic model routing while keeping explicitly selected MANUAL models pinned without fallback.
- Restore local data access through normalized verified account email identity and preserve existing local SQLite data.
- Improve chat streaming, model routing, GitHub repository workflows, and local-model timeout handling.

### Removed
- Remove the retired X.com and Reddit social integrations and their Social Drafts interface.

## [0.6.10] - 2026-11-05

### Fixed
- Treat MANUAL mode with the model selector set to `auto` as automatic routing, while keeping an explicitly selected MANUAL model strictly locked with no fallback.
- Add regression tests for MANUAL auto-routing and strict concrete-model selection.

### Changed
- Update checks now read the latest stable version directly from `Georgediego/runtimeforce-app` `main/CHANGELOG.md`.
- Run automatic version checks at most twice per day, defer update reminders for four hours, and wait for an idle UI before displaying a pending update.
- Add Settings → Software Updates with installed/latest versions, status, and a manual check action.
- Keep updates user-initiated: the IDE only displays safe Git commands and never replaces running code or modifies the local database automatically.


## [0.6.9] - 2026-11-04

### Fixed
- Show generation errors only after the stream ends without a final answer; add authenticated one-click diagnostic reports to errors@runtimeforce.dev.
- Start the thinking indicator immediately and render its rotating glow as a closed ring with a crescent highlight.

## [0.6.8] - 2026-11-04

### Fixed
- Increase local Ollama and LM Studio generation timeout to 900 seconds for slow CPU-only hardware. Cloud timeouts unchanged.

## [0.6.7] - 2026-11-04

### Fixed
- Use the verified, normalized account email as the WebSocket local-data identity so chat routing can access saved provider API keys and selected models.
- Increase local Ollama and LM Studio generation timeout from 45 to 300 seconds for slower CPU-only hardware.


## [0.6.6] - 2026-11-04

### Fixed
- Prevent stale MANUAL model selections from overriding AUTO, ATM, and LOCAL routing; keep strict model locking exclusive to MANUAL.
- Preserve ATM as the user-facing mode (internally routed as `coding`) and return strategy-specific routing errors when no eligible model is available.
- Add a chat action to open model/provider selection after a generation error.
- Add regression coverage for AUTO routing with a stale manual model lock and MANUAL selection validation.

## [0.6.5] - 2026-11-04

### Fixed
- Remove the stale social interface import and public export left behind after deleting the X.com/Reddit Social Drafts module; restore IDE startup.

## [0.6.4] - 2026-11-04

### Removed
- Remove X.com and Reddit sign-in, account linking, publishing, media upload, token refresh, and connected-account management from both IDE and SaaS.
- Remove the X-only Social Drafts UI, API, services, and obsolete local OAuth/social-draft storage.
- Keep Google and GitHub authentication and GitHub repository access.

## [0.6.3] - 2026-11-03

### Changed
- Reduce IDE update checks to one check at startup and then once every eight hours; remove extra checks on tab visibility changes and short retry loops.
- Postpone update reminders for eight hours to match the reduced notification frequency.

## [0.6.2] - 2026-11-03

### Added
- Automatically check the stable RuntimeForce IDE release published on GitHub main and notify the user inside the IDE when an update is available.
- Add platform-specific update commands with one-click copying; reminders can be postponed for four hours and are retried after active generation, authentication, or other dialogs finish.
- Keep updates manual so running work is not interrupted and local projects, settings, and SQLite data are never overwritten.
- Add `requirements-dev.txt` for a reproducible test environment and remove a stale test dependency on the retired OAuth repository.


## [0.6.1] - 2026-11-03

### Fixed
- Use the verified, normalized account email as the local SQLite ownership key instead of the SaaS UUID, restoring access to existing local projects, provider settings, sessions, and drafts after account identity synchronization.
- Reject authenticated SaaS responses without a verified email rather than falling back to a UUID and silently creating a second local data identity.
- Add regression tests for email normalization and missing-email rejection.


### Security
- Verify IDE access tokens against the official RuntimeForce SaaS authentication endpoint; do not trust locally decoded JWT claims.
- Pin authentication and entitlement requests to `https://runtimeforce.dev`.
- Require verified account entitlements for WebSocket chat and local social-draft operations.
- Remove retired local OAuth routes, token storage, and embedded OAuth credentials.

### Added
- Add the BUSL-1.1 license with a RuntimeForce-specific limited production-use grant.
- Add GitHub Actions checks for Python compilation and pytest.

### Changed
- Keep social OAuth credentials on the SaaS control plane; retain only local social-draft generation and publishing workflows.
- Document local-first data handling, BYOK network boundaries, and stable-main installation policy.

## [0.6.0] - 2026-11-02
- Git push and pull use the linked GitHub OAuth account through a short-lived authenticated server bridge; no project PAT is required.
- Social Drafts can attach up to four images or one MP4 video before publishing to X.com.
- The IDE starts OAuth account linking using its authenticated RuntimeForce session, so a separate browser login cookie is not required.


### Added
- Added Studio Social Drafts: generate X.com copy from recent Git history and local project memory, review/edit it, and publish through the connected RuntimeForce account.
- Added automatic draft preparation after a successful Git push.
- Added a GitHub repository picker backed by the linked GitHub OAuth account; the IDE no longer requires a project PAT field.

### Fixed
- Social account status and disconnect actions now use the RuntimeForce account service as the single source of truth.
- GitHub and X OAuth initiated from the IDE link to the existing signed-in account instead of creating a separate local connection.
- Reddit remains disabled in the IDE until application approval.

### Changed
- Cloud social OAuth tokens remain on the account service; the IDE receives only the RuntimeForce session token and safe account metadata.


## [0.5.2] - 2026-11-02

### Fixed
- BYOK key management no longer depends on a successful cloud entitlement check; authenticated users can manage their locally stored provider keys.
- Local editor, terminal, and Ollama/LM Studio discovery remain available without plan-feature verification.
- Cloud model requests now fail clearly when the required BYOK API key is missing instead of silently relying on an implicit provider key.
- Low-spec and CPU-only hardware notices are informational and never block local model selection.
- Terminal prompt displays the current OS username and hostname.
- Unified translucent styling for IDE modals, toasts, and tooltips.

### Changed
- IDE version metadata is aligned to 0.5.2.

## [0.5.1] - 2026-11-02

### Fixed
- Removed obsolete automated tests for the retired credit balance service and Managed AI proxy/routing paths.
- Documented `python -m pytest -q` as the standard test command so the repository root is reliably added to Python's import path.

## [0.5.0] - 2026-11-02

### Removed
- Removed the Managed AI server-proxy route and all server-managed model candidates from local orchestration.
- Removed the local AI credit balance service and UI integration.

### Added
- Added server-verified dynamic entitlement loading with plan-configured offline grace.
- Project creation limits now come from the current plan's server-managed limits instead of hard-coded plan names.

### Changed
- Local BYOK keys and model routing remain on the user's computer; provider API calls go directly to the configured provider or local runtime.
- BYOK key storage no longer depends on a fixed Studio/Expert plan tier.

## [0.4.5] - 2026-11-02

### Fixed
- OpenAI model discovery now excludes transcription, audio, realtime, embedding, image-generation, and other non-chat model IDs from chat routing.
- Deprecated OpenAI `o3-mini` model IDs are no longer offered for new chat requests.
- Provider autoselection now matches complete model IDs, preventing `gpt-4o` from accidentally selecting `gpt-4o-transcribe-diarize`.
- AI thinking orbit uses a fixed square box centered on the avatar, keeping its circular path perfectly round.

### Notes
- OpenAI API requests still require an active API billing balance. A valid API key alone does not provide credits.

## [0.4.4] - 2026-11-02

### Fixed
- Wait for local SaaS authentication/session synchronization to finish before requesting projects, preventing the startup race that caused `401 Authentication required` during project loading.

### Notes
- Existing SQLite files and records are not modified by this fix. Legacy identity migration remains a separate, non-destructive step.

## [0.4.3] - 2026-10-31

### Fixed
- Managed AI upstream authentication failures no longer mark the local `runtimeforce-managed` proxy as permanently unauthorized. The cooldown applies only to the failing route, so the local app does not confuse a server-side provider-key error with its own account authentication.
- Managed AI failure summaries now include the safe upstream provider name and failure category, making it clear which Admin-configured provider needs attention without exposing credentials.
- FastAPI version metadata now matches the `0.4.3` app release.

### Notes
- If all Admin-selected providers return `AuthenticationError`, check and replace the affected API key in the server Admin provider settings. The local app does not receive or store those keys.
- Automated coverage verifies upstream provider diagnostics and that Managed AI authentication errors do not permanently disable the proxy route.
- Documented server-side fallback for recoverable pre-output failures, including the rule to skip same-provider models on provider-wide quota or authentication errors.

## [0.4.2] - 2026-10-31

### Fixed
- Manual and ATM model menus stay open while the page or menu is scrolled, reposition within the viewport, and close after model selection or an outside click.
- Manual and ATM model choices use the same delegated selection handler, so portaled options update the selected model consistently.
- Managed AI errors now preserve safe upstream failure types from the server stream, making provider authentication, rate-limit, and empty-response failures distinguishable in the local trace.

### Notes
- Verified the local Manual and ATM menus with scroll and selection interactions. A live Studio request reached the server-managed OpenAI route and exposed that provider failure types were being dropped by the local client; this release preserves those safe diagnostics.

## [0.4.1] - 2026-10-30

### Fixed
- Managed AI routing now uses an authenticated session token as the signal to try the server. The server validates the real subscription, so a stale local plan claim no longer blocks a Studio account from reaching its configured server models.
- Replaced the misleading local Groq/Gemini setup instruction with errors that reflect both local and Managed AI routing.

### Notes
- This patch release fixes the entitlement handoff between the local app and server. Free accounts remain denied by the server and can still use local provider routes.

## [0.4.0] - 2026-10-30

### Added
- Server-backed Managed AI model catalog in the MANUAL and ATM selectors. Models shown here come from active provider keys and model IDs selected by the server administrator.
- Managed AI streaming client for the server's authenticated `/api/v1/chat/stream` endpoint, including tool calls, server model-attempt status, and fallback events.

### Changed
- Paid Pro, Studio, Expert, and Enterprise sessions prefer the server-managed model catalog in AUTO, CODING, and ATM modes; AUTO makes a coarse code/analytics classification from the latest user prompt, and the local-only mode continues to use local runtimes.
- Explicit Managed AI model selections stay pinned to the server catalog. Explicit local Manual selections keep their local route first, with Managed AI as fallback.
- WebSocket authentication now sends the bearer token in the first WebSocket message instead of the URL query string, keeping it out of URL access logs.
- Chat status shows operational phases and attempted models while keeping provider-supplied hidden reasoning out of the UI.
- Custom model dropdowns are portaled to the document viewport so the right sidebar's scroll container no longer clips them.

### Removed
- The obsolete Consilium strategy guard and its retired-mode test.

### Security
- Managed AI plan authorization and selected-model enforcement are performed by the server on every catalog and streaming request. The local app's JWT claim decoder still does not verify signatures and is not an entitlement authority.

### Notes
- Requires runtimeforce-server `>= 2.10.0` for the Managed AI catalog and streaming routes.
- Automated tests cover proxy payloads, plan rejection, selected-model enforcement, Studio routing, and provider fallback behavior. Live provider credentials and deployment behavior require manual verification.

## [0.3.1] - 2026-10-30

### Changed
- Updated the contacts page to identify Creem as the Merchant of Record for billing questions.
- Aligned FastAPI version metadata with the changelog-driven app version, so API metadata and the UI report the same release.

### Documentation
- Rewrote the README, project context, and roadmap to describe the current app/server boundary and verified implementation details.
- Added focused development guidance and removed an obsolete rules document that contradicted the checked-in implementation.

### Notes
- This patch release changes app metadata, contacts wording, and documentation. It does not change the local app API contract.
- The existing server compatibility baseline remains `>= 2.8.0`.

## [0.3.0] - 2026-10-26

### Added
- Manual model selection dropdowns for ATM and MANUAL.
- GitHub repositories and branches listing API.
- Secure git token passing via process environment.
- Light theme sync with the server.
- Version from CHANGELOG.

### Changed
- Ticket generation uses crypto.getRandomValues.
- Selected models are enforced on the server.

### Fixed
- Shared SQLite connection no longer closed by the OAuth repository.
- ATM architect context call.

### Removed
- Consilium mode.
- Ghost agent services.
- Support bot.
- JS shims.
- Billing & Credits tab.

### Notes
- Requires server >= 2.8.0.

## [0.2.0] - 2026-10-14
- Initial release.
