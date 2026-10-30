# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
