# Changelog

All notable changes to Spoken Ukrainian will be documented here.
This project follows Semantic Versioning and the Keep a Changelog structure.
Dated version sections describe project baselines; they do not imply that a Git tag
or GitHub Release has been published.

## [Unreleased]

### Added

- Record approved four-module policy and configurable ordered translation sources. Add an offline, sequential Spoken-inventory candidate resolver, provider/remaining/total metadata coverage reports, synthetic tests, and editable draw.io/SVG architecture diagrams. `another` remains stub-only; `own_translator` is a non-publishable mock; `[]` / `{}` selects the real client locale. No real identity joins or translated packs are approved.
- Add Stage 3 pinned public canonical inventories, independently reviewed join-proof validation, persistent metadata review schema, offline two-revision effective comparison, coverage/impact CLI, and 23 additional tests. Real mapping acceptance remains pending: zero independently approved real joins; runtime display gates remain unchanged.
- Add Stage 2B pinned Lua runtime characterization, per-surface compatibility evidence, manual Forever checks and minimal upstream text/audio API proposals.
- Document ClassicUA's project-specific permission and required attribution; explain the planned user experience and translation update workflow in README.
- Add a Ukrainian README (`README.uk.md`) and language links between the English and Ukrainian guides.

### Changed

- Refresh English/Ukrainian READMEs with the four approved modules, configurable provider chain, sequential candidate accounting, synthetic coverage example and editable diagram; document current offline/runtime limitations. Clarify AGENTS.md guidance on mapping invalidation and bilingual parity, update existing code-review/runtime/ClassicUA skills, and add translation-source-pipeline and canonical-mapping-review Codex skills.

### Fixed

- Align single-record translation source priority with the batch resolver (first real candidate wins), verify translation candidate field SHA-256 against UTF-8 text, and correct Markdown code fences in source-chain documentation.
- Bind Stage 3 source evidence to independently audited ClassicUA revision/file/field provenance; reject forged or unverifiable persisted evidence while retaining reviewed canonical IDs across translation-only updates.

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
