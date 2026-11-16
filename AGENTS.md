# Instructions for coding agents

## Project
Spoken Ukrainian is an independent WoW Forever `ukUA` Community Packs project. Spoken Player and ClassicUA are external repositories. A Community Pack is not a replacement for the player; `ukUA` is a content language, not a Blizzard client locale.

## Read relevant context
- `README.md`: supported commands and current implementation.
- `docs/IMPLEMENTATION_PLAN.md`: architecture, stages and gates.
- `docs/PRODUCT_PRIORITIES_2026_11.md`: current explicitly updated execution order: Compendium UI, Places, Readables (Books and Notes), Bosses; defer Quests/Gossip.
- `docs/SOURCE_INTEGRATION.md`, `docs/COMPATIBILITY_MATRIX.md`: source semantics and runtime limitations.
- `docs/LEGAL_AND_ATTRIBUTION.md` (historical Stage 0), `docs/CLASSICUA_PERMISSION.md` (subsequent approval), `THIRD_PARTY.md`: third-party rights.
- `docs/STAGE_1_*.md` and `docs/STAGE_2A_*.md`: implemented behavior and tests.
- `sources.lock.json`: pinned source commits and hashes.
- `docs/STAGE_3_SPECIFICATION.md`: canonical ID mapping, future ClassicUA updates, review invalidation and source diff requirements.
- `docs/ARCHITECTURE_UNMODIFIED_SPOKEN.md`: binding no-fork/no-patch architecture and fallback choices A/B/C.
- `docs/APPROVED_MODULES_AND_FALLBACK.md`: exactly four approved official module targets and the separately tested text/audio fallback policy.
- `docs/TRANSLATION_SOURCE_CHAIN.md`, `config/translation_sources.json`: offline provider ordering, remaining-record processing, mock rules and coverage reporting.
- `docs/STAGE_3_IMPLEMENTATION.md`: current **zero approved real joins**, evidence gates and effective-diff behavior.
- `docs/STAGE_4A_INVENTORY_COVERAGE.md`: read-only pinned Spoken English-original indexing and metadata-only source-coverage dry-run; not real translation coverage.
- `docs/STAGE_4B_REVIEW_WORKBENCH.md`: real pinned Quest candidate review queue; manual reject/defer and explicit two-reviewer Stage 3 identity approval.
- `docs/STAGE_4C_REVIEWED_QUEST_BRIDGE.md`: synthetic-only independently reviewed Quest identity → audited effective ClassicUA field bridge; not yet part of Stage 4A CLI.
Read only what the task needs; do not use old planning notes as proof of current behavior.

## Active product priorities
- Near-term user-facing Ukrainian text priority is **P0 Compendium UI chrome**, **P1 Places lore**, **P2 Readables books/notes**, **P3 Bosses stories**. Quests/Gossip mapping and local reviewer UI are deferred, not deleted. Treat Compendium as a shared core UI, **not** an added fifth Community Pack.
- Runtime blockers are distinct: core UI labels follow actual `GetLocale()`; Places has no safe per-record English story fallback; Readables text-only records need safe no-audio handling and Compendium text selection; Bosses need an explicit story language resolver and content rights. Work only on supported/rights-cleared slices and report blockers truthfully.
- This feature order is **not** `config/translation_sources.json` provider order. Do not reorder providers or change the four agreed official modules to implement feature priority.

## Hard boundaries
- Do not modify upstream Spoken/ClassicUA checkouts or installed game AddOns unless specifically authorized.
- Do not call production APIs, spend TTS credits, publish packs/releases, or change the player to bypass language restrictions.
- ClassicUA maintainer granted project-specific permission for translation use, adaptation, AI TTS and distribution (see `docs/CLASSICUA_PERMISSION.md`). Follow the requested attribution and maintain provenance. Use invented text in committed fixtures; do not commit source snapshots, bulk translation corpora or audit dumps by default. Any change to that policy or content publication requires an explicit scoped task and independent third-party rights review.
- Keep `build/` and `dist/` ignored, and preserve Stage 1 diagnostic archive determinism.
- Stage 4C `adapters/reviewed_bridge.py` may bind *independently reviewed* Quest mapping decisions to exact audited effective ClassicUA fields, but **only as pending Ukrainian candidates**. It must refuse stale/missing source or target evidence and duplicate source-to-target binding; no real reviewed joins, content approvals or CLI integration exist yet.
- Stage 4B workbench `tools/stage4b_workbench.py` may propose Quest ID/event **candidates**, but never auto-approves. Manual reject/defer decisions are pinned to source/target revisions and evidence digests (workbench schema v2), fail closed on changes, and are not canonical joins. Only an independently inspected, explicit `JoinProof` with separate evidence and mapping reviewers can enter the audited Stage 3 `review_file` schema. Identity approval never approves content/grammar/AI/rights/audio/runtime. The default/CI workbench must keep all real approval counts zero until humans independently supply proofs.
- Use canonical Spoken identities, never guessed mappings from translated names. Do not treat ClassicUA item IDs as Spoken page IDs or numeric Gossip hashes as Spoken moment IDs.
- Honor the explicit order and membership of `config/translation_sources.json` (see `docs/TRANSLATION_SOURCE_CHAIN.md`), including English-only or no English. Empty `sources: []` or `{}` means actual WoW client `GetLocale()` with **no source calls**; never spoof it. Given an indexed canonical Spoken object list, process providers in sequential passes, passing only not-yet-translated objects to each next provider. Track provider and provisional status for each ID; report per-source found/remaining/total and differentiate candidates from **approved** translations. `another` is stub-only and `own_translator` mock-only; neither may silently approve mappings, text, rights, audio or publication. Never generate an override from an unresolved record.
- The translation provider pipeline (`adapters/translation_sources.py`) is an **offline prototype**, not connected to the Stage 3 report CLI or a production pack builder. Stage 4A can now read the **real pinned Spoken ID inventory and verified original English wording** through `tools/stage4_coverage.py`, but **does not bind any ClassicUA field without separately approved source→target mapping evidence**. Preserve its single-record/batch first-real-candidate semantics; require matching UTF-8 content fingerprint and provenance. Any candidate remains pending independent identity/content/rights review. Rejected candidates' retry with lower-priority sources is **future design**, not implemented behavior.
- An explicit `original_english` is an offline source selection, **not** proof of per-record English text fallback in a live Spoken module. In particular, Places has no per-record fallback in the pinned baseline. Empty provider policy means real client locale **for every canonical ID**, including Places/Bosses or any ID lacking a verified English original, and no provider calls, not English. Track `original_verified` independently and never construe locale selection as proof of localized text.
- Use exactly four module targets: `Spoken_Quests` (**includes Gossip**), `Spoken_Places`, `Spoken_Readables` and `Spoken_Bosses`. Do not create a fifth Gossip module or treat historic Zones/Books labels as current modules.
- Do not spoof `GetLocale() == "ukUA"`, create fake audio, monkey-patch player internals or claim independent text display without verified module support.

## Integration policy — unmodified Spoken Player
- **Primary strategy A:** ship standalone `ukUA` Community Packs using only actual public Spoken contracts; **optional strategy B:** allow an independently installed ClassicUA addon to translate native game windows. ClassicUA's native UI translation does not establish Ukrainian Spoken captions or Compendium support.
- Do **not** fork, patch, vendor, overwrite, repackage, monkey-patch or inject into Spoken Player or its modules. No `GetLocale()` spoofing, rewriting private globals, fake/silent audio or fabricated metadata.
- If a module lacks a safe public text-only/display contract (especially Readables on `enUS`), mark the feature **blocked**. Preserve exact Stage 2B test findings, fallback and manual-test status; never silently work around it.
- Upstream API suggestions and issue drafts are documentation only, not an obligation to implement player code. Future official upstream releases may be considered via an independently approved, pinned compatibility update.
- **Optional strategy C** (a separate addon with its own UI) is a future architectural investigation requiring explicit authorization. It must use public WoW APIs without modifying Spoken internals and must not claim to translate existing Spoken windows.
- Read `docs/ARCHITECTURE_UNMODIFIED_SPOKEN.md` before designing, reviewing or publishing runtime integrations. Runtime readiness and source mapping are separate gates.

## Translation updateability (Stage 3 and later)
- Treat ClassicUA as a **versioned upstream input**, not a one-time copy. Design mappings to work across explicitly reviewed new ClassicUA revisions and to reuse confirmed canonical Spoken IDs.
- See `docs/STAGE_3_SPECIFICATION.md` before implementing ID crosswalks, update detection, diff reports or pack rebuilds. Do not implement a source updater just because this policy exists.
- Pin both repositories by commit and relevant file hashes in `sources.lock.json`; never build from a silently advancing branch or automatically update the lock during a normal build.
- Compare **effective resolved records** after actual ClassicUA load/override semantics, not raw git line changes. Ignore source edits that cannot affect effective output; distinguish added, modified, removed, unchanged and ambiguous records.
- Preserve stable source-to-Spoken crosswalk decisions across revisions when identity evidence stays valid. A changed **effective text** resets dependent content/grammar review and flags affected audio as stale; a **source-file-only SHA/line-number change** does not automatically invalidate unchanged effective content or mapping. Identity-context changes require mapping review. Never re-mint a Spoken ID from a translation change.
- Keep reviewed mapping decisions and minimal provenance in Git, not translated text. Reports and temporary normalized content belong only in ignored local build output; never commit source translation bodies, raw diffs, audio or derived packs without explicit permission.
- Detect downstream impact separately for text, templates, matching/identity, AI-review flags and existing voice takes. If recording text changes, mark dependent audio stale until it is reviewed or regenerated under authorized TTS rights.
- Future update checks may propose a PR with hashes, counts, changed IDs and risks; **never automatically merge, release, publish packs or make paid TTS calls**. Follow the ClassicUA permission scope/attribution in `docs/CLASSICUA_PERMISSION.md` and each Spoken runtime display contract.

## Project versioning and release discipline
- Read `docs/VERSIONING.md`, `CHANGELOG.md`, and `VERSION` before a versioning or release task.
- `VERSION` is the single source of truth for the **project** version (currently `0.0.1`). Read it with `python3 tools/version.py show`; never add another hardcoded project-version constant.
- Project and addon versions are independent. In particular, the diagnostic addon's `.toc` version is `0.1.0`; do not synchronize it with `VERSION`, change its proven archive, or alter dependency versions in `sources.lock.json` as part of a project bump.
- Use the repository's strict numeric `MAJOR.MINOR.PATCH` policy: PATCH for fixes, MINOR for features; during 0.x, breaking changes may use MINOR but must be labeled **BREAKING** in the changelog. The first stable MAJOR requires explicit approval and `--approve-stable`; do not assume Stage 2B or Stage 3 completion implies a release.
- During ordinary development, describe notable changes under `CHANGELOG.md` > `[Unreleased]`. **Do not bump versions automatically for every commit, fix, feature or completed stage.** Bump only when the task expressly requests release/version preparation.
- For a requested bump, first inspect Git state, version and changelog. Use `python3 tools/version.py bump patch|minor|major --dry-run` to preview, then the supported bump command. The CLI updates **only** `VERSION`: prepare the matching new dated changelog section separately, preserve history, and run `python3 tools/version.py check`. A check failure between the bump and changelog edit is expected; do not bypass validation.
- CI validates version/changelog consistency. If verifying a project tag, use `python3 tools/version.py check --tag vX.Y.Z`. Never create, move, push tags, merge release PRs, publish GitHub Releases or publish Community Packs without explicit authorization and required content permissions.
- Annotated Git project tags use `v<project-version>`; tag creation, Git pushes and GitHub Releases are separate decisions from incrementing the version.

## Documentation parity and reporting
- Keep `README.md` and `README.uk.md` aligned on architecture, module count, default/empty provider policy, verified stage status, synthetic examples and links to the editable draw.io/SVG diagrams. Translate prose, not source identifiers or shell commands.
- Distinguish **source candidates**, **reviewed canonical joins**, **approved Ukrainian text**, **audio availability** and **runtime display support** as separate counts/gates. Every table must label its denominator; never call synthetic examples or Stage 3 source candidate counts real coverage.
- Document known limits (0 approved real joins, Another stub, Own Translator mock, client-locale supplied by caller, no production pipeline wiring) until independently verified evidence changes them.
- Documentation-only changes: check Markdown fences, image/relative link paths and bilingual parity; the standard CI remains the source of build/test confirmation.

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
- `.agents/skills/canonical-mapping-review/SKILL.md` — independent Stage 3 source-to-Spoken identity evidence and review invalidation.
- `.agents/skills/translation-source-pipeline/SKILL.md` — provider priorities, offline batch resolution, metadata-only coverage and mock/English/client-language rules.
- `.agents/skills/code-reviewer/SKILL.md` — risk-first review of changes and PRs.
- `.agents/skills/spoken-runtime-contracts/SKILL.md` — language, text-only and audio runtime contracts.

Use concise English for technical instructions; explain results to the user in Ukrainian when appropriate.
