# Changelog

All notable changes to Spoken Ukrainian will be documented here.
This project follows Semantic Versioning and the Keep a Changelog structure.
Dated version sections describe project baselines; they do not imply that a Git tag
or GitHub Release has been published.

## [Unreleased]
- Add the optional Ukrainian Interface Pack for Spoken 3.10.1, with English fallback for untranslated labels.
- Share the private Quest and Gossip editor, module creation, and build-before-install workflow. Start Gossip in a fresh SQLite choice scope while retaining its historical ledgers.
- Reproduce the historical Gossip matching counts against independently pinned Spoken 3.9.0 and 3.10.1, with verified ClassicUA comment provenance and private canonical-ID evidence.
- Cache Quest and Gossip catalogs independently, reuse verified source indexes, and add opt-in Translation Manager timings.
- Let Quest reviewers compare and register candidates, draft directly against verified context, and confirm a translation across all verified originals. Verify the selected text in the Quest ZIP before applying the decision.
- Translate supported Forever Quest Journal widgets and use an OFL-licensed Ukrainian-capable font in Quest surfaces.
- Limit Translation Manager workers to ten minutes and publish staged changes only after a successful worker response.
- Separate translation conflicts from mapping status in the local manager. Add candidate eligibility, pending Quest registration and drafts, and a guided Stage 3 review form.
- **BREAKING** Split Quest and Gossip into independently installable local addons and ZIPs with separate SQLite build heads. The root manager handles module-scoped builds and inline review. Move the legacy combined addon out of AddOns before upgrading.
- Enforce Quest mapping decisions across local imports, deduplicate shared ClassicUA faction evidence, and expose verified original variants, distinct mapping and import states, and Gossip diagnostics in Translation Manager.
- Add a module-centered local Translation Manager with unified Quest/Gossip browsing, staged reimport and optional scoped test reset.
- Add the optional local Translation Review Agent, explicit verified import for private test builds, separate source/provider comparisons and bilingual CLI guides.

### Gossip provisional machine imports

- Add auditable ClassicUA Gossip 1:1 import, CLI and localhost Review UI panel with status filters. Persist exact pinned provenance and version history in SQLite; preserve human decisions, exclude ambiguous hashes/contexts, and hold source changes as pending updates.
- Refresh Quest and Gossip imports before local test builds. Include only verified provisional Gossip matches with human/source-selection precedence. Add schema v5 fingerprints and latest-build tracking; distinguish unique texts, NPC/hash occurrences, common fallbacks, recorded imports and actual ZIP contents. No human approval, provider calls, audio or public release.

### Native Gossip — integrated Quest local test

- Include pinned ClassicUA exact NPC-ID/English-hash Gossip greeting and player-reply translations in the existing `Spoken_Quests_UA` test addon (separate `GossipTranslations.lua` data and `GossipFrame.lua` runtime). Reuse Shift-to-original and yield to installed ClassicUA; retain English on absent/mismatched identities. No new `Spoken_Gossip_UA` pack, fake audio, Spoken captions, approved canonical Gossip mapping or public release.
- Update deterministic ZIP/installer contracts, synthetic Lua tests, CI archive smoke tests and EN/UK test instructions. Generated translation bodies stay in ignored private `dist/`; original Spoken/ClassicUA and source pins remain unchanged.

### Local review workflow

- Extend PR #14 with separate Quest Mapping/Translation Review, explicit independently attested Stage 3 mapping approval, local text editing/version history, four-part content approval and deterministic explicit inert import. No real approvals, packs, runtime activation, TTS or source pin changes.
- Add a strict private schema-v1 translation ledger under ignored `build/`, atomic/fsynced writes, concurrent-writer detection, provider provenance and optional `store_locally` policy. Reuse approval only for equivalent original/text/context; preserve edits and reject stale/conflicting imports.
- Document reviewer workflow, source updates, schema compatibility, local recovery and exact UI/import/test commands in both READMEs and architecture guides; extend synthetic workflow and HTTP security tests.

### Added

- Add a loopback-only Stage 4B.2 Quest review browser UI with audited ClassicUA vs verified Spoken English text side by side, variant metadata, evidence-bound reject/defer actions, local HTTP security checks and synthetic tests. No automatic identity/content approvals, published translated content, TTS or addon changes.
- Add a metadata-only, spreadsheet-safe Stage 4B.1 CSV review worksheet (one row per Quest target/voice variant), with synthetic regression tests and a short-lived real pinned-source CI artifact for the first 40 Horde source units; no translation bodies or automatic reviews.
- Introduce a Stage 4C **synthetic-only** reviewed Quest identity → audited effective ClassicUA source-field bridge, preserving first-source priority and strict separation between Stage 3 mapping approval and Ukrainian text approval. No real mapping joins, CLI activation, packs or releases.
- Stage 4B pinned Quest canonical-ID mapping review workbench: metadata-only 40-record Horde/Alliance review queue, deterministic evidence/variant hints, strict manual reject/defer decisions, and explicit two-reviewer Stage 3 JoinProof approval with revalidation. Synthetic tests and real-checkout CI; no real approvals, Ukrainian packs or release actions.
- Add Stage 4A offline pinned public Spoken English-original index and configurable source-coverage CLI: sequential source passes over verified canonical original texts, full-inventory metadata accounting, and strict zero-unreviewed-join behavior; synthetic regression tests and honest coverage docs. No real mapped translation or live fallback is implemented.
- Record approved four-module policy and configurable ordered translation sources. Add an offline, sequential Spoken-inventory candidate resolver, provider/remaining/total metadata coverage reports, synthetic tests, and editable draw.io/SVG architecture diagrams. `another` remains stub-only; `own_translator` is a non-publishable mock; `[]` / `{}` selects the real client locale. No real identity joins or translated packs are approved.
- Add Stage 3 pinned public canonical inventories, independently reviewed join-proof validation, persistent metadata review schema, offline two-revision effective comparison, coverage/impact CLI, and 23 additional tests. Real mapping acceptance remains pending: zero independently approved real joins; runtime display gates remain unchanged.
- Add Stage 2B pinned Lua runtime characterization, per-surface compatibility evidence, manual Forever checks and minimal upstream text/audio API proposals.
- Document ClassicUA's project-specific permission and required attribution; explain the planned user experience and translation update workflow in README.
- Add a Ukrainian README (`README.uk.md`) and language links between the English and Ukrainian guides.

### Changed

- Prioritize Ukrainian content **Places lore → Readables (Books and Notes) → Bosses → Compendium interface strings → Quests/Gossip**. Add an audited source survey: ClassicUA place-name dictionary vs UA VoiceOver publisher-reported ~900 zone/subzone histories and 1000+ book pages; external text/audio provenance and canonical matches remain unverified. Add a dependency/rights/runtime-gated roadmap; no new fifth module, source-policy change or released translation.
- Refresh English/Ukrainian READMEs with the four approved modules, configurable provider chain, sequential candidate accounting, synthetic coverage example and editable diagram; document current offline/runtime limitations. Clarify AGENTS.md guidance on mapping invalidation and bilingual parity, update existing code-review/runtime/ClassicUA skills, and add translation-source-pipeline and canonical-mapping-review Codex skills.

### Fixed

- Distinguish missing SQLite backup sources from identical paths, show corrective CLI diagnostics, preserve exclusive destination creation and reject symlinks. Open backup sources read-only, add explicit `translation_db.py init`, and keep status inspection read-only; preserve schema, approvals and review history.
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
