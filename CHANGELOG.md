# Changelog

All notable changes to Spoken Ukrainian will be documented here.
This project follows Semantic Versioning and the Keep a Changelog structure.
Dated version sections describe project baselines; they do not imply that a Git tag
or GitHub Release has been published.

## [Unreleased]

### Added

- Add a metadata-only, spreadsheet-safe Stage 4B.1 CSV review worksheet (one row per Quest target/voice variant), with synthetic regression tests and a short-lived real pinned-source CI artifact for the first 40 Horde source units; no translation bodies or automatic reviews.
- Stage 4B pinned Quest canonical-ID mapping review workbench: metadata-only 40-record Horde/Alliance review queue, deterministic evidence/variant hints, strict manual reject/defer decisions, and explicit two-reviewer Stage 3 JoinProof approval with revalidation. Synthetic tests and real-checkout CI; no real approvals, Ukrainian packs or release actions.
- Add Stage 4A offline pinned public Spoken English-original index and configurable source-coverage CLI: sequential source passes over verified canonical original texts, full-inventory metadata accounting, and strict zero-unreviewed-join behavior; synthetic regression tests and honest coverage docs. No real mapped translation or live fallback is implemented.
- Record approved four-module policy and configurable ordered translation sources. Add an offline, sequential Spoken-inventory candidate resolver, provider/remaining/total metadata coverage reports, synthetic tests, and editable draw.io/SVG architecture diagrams. `another` remains stub-only; `own_translator` is a non-publishable mock; `[]` / `{}` selects the real client locale. No real identity joins or translated packs are approved.
- Add Stage 3 pinned public canonical inventories, independently reviewed join-proof validation, persistent metadata review schema, offline two-revision effective comparison, coverage/impact CLI, and 23 additional tests. Real mapping acceptance remains pending: zero independently approved real joins; runtime display gates remain unchanged.
- Add Stage 2B pinned Lua runtime characterization, per-surface compatibility evidence, manual Forever checks and minimal upstream text/audio API proposals.
- Document ClassicUA's project-specific permission and required attribution; explain the planned user experience and translation update workflow in README.
- Add a Ukrainian README (`README.uk.md`) and language links between the English and Ukrainian guides.

### Changed

- Refresh English/Ukrainian READMEs with the four approved modules, configurable provider chain, sequential candidate accounting, synthetic coverage example and editable diagram; document current offline/runtime limitations. Clarify AGENTS.md guidance on mapping invalidation and bilingual parity, update existing code-review/runtime/ClassicUA skills, and add translation-source-pipeline and canonical-mapping-review Codex skills.

### Fixed

- Stage 4A empty-provider policy now selects client locale for every canonical Spoken ID, independently tracking whether an English original is verified; align optional source identity typing and clarify four modules vs five content families.
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
