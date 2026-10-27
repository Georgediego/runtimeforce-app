# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Requires server >= 2.7.0.

## [0.2.0] - 2026-10-14
- Initial release.
