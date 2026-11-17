# Stage 2B task — Spoken runtime compatibility for Ukrainian text

> **Status: task specification, not implementation.** Work on `feat/spoken-runtime-compatibility`. This document defines the Codex implementation task; creating it does **not** establish that any previously unsupported Spoken module now supports Ukrainian text.

## Objective

Characterize the exact **unmodified pinned Spoken Player/module** behavior when a WoW Forever client reports `GetLocale() == "enUS"`, while Spoken registers a community content language `ukUA`.

Determine where and under what conditions independent **Ukrainian text display** is possible in **Quests, Gossip, Readables, Places and Bosses**, both **without audio** and **with genuine audio**, without breaking existing users. Establish actionable, backward-compatible requirements for any upstream extension. Give special priority to **Readables text-only** so that Stage 4 can choose a feasible first real pack.

This is research + executable characterization tests + documented recommendations. **Do not modify upstream Spoken or ClassicUA, implement a player fork, ship translated packs, generate voice files, or publish releases.**

## Context and authoritative inputs

- Read root `AGENTS.md`, then follow `.agents/skills/spoken-runtime-contracts/SKILL.md` and `.agents/skills/code-reviewer/SKILL.md` where relevant.
- Read `docs/SOURCE_INTEGRATION.md`, `docs/COMPATIBILITY_MATRIX.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/STAGE_1_TESTING.md`, `docs/STAGE_2A_IMPLEMENTATION.md`, `docs/CLASSICUA_PERMISSION.md` and `docs/VERSIONING.md`. Historical Stage 0 rights conclusions are superseded by the explicit ClassicUA permission record.
- Use the exact Spoken revision and file hashes in `sources.lock.json` (currently `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`). The pinned Spoken implementation is the runtime **baseline**; check present upstream issues/releases for relevant fixes as a separate evidence category, but do not change the pin or tests to a new revision without explicit scope.
- Inspect actual implementation and data/TOC registration paths, especially `addons/Spoken/{Languages,API,SoundQueue}.lua`, `addons/Spoken_Quests/{Language,DataModules}.lua`, `addons/Spoken_Readables/{Language,Audio,Reader,Core}.lua`, `addons/Spoken_Readables/UI/`, `addons/Spoken_Places/{Language,Core,Audio}.lua`, and `addons/Spoken_Bosses/{Audio,Core}.lua` and its UI.
- Public upstream community packs guidance: https://github.com/rusty-key/spoken-wow/blob/master/community/README.md
- Existing upstream Ukrainian coordination: https://github.com/rusty-key/spoken-wow/issues/1123 ; look for an actual maintainer answer about Readables; do not pretend an unanswered question is an upstream commitment.
- ClassicUA maintainer permission: https://github.com/greenya/ClassicUA/issues/100#issuecomment-6917008199 — translation use/adaptation, AI TTS and distribution allowed with attribution. This **does not** mean the module runtime supports Ukrainian text; third-party stories/fonts and eventual provider terms still need review.

## Work package A — Pin, scope and executable harness

1. Check `git status` and current branch; preserve unrelated local changes. Do not rebase, merge, force-push or delete files.
2. Review existing Stage 1 Lua runner (`tests/lua_runtime.py` and `tests/contract.lua`). Extend or reuse the same testing approach rather than inventing a second unrelated framework. Preserve the existing diagnostic ZIP and regression tests.
3. Add focused, **offline** synthetic tests exercising **real unmodified upstream Lua function bodies** wherever practical. Read them from an existing separate pinned Spoken checkout. Clearly label any fallback static-analysis assertions; do not describe textual source inspection or a reimplemented mock as executable verification of upstream runtime.
4. Mock only essential WoW APIs, addon metadata, saved settings, addon enablement, frames/fonts and optional real-audio availability. Model `GetLocale()` truthfully as `enUS`. Preserve load order.
5. Do not create fake or silent MP3s, bogus `file`/duration entries, `ukUA` client-locale spoofing, unapproved monkey patches or modified upstream copies. For the “audio present” case, use a test fixture representing an actually valid clip entry/path contract without trying to play an invented file.
6. Distinguish: (a) native WoW game window, (b) Spoken narrator caption, (c) Azeroth's Compendium page, (d) Places lore panel, and (e) playback/audio availability. A translated game window (potentially due to ClassicUA hooks) is not proof of a Ukrainian Spoken narrator caption.

## Work package B — Verify each module

### 1. Quests + Gossip

- Discover language registration vs matching locale vs `Voice Language` settings.
- Characterize source identification, queue creation, actual audio-file requirement, `TextByFileName`, fallback and caption selection when client is `enUS` but a supported non-client voice/language is `ukUA`.
- Exercise: available valid audio metadata, missing audio, disabled Ukrainian pack, English fallback, matched/unmatched moment, and player-dependent template cases.
- Describe whether `Spoken` provides any independently supported **text-only** path, or merely has generic text-only primitives that these modules do not use.
- Do not conflate ClassicUA gossip's numeric hashes with Spoken IDs or assume the client text is already in Ukrainian.

### 2. Readables — highest priority

- Inspect exact format-1 `SpokenReadablesAudioPacks` registration, `pages`, `ClipFor`, `HasAudio`, `CaptionText`, `Reader` and Compendium display selection logic.
- Test a minimal synthetic `ukUA` page containing **text but no `file`** and characterize precisely (i) text availability, (ii) audio availability reporting, (iii) playback request behavior/error, (iv) Compendium language selection for `enUS` and (v) possible independent text-language selection.
- Test valid-audio metadata separately from no-audio metadata; do not make tests “pass” by introducing fake files or silently dropping the failing path.
- Separate what needs to change for **audio safety** vs what needs to change for **text display**. Give the smallest credible backward-compatible upstream API/data contract, with concrete functions and file/line references.
- Provide one isolated manual **in-game test** procedure if the code behavior cannot be conclusively reproduced offline. Do not install an unsafe text-only pack into a user's game to trigger an error without an explicit and reversible test plan.

### 3. Places

- Preserve already successful diagnostic `ukUA` registration and lore display without audio.
- Characterize independent `Text Language` vs `Voice Language`, disabled/removed pack, font guard, selection/reload and English behavior.
- Show exactly why this support does not automatically imply similar support in other modules.

### 4. Bosses

- Distinguish core story text from community-pack story selection, narrator captions, audio flags and Compendium/encounter display.
- Characterize `ukUA` when `GetLocale()` is `enUS`, with and without audio.
- Determine whether existing text-only story paths can be generalized by a small **public** extension without changing existing stable identities.

## Work package C — Compatibility and upstream proposal

Create a matrix with a separate row per **module × display surface × audio condition**, containing:

- exact pinned revision and source function(s)/line ranges;
- test evidence (test name and result) vs unverified hypothesis;
- current supported/unsupported/conditional status;
- English fallback and missing-pack behavior;
- smallest necessary upstream change, if any;
- explicit manual Forever test still required.

Propose a minimal **upstream-first** design with independent content-text and voice-language selection, separate `HasText`/`HasAudio` semantics, safe absence of `file`, explicit locale/fallback behavior and backward compatibility with existing community packs. Avoid modifying the player inside this repository.

For changed APIs, provide illustrative interface signatures or pseudocode in a design document **only**, not a working player fork. Identify any potential need for upstream maintainer discussion and supply a proposed issue/PR description without submitting it.

## Work package D — ClassicUA coexistence

- Separately characterize the difference between ClassicUA's translated native game frames and Spoken's own caption/Compendium sources.
- Use only synthetic fixtures in committed tests. Optional real ClassicUA inspection must use a clean pinned checkout and must not leak translated bodies into tracked files.
- Define manual testing with ClassicUA disabled and enabled, including `GetLocale()`, real addon versions, changed quest/gossip/readables surfaces, missing audio, Lua errors, language selection and settings restoration.

## Work package E — Deliverables, versions, validation

Add:

- `docs/STAGE_2B_COMPATIBILITY.md`: verified module/surface matrix; pinned function references; upstream issue status and minimum extension proposal.
- `docs/STAGE_2B_TESTING.md`: automated commands/results, limits of Lua 5.4 vs WoW runtime, and precise manual Forever acceptance checklist.
- `docs/UPSTREAM_REQUIREMENTS.md`: clear minimal API proposals (especially for Readables), backward compatibility, examples, non-goals and maintainer questions.
- Appropriate `tests/test_*.py` and optionally `tests/*.lua` characterization tests. Keep synthetic content only.
- A concise note under `CHANGELOG.md` > `[Unreleased]`, when code/tests actually change; **do not bump `VERSION`** without a separately requested release/version task.

Run at minimum:

```sh
uv run --locked python tools/version.py check
uv run --locked python tools/build.py
uv run --locked python -m unittest discover -s tests -v
```

Verify the resulting diagnostic ZIP digest remains **`5a2519858229c9aa004dbef075d1c8c51561e33f09828112504e0558005c8a8e`** (unless tests establish an authorized intentional change, which this task should avoid). Record actual test counts, unexpected gaps and evidence. An absence of a working WoW client means **manual in-game acceptance is pending**, not passed.

**Stop after Stage 2B.** Do not perform Stage 3 mapping, create any real translated pack, call TTS, update the source lock automatically, push commits, open PRs or publish releases unless explicitly instructed.

## Acceptance

1. Each of the five modules has a verifiable documented text-display vs audio/playback contract for `enUS` client + `ukUA` content language.
2. Baseline inability to display something is accurately characterized, not hidden by mocks, fake clips or unsupported locale changes.
3. Readables text-only safety and independent display are specifically tested and separated.
4. Known functioning Stage 1 diagnostic and Stage 2A tests remain green; version/changelog verification remains green.
5. The documentation proposes only minimal backward-compatible upstream changes justified by actual pinned functions.
6. No player/ClassicUA edits, translated-content exports, TTS calls, pack releases or unapproved Git actions were performed.

## Final Codex report

Summarize changed files, actual automated test results, module-by-module findings, Readables blockers, minimal upstream proposals, test harness limitations, manual in-game checks, unresolved requirements and recommended Stage 3 path. Do not claim unsupported text is working merely because a content language is registered.
