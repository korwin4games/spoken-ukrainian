# Changelog

All notable changes to Spoken Ukrainian will be documented here.
This project follows Semantic Versioning and the Keep a Changelog structure.
Dated version sections describe project baselines; they do not imply that a Git tag
or GitHub Release has been published.

## [Unreleased]

### Added

- Document ClassicUA's project-specific permission and required attribution; explain the planned user experience and translation update workflow in README.

### Changed

### Fixed

## [0.0.1] - 2026-11-16

### Added

- Initial independent project structure and architecture, source integration and licensing documentation.
- Ukrainian language registration through Spoken Community Pack metadata.
- Original text-only Places diagnostic addon, with its own version 0.1.0.
- Deterministic diagnostic packaging, provenance checks and automated tests.
- ClassicUA source adapter, restricted Lua parser, source override resolution, grammar inventory and metadata-only provenance audit, merged into main in PR #1.
- Synthetic adapter tests and GitHub Actions build/test validation.
- Authoritative project VERSION file and standard-library version CLI with explicit stable-release approval.
- Project versioning policy, changelog and CI checks for version/changelog/tag consistency.

### Fixed

- Quoted Lua delimiters and keywords can no longer satisfy parser structural checks.

No ClassicUA translation content or audio is distributed. Redistribution and TTS permissions remain unresolved.
