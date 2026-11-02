# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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


