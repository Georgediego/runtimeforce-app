# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
