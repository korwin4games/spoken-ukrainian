# Codex task — complete Stage 3 canonical identity mapping

> **Status: implementation task (not evidence of completion).** Current branch: `feat/stage3-canonical-mapping`. The already committed `adapters/crosswalk.py` and `tests/test_crosswalk.py` are a **foundation only**; they do not contain a real verified Spoken canonical inventory or accepted ClassicUA→Spoken mappings. Do not describe this stage as finished until the acceptance gates are met.

## Goal

Implement deterministic, maintainable, *evidence-backed* identity crosswalks between effective Ukrainian units of the pinned ClassicUA `1770d208ad853d23d61105cf510d53804770d916` and canonical IDs in the pinned public Spoken `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`. Separate mapping identity validity, translation review, Ukrainian grammar review, AI eligibility, audio freshness, and **runtime display readiness**.

The only deliverables are source adapters, validated **minimal evidence records**, metadata-only impact/coverage reports, tests and documentation. Do not create translation-bearing packs or audio.

## Read before editing

1. `AGENTS.md` and `docs/ARCHITECTURE_UNMODIFIED_SPOKEN.md` (binding: **do not modify/fork/patch/monkey-patch Spoken**).
2. `docs/STAGE_3_SPECIFICATION.md`, `docs/IMPLEMENTATION_PLAN.md` (Stage 3 acceptance), `docs/SOURCE_INTEGRATION.md` and `docs/COMPATIBILITY_MATRIX.md`.
3. `docs/STAGE_2A_IMPLEMENTATION.md`, `docs/STAGE_2A_TESTING.md`, `docs/STAGE_2B_COMPATIBILITY.md`, `docs/STAGE_2B_TESTING.md`, `docs/CLASSICUA_PERMISSION.md`.
4. `.agents/skills/classicua-adapter/SKILL.md`, `.agents/skills/code-reviewer/SKILL.md`, `.agents/skills/spoken-runtime-contracts/SKILL.md`.
5. Current `adapters/crosswalk.py` and `tests/test_crosswalk.py`; inspect the actual Stage 2A model/parser before changing semantics.
6. Read and validate `sources.lock.json`. Do not advance the pins or use moving branches.

## 3A — Finish the safe, source-semantic unit model

- Reuse `Dataset` built by the existing `audit_checkout()`/effective resolver. **Never parse ClassicUA with ad-hoc regex or execute its Lua.**
- Review and strengthen the foundation's `effective_units()` extraction against **actual pinned source table schemas**, especially:
  - Quest fields 2/4/5, faction/shared override and AI exclusion rules; retain source record category and source-to-voice variants. A faction-specific row overrides *the entire shared row*; missing slots are still missing.
  - Gossip: distinguish the actual source NPC/hash/common/code structures from Spoken's canonical moment identity. Numeric ClassicUA hashes are **not** Spoken MD5/g: IDs; `!code` is replaced as a unit, not recursively merged.
  - Readables: item ID vs owner/book vs canonical page; object title and `h1` namesakes, missing middle pages, chain order, inherited SoD entries, empty Forever tables. Never equate ClassicUA item ID or page ordinal with a Spoken `b:` page ID.
  - Places ClassicUA zone names are **terminology only**, not translated lore. Boss stories are not provided by ClassicUA; these categories must not silently count as translated coverage.
- Make source IDs stable across revised translation bodies and origin line-number drift. Hash name-bearing source keys in report output; no raw copyrighted source text or namesake titles in tracked JSON.
- Identify and **test source fields that must not be considered narratable** (quest title/objective, unsupported Gossip options, namesake `h1`, metadata, empty/nil fields); if the existing foundation's simplified filter is wrong, correct it before adding mapping.
- Keep distinct `source_origin`, field SHA-256, identity/matching evidence digest, grammar summary, AI marker and predecessor references. Audit hashes/provenance are data, never inferred from translated strings.

## 3B — Independently verify public canonical target identities

- Implement `adapters/spoken/` (or equivalent) reading **immutable public** checked-out files at the pinned Spoken revision using `git show <pin>:<path>` and digest validation. No private Spoken database, production API or guessing unseen data.
- Provide canonical index evidence where the pinned public source contains sufficient detail: quests `q:<questID>:accept/progress/complete` **plus eligibility, wording/voice variants**; Gossip `g:` existing stems plus verified NPC/object/greeting/voice context; Readables `b:<pageTextID>` plus owner/page-chain/checksum; Places `z:` and `s:` keys; Bosses `boss:` map/key.
- Demonstrate valid source-to-target **join evidence**, not merely validity of each side separately. Existing `VerifiedTarget` and `VerifiedJoin` are deliberately strict placeholders: improve them as required, but **never accept a target merely because its ID is syntactically valid**.
- When pinned public source does not expose a reliable canonical ID or its join context, report `unresolved/ambiguous` with machine reason and evidence sought. Do not fabricate a stand-in, hash a Ukrainian name into a canonical ID or broaden fuzzy matching to manufacture coverage.
- Record canonical source ref/path, blob SHA-256, pinned revision and reviewed join evidence. Store minimal hand-reviewed decisions only; don't commit bulk source snapshots, full corpus dumps or translation text.

## 3C — Reviewed mapping and version-aware effective diff

- Extend `MappingDecision` so independently approved **identity joins** persist across separately reviewed source versions when identity evidence remains valid. Mapping review must be independent from text, grammar, AI and future audio-review flags; a text hash difference does not automatically change a canonical ID.
- Add deterministic candidate validation, ambiguity/exclusion reasons, identity invalidation and stable canonical alias/voice checks. Reject an unverified join and a changed speaker, owner, page chain, voice variant, or target revision until reviewed.
- Compare two separately pinned ClassicUA datasets using the **existing effective resolver**: added, removed, changed, unchanged, source-only masked edits, origin-only changes, AI/review changes and identity changes. Explain hidden prior-layer overrides and prevent false change reports for a source file-hash-only edit not affecting an effective unit.
- Mark old audio stale where the recording text or rendering changed (no actual MP3/TTS), flag changes in grammatical template status, require independent review for AI content, retain stable reviewed mapping on harmless wording changes.
- Keep update-check routines **offline, read-only, opt-in**, never silently change `sources.lock.json`. Implementing an automatic downloader, scheduled updater, apply/merge or release is **not** part of Stage 3.

## 3D — Validation reports and coverage

- Design and test a versioned reviewed-mapping file schema (small synthetic example only) and an optional CLI that validates locally pinned inputs and writes **only metadata** to ignored `build/`. Do not save raw translated bodies or unreviewed raw English dialog strings in Git, CI or logs.
- Coverage denominators must explicitly distinguish: resolved source units; supported Spoken target units **actually inventoried**; confirmed unique canonical join intersections; rejected/unresolved candidates; AI-marked/excluded units; and blocked player display surfaces.
- Output stable, sorted, reproducible metadata JSON with granular machine reasons; no text from ClassicUA may appear even in error messages. Test determinism across reordering and SHA changes.
- Keep source and target ID namespace validation strict, but support independently verified aliases/variants instead of re-minting IDs.
- Add a human-review procedure: what exact public evidence is needed to accept quest/Gossip/readable/zone/boss joins, how to review grammar, and when to invalidate an audio take.

## Required tests

Add synthetic fixtures for all cases in `docs/IMPLEMENTATION_PLAN.md` Stage 3 and `docs/STAGE_3_SPECIFICATION.md`, including: overrides masked by Forever, sparse fields, faction/shared conflict + AI filter, Gossip `!common` and `!code`, options vs greetings and multiple NPC voices, same-name objects with different `h1`, reused titles, shared/missing-middle pages and book owners, unknown/unavailable target IDs, title-only ambiguity, speaker/voice/page-chain changes, Unicode/grammar templates, changed text with stable mapping but stale audio, changed AI eligibility without text change, and no raw-body leaks.

Tests must use actual pinned public functions or source-verified golden naming/checksum vectors wherever possible; synthetic fixture text only. Separate source-level observations from client behavior. **No in-game validation is claimed by these tests.**

Run:
```sh
uv run --locked python tools/version.py check
uv run --locked python tools/build.py
uv run --locked python -m unittest discover -s tests -v
```

The diagnostic ZIP must remain byte-identical, SHA-256:
`5a2519858229c9aa004dbef075d1c8c51561e33f09828112504e0558005c8a8e`.

## Documentation, status and decisions

- Add `docs/STAGE_3_IMPLEMENTATION.md` explaining completed vs blocked functionality and public identity evidence, with exact tested command outputs.
- Add `docs/STAGE_3_TESTING.md` and concise metadata review examples that contain **invented** text only.
- Update both README status tables and `CHANGELOG.md` > `[Unreleased]` when implemented; don't imply everything works because an index exists.
- No release/version bump, TTS, addon patch/fork, source-pin change, translated package, external paid API, commit of third-party text, merge, tag or publication.
- Preserve Stage 2B's known limitations on `enUS`/non-client `ukUA` and the manual tests still pending for Quests/Gossip/Readables/Bosses. Readables text-only delivery remains blocked.

**Stop after Stage 3.** Report exact verified source/target coverage, unsupported identities and blockers rather than claiming fictional full completion. Do not push, open a PR or merge without another explicit request.
