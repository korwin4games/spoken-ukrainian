# Instructions for coding agents

## Project
Spoken Ukrainian is an independent WoW Forever `ukUA` Community Packs project. Spoken Player and ClassicUA are external repositories. A Community Pack is not a replacement for the player; `ukUA` is a content language, not a Blizzard client locale.

## Read relevant context
- `README.md`: supported commands and current implementation.
- `docs/IMPLEMENTATION_PLAN.md`: architecture, stages and gates.
- `docs/SOURCE_INTEGRATION.md`, `docs/COMPATIBILITY_MATRIX.md`: source semantics and runtime limitations.
- `docs/LEGAL_AND_ATTRIBUTION.md`, `THIRD_PARTY.md`: third-party rights.
- `docs/STAGE_1_*.md` and `docs/STAGE_2A_*.md`: implemented behavior and tests.
- `sources.lock.json`: pinned source commits and hashes.
Read only what the task needs; do not use old planning notes as proof of current behavior.

## Hard boundaries
- Do not modify upstream Spoken/ClassicUA checkouts or installed game AddOns unless specifically authorized.
- Do not call production APIs, spend TTS credits, publish packs/releases, or change the player to bypass language restrictions.
- ClassicUA redistribution, adaptation and TTS rights are unresolved. Use invented text in committed fixtures. Never commit copied translations, source snapshots, translated corpora or audit dumps.
- Keep `build/` and `dist/` ignored, and preserve Stage 1 diagnostic archive determinism.
- Use canonical Spoken identities, never guessed mappings from translated names. Do not treat ClassicUA item IDs as Spoken page IDs or numeric Gossip hashes as Spoken moment IDs.
- Do not spoof `GetLocale() == "ukUA"`, create fake audio, monkey-patch player internals or claim independent text display without verified module support.

## Project versioning and release discipline
- Read `docs/VERSIONING.md`, `CHANGELOG.md`, and `VERSION` before a versioning or release task.
- `VERSION` is the single source of truth for the **project** version (currently `0.0.1`). Read it with `python3 tools/version.py show`; never add another hardcoded project-version constant.
- Project and addon versions are independent. In particular, the diagnostic addon's `.toc` version is `0.1.0`; do not synchronize it with `VERSION`, change its proven archive, or alter dependency versions in `sources.lock.json` as part of a project bump.
- Use the repository's strict numeric `MAJOR.MINOR.PATCH` policy: PATCH for fixes, MINOR for features; during 0.x, breaking changes may use MINOR but must be labeled **BREAKING** in the changelog. The first stable MAJOR requires explicit approval and `--approve-stable`; do not assume Stage 2B or Stage 3 completion implies a release.
- During ordinary development, describe notable changes under `CHANGELOG.md` > `[Unreleased]`. **Do not bump versions automatically for every commit, fix, feature or completed stage.** Bump only when the task expressly requests release/version preparation.
- For a requested bump, first inspect Git state, version and changelog. Use `python3 tools/version.py bump patch|minor|major --dry-run` to preview, then the supported bump command. The CLI updates **only** `VERSION`: prepare the matching new dated changelog section separately, preserve history, and run `python3 tools/version.py check`. A check failure between the bump and changelog edit is expected; do not bypass validation.
- CI validates version/changelog consistency. If verifying a project tag, use `python3 tools/version.py check --tag vX.Y.Z`. Never create, move, push tags, merge release PRs, publish GitHub Releases or publish Community Packs without explicit authorization and required content permissions.
- Annotated Git project tags use `v<project-version>`; tag creation, Git pushes and GitHub Releases are separate decisions from incrementing the version.

## Changes and verification
1. Inspect `git status`, branch and task scope; do not discard existing changes.
2. Use focused edits, synthetic fixtures and source-backed tests. Source adapters read pinned local checkouts without executing arbitrary Lua.
3. For code or build changes, run:
   `python3 tools/version.py check`
   `python3 tools/build.py`
   `python3 -m unittest discover -s tests -v`
   Stage 1 tests require pinned Spoken and system Lua 5.4.
4. For optional real-source audits, run:
   `python3 tools/classicua_audit.py --source /absolute/path/to/clean-pinned-ClassicUA`
   Outputs must remain under ignored `build/` and contain metadata only.
5. Report verified results, untested in-game behavior, regressions and unresolved permissions.
6. Never push, merge, tag or publish without the user's explicit instruction.

## Repo-local Codex skills
Use these workflows when the task matches their descriptions:
- `.agents/skills/classicua-adapter/SKILL.md` — parser, overrides, grammar, source audits.
- `.agents/skills/code-reviewer/SKILL.md` — risk-first review of changes and PRs.
- `.agents/skills/spoken-runtime-contracts/SKILL.md` — language, text-only and audio runtime contracts.

Use concise English for technical instructions; explain results to the user in Ukrainian when appropriate.
