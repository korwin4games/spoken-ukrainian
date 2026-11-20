# Instructions for coding agents

- A single scoped, provenance-verified `same_template` Gossip candidate can be **automatically ready** when the English templates match and **all** required runtime placeholders match. Count documented ClassicUA grammatical forms such as `{Ім'я}`, `{Клас}`, `{Раса}` and `{стать:male:female}` as the equivalents of `$N`, `$C`, `$R` and `$G`; retain the original forms for expansion in-game. Still reject missing/extra/mismatched placeholders, unsupported inflections, NPC-scope conflicts and unverified evidence. Distinguish a truly safe sole candidate from the existence of one **unverified audit lead**. Dropdown labels must be compact; keep full references in the audit detail view.
## Gossip audit leads in the translation editor

Gossip audit candidates in `unverified_alternatives` are **evidence**, not safe NPC/hash mappings or human-approved translations. The editor may offer their **existing Ukrainian text** in a clearly labeled dropdown for explicit user review. Selecting one fills the textarea only; it must not save, approve, auto-import, or call `choose_gossip` for an unverified candidate. Clicking **Зберегти** must use the regular `save_gossip` path and validate placeholders against every verified English original under the current NPC/hash. Keep English-only audit leads visible but disabled (never insert English into the Ukrainian field or fabricate a translation). Preserve existing verified candidate selection behavior and the SQLite audit history. No change to the Gossip global canonical-ID collision restrictions.

## Quest and Gossip coverage KPI (Translation Manager)

The manager must show **Покриття перекладом** for both Quest and Gossip. Use the complete *module inventory*, not the current search/filter/page. Every item belongs to exactly one UI bucket: ready-to-import takes precedence over already-built, then imported, then problematic. Coverage = (ready + imported) / total × 100, with no double counting. Show both percentage (one decimal maximum) and covered/total counts; an empty inventory displays a dash instead of a misleading 0%. Quest items are ID/event moments, while Gossip items are NPC/hash wordings. This is coverage of the manager's indexed Spoken module inventory, **not** a claim about all WoW quests, every upstream Spoken line, or verified in-game translation quality. Keep backend summary and visible UI metrics consistent with independent module selection and unfiltered counts.

## Owner-approved Quest auto-import policy — private WoW: Forever testing

This **newest Quest-specific decision overrides older Stage 3 / Stage 4 human-approval prerequisites for *local test ZIPs and Translation Manager ready status only***. Do not weaken the separate Gossip NPC/hash safety rules, approved-translation ledger semantics, mapping audit history, rights for publication or public release gates.

- Use the *pinned* ClassicUA Quest field and the *verified* Spoken **Quest ID + event** (`accept`, `progress`, `complete`) as the private test-pack mapping. Stage 3 hints and human mapping/content approval are **not required** for an automatically importable Quest entry. Never infer Quest IDs from names, unverified fuzzy text similarity, or a different event.
- If a Quest ID/event has **one distinct eligible Ukrainian translation**, automatically select it for **all verified English originals, faction-compatible contexts and wording variants of that same event**, even if the English texts differ. No reviewer action, checkbox or manual Save click is needed; show **Готовий до імпорту** immediately.
- Two or more **different eligible Ukrainian texts** for the same Quest ID/event require an explicit user choice; do not pick arbitrarily. Duplicate identical texts collapse to one candidate. Persist user choices and exact source provenance; an existing explicit valid choice takes precedence. Explicit rejections, mismatched IDs/events, opposing faction, stale changed evidence/source, missing verified originals, invalid source hashes or unsafe content remain blocked.
- The **Ready to import** status must mean the backend will include that Quest ID/event in the next private ZIP build. The UI list, detail, summary counts, ready-only CLI/build, native QuestFrame/Journal and Spoken 3.10.1 Text Pack/Compendium must use the *same* decision. Text Pack writes a single base `q:ID:event` fallback for all verified English wording/sex variants; never fabricate `:wN` or `:m/:f` entries.
- Automatic selection is **not human approval** and must not rewrite human decisions or auto-publish translations. Preserve SQLite audit history, original wording context and fallback. Record how the selection was obtained. Test actual game cases and refine exceptions based on evidence instead of demanding manual review for every Quest.
- Scope is Quest local testing only. Gossip retains its complete pinned-corpus cross-NPC collision checks and separate text/voice modules retain their independent installation contracts.


## Owner decision ? shared local module workflow

- `Spoken_Quest_UA` and `Spoken_Gossip_UA` are independent Ukrainian addons. Each module ZIP contains the selected addon and required shared `Spoken_Ukrainian` core, with its own checksum. Keep independent text and voice addons where applicable. `Spoken_Quests` remains the unchanged official Quest and Gossip target.
- Every translation module registers its identity in the shared manager and uses the simple English/Ukrainian editor. Show verified context and available choices. Allow typing, pasting, selecting, and copying a Codex prompt. Use ready, imported, and problematic states. Saves persist only local SQLite choices. Keep historical review and attestation UI out of routine editing.
- Use one **Створити модуль** action. Capture the selected module, verify its source and selections, build the private ZIP and checksum, record the successful build in SQLite, and report counts and ZIP location. Quest retains incremental merging of ready moments into its verified previous archive. Keep full rebuild separate from the primary manager.
- Use one **WoW path** field (Windows default `D:\Games\World of Warcraft`) and one **Інсталювати** action. Keep the entered path when switching modules. Build the captured module first and use the shared safe installer for `_forever_/Interface/AddOns`, including checksum, dependency and path checks, backup and rollback. Replace only that Ukrainian module and its required shared core.
- Module-specific identity, current pinned evidence, rights and placeholder checks still apply. For Gossip use a fresh versioned selection scope. Keep old SQLite decisions as history and exclude them from candidates, selections and builds. A local choice is not an approval. Bind each Gossip selection to the verified NPC and original wording/hash. Never promote uncertain audit candidates, reuse one gender branch across variants, use TTS-prepared wording as a runtime key, or widen a choice to unrelated NPCs.
- Keep the workflow private for local testing. These conventions supersede older per-module UI, legacy combined addon, and installer restrictions below.

## Spoken 3.10.1 text-pack integration (issue #38, PR #39)

- The active audited Spoken source pin is `spoken/v3.10.1` at `db5669b0a39815dd38568f0e871f4ced82bc9229`. The Quest/Gossip corpus, aliases and Stage 3 input files are byte-identical to 3.9.0; preserve legacy Stage 1/2B behavior tests against their **separate** historical 3.9.0 manifest, not the active source pin.
- Register Quest/Gossip text only through the public `Spoken:RegisterText("ukUA", "quests", ...)` API, with `X-Spoken-Text` metadata. Do not invent voice packs or synthetic sound lengths. Official `Spoken_Quests` remains required for the Compendium Quest tab but is not overwritten by Ukrainian modules.
- Canonical Spoken IDs and native ClassicUA NPC/hash lookups are different contracts. Verify all pinned English variants exist before exporting one base `q:ID:event` covering their shared Quest ID/event; different verified English wordings are allowed under the owner-approved private Quest policy, but never guess `:wN` or player-sex variant IDs. Export shared `g:...` only after checking **all** pinned corpus contexts including unselected NPCs and unsupported objects. Missing evidence, conflicting translations or unsafe tokens mean omit that Text Pack entry, retaining English fallback and native localization.
- Native Quest and Gossip hooks must remain usable regardless of the selected Spoken Text Language. The modules load normally (official Text Packs also permit non-LoadOnDemand addons), and each independently includes a Cyrillic-capable font plus license. Keep text-only and voice modules independently installable. In-game WoW: Forever verification is required before claiming acceptance.

## Project

Spoken Ukrainian is an independent WoW Forever `ukUA` Community Packs project. Spoken Player and ClassicUA are external repositories. A Community Pack is not a replacement for the player; `ukUA` is a content language, not a Blizzard client locale.

## Read relevant context
- `README.md`: supported commands and current implementation.
- `docs/IMPLEMENTATION_PLAN.md`: architecture, stages and gates.
- `docs/PRODUCT_PRIORITIES_2026_11.md`: current explicitly updated execution order: Places, Readables (Books and Notes), Bosses, Compendium UI, Quests/Gossip.
- `docs/PLACES_SOURCE_AUDIT.md`: source assessment for ClassicUA location terminology vs UA VoiceOver publisher-reported Ukrainian lore; never import unaudited bodies or audio.
- Keep `docs/IMPLEMENTATION_PLAN.md` unchanged: it is a hash-pinned Stage 0 contract. Current feature ordering belongs in the separate priorities document.
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
- `docs/STAGE_4B_LOCAL_REVIEW_UI.md`, `docs/TRANSLATION_APPROVALS.md`: local Quest mapping/content review, private versioned text storage, explicit inert import, recovery and browser/server security restrictions.
- `docs/STAGE_4C_REVIEWED_QUEST_BRIDGE.md`: synthetic-only independently reviewed Quest identity → audited effective ClassicUA field bridge; not yet part of Stage 4A CLI.
Read only what the task needs; do not use old planning notes as proof of current behavior.

- Under explicit user authorization, bulk import may store *provisional* machine-only one-to-one Quest translations in ignored private `build/machine-one-to-one.json` when both source and target candidate cardinalities are exactly one, target has a single verified English context, and pinned ClassicUA field bytes/provenance match. Do NOT construct synthetic Stage 3 JoinProof/human reviewers, call it a human approval, overwrite curated text, persist a stale automatic import, or publish machine-only content. Every output report must split machine-imported from human-reviewed versions and count full canonical Spoken inventory. Other families require separate identity contracts.
- Bulk `auto_approve_one_to_one` uses explicit local UI/CLI action only; ClassicUA is enabled in the current example policy after user authorization. It may auto-approve **content** only after an independently reviewed Stage 3 mapping, globally unique source↔target candidate, current exact provenance and rights checks. The result is an inert private `build/` import and metadata-only total-Spoken/source-coverage table, not a release or a Git text import. Never invent mapping approvals or count structural candidates as imported translations. CLI: `tools/review_ui_server.py --classicua <pinned> --spoken <pinned> --auto-import-one-to-one`.

## Local installable Quest and Gossip tests
- Current owner's requested names are **Spoken Ukrainian** for the base AddOn (`Spoken_Ukrainian`) and **`Spoken_Quest_UA`** for the Quest module. `Spoken_Quests` remains the untouched official upstream module.
- The **only** supported local package builder is `tools/build_ukrainian.py`; it **must call** the audited `auto_import_one_to_one` action before full Quest rebuilds. Do not add a skip-import/unchecked-source flag or commit the generated `Translations.lua` or test ZIP. Fail closed on missing/changed source revisions or zero unique eligible Quest moments. Treat machine imports as provisional.
- Register `Spoken_Quest_UA` through documented v1 `X-SpokenQuests-DataModule-*` metadata / `VoiceOver.DataModules:Register`, with **empty** sound-lengths. Never invent MP3s, silent files, lengths or patches to upstream audio gating. The optional standalone Quest preview only uses public WoW events and is disabled by default; **do not claim it is native Spoken captions**. No live-client acceptance is established until the user tests it. See `docs/QUEST_LOCAL_TEST_BUILD.md`.
- Issue #19 is implemented in `addons/Spoken_Quest_UA/NativeQuestFrame.lua`: independent **native NPC QuestFrame** translation for imported, audited QuestID/events with Shift-held English original; ClassicUA is an offline-only build input. Use only guarded widget-level `hooksecurefunc` with SetText reentry protection and per-Quest/moment snapshot; no global getter/Spoken monkey-patches. Yield to runtime ClassicUA when loaded. Lua simulation + actual WoW client acceptance required before any release. This is separate from Spoken audio-gated captions and opt-in preview.
- `GossipQuestTitles.lua` handles Quest labels. The separate `Spoken_Gossip_UA` addon handles NPC greetings and replies using NPC ID and exact native English hash. Each ZIP contains two Ukrainian addon folders. Shift shows original English. Missing text falls back to English.
- The legacy Gossip review CLI, ledgers, optional explicit Codex batch CLI and source-revision decisions are historical and independent of local selection and package creation. Retain their validation and privacy boundaries for archival access. Never present those records as eligible inputs to the simple Gossip workflow.
- Preserve same-origin, loopback, Host/Origin, CSRF, request content-type/size, pinned evidence and textContent-only display protections.
- The historical Places diagnostic remains unchanged and maintains its source-lock hashes. Release and distribution require separate authorization.

### Translation import statistics

- `adapters/import_statistics.py` and `tools/import_build_inventory.py` keep metadata-only counts of **recorded reviewer imports** vs **actual successfully built ZIP contents**. Those are NOT the same measurement. Never count discovered/pending candidates as imported.
- Attribute each actual ZIP text unit to a source and route: Quest moments counted by Quest ID/event, Gossip NPC/hash pairs, common fallback hashes and Gossip Quest titles separately; future modules must show zero until real code embeds them.
- SQLite schema v4 stores immutable build snapshots and unit/source records, never English/Ukrainian text bodies. Only save after successful ZIP write; no public publication; validate source evidence as before.
- Schema v5 adds metadata-only Gossip `text_sha256` fingerprints and `build_import_head` for the actual latest successful ZIP. Report known unique texts, NPC/hash occurrences, distinct NPC IDs, human English groups and common fallback units separately; legacy fingerprints remain explicitly unknown. Machine import is separate from human approval and from effective ZIP inclusion.
- GET `/api/import-stats` is localhost-only and returns metadata; the UI should refresh after successful review/import/selection actions without weakening existing CSRF, Host/Origin protections. Keep dynamic text rendered through `textContent`.
- Documentation: `docs/IMPORT_STATISTICS.md`. CLI: `uv run --locked python tools/translation_db.py imports`.

### Source conflict review UI

- The existing localhost UI adds a **Source Revision Review** section with authenticated GET `/api/source-reviews` and POST `/api/source-reviews/{decide,activate,clear}`. Keep Host/Origin, CSRF, strict JSON schema, request size and pinned source revalidation. UI displays dynamic strings through `textContent`, not `innerHTML`.
- Never auto-capture or auto-select a new provider in the browser. Imported source candidates and recommended provider order are strictly advisory, and must not bypass five human checks, Stage 3 Quest mapping or the private test-only scope.

### Source revision history & conflict policy

- `adapters/source_revision_store.py` and `tools/source_revision_review.py` add immutable provider+revision candidate snapshots and independent source review decisions. **Do not equate source import with approved content, proven Spoken identity, publication rights or active import.**
- External candidate files under ignored `build/` must be verified against the pinned Spoken original/context before accepting; reject attempted ClassicUA source impersonation and edited English proof fields. Source pin changes require explicit validated lock updates.
- Manual active selection requires ALL five human attestations and a separate explicit step. Provider priority is advisory, never replaces an existing selection. Retain old source revisions and history; reject same-revision content rewrites. Rejection/defer revokes activation but does not erase history.
- Quest full rebuild can render an independently Stage 3 mapped Quest override, checking current pinned context and conflicting human reviews before ZIP creation. No public release, unapproved TTS, provider auto-approval or audio changes.

### SQLite translation persistence

- Executable Quest/Gossip CLIs use a durable local SQLite file outside `build/` by default, configured through `SPOKEN_TRANSLATION_DB` or `XDG_DATA_HOME`. See `docs/SQLITE_TRANSLATION_STORE.md`.
- Keep the five existing strict ledger validators, provenance, version hashes and approvals intact; do not manufacture review decisions. Initial legacy JSON migration is **read-only** for the source files, transactional for SQLite, and fails closed on malformed/stale evidence. SQLite becomes authoritative once migrated. Never silently overwrite a database, export private bodies into Git, or delete prior review ledgers.
- The archival review tools may surface `translation_memory` hits as unapproved drafts. The new Gossip editor uses only its local choices and pinned candidates.
- Backup with `uv run --locked python tools/translation_db.py backup` and test concurrent-change detection and restoration. No new Python third-party database dependencies, Docker services, network servers, or changes to official Spoken/ClassicUA are needed.

### Mandatory uv Python workflow

- Use **uv** for all Python commands: `uv sync --locked`, followed by `uv run --locked python tools/…` / `uv run --locked python -m unittest discover -s tests -v`. Keep `.python-version` set to 3.12 and `uv.lock` committed in sync with `pyproject.toml`. Avoid `pip install` and bare `python3` in instructions or CI. The test suite currently has no third-party Python packages; `liblua5.4` is a system C library and remains a runner prerequisite.
- `VERSION` is the authoritative project version: if it changes, synchronize the PEP 621 `project.version` and regenerate `uv.lock` in that same reviewed change; do not allow version metadata to drift.

## Active product priorities
- Near-term Ukrainian content priority is **P0 Places lore**, **P1 Readables books/notes**, **P2 Bosses stories**, then **P3 Compendium UI chrome**, then **P4 Quests/Gossip**. Quest mapping and local reviewer UI are deferred, not deleted. See `docs/PLACES_SOURCE_AUDIT.md` for verified ClassicUA-name-only vs UA VoiceOver candidate-source constraints. Treat Compendium as a shared core UI, **not** an added fifth Community Pack.
- Runtime blockers are distinct: core UI labels follow actual `GetLocale()`; Places has no safe per-record English story fallback; Readables text-only records need safe no-audio handling and Compendium text selection; Bosses need an explicit story language resolver and content rights. Work only on supported/rights-cleared slices and report blockers truthfully.
- This feature order is **not** `config/translation_sources.json` provider order. Do not reorder providers or change the four agreed official modules to implement feature priority.

## Hard boundaries
- Do not modify upstream Spoken/ClassicUA checkouts or installed game AddOns unless specifically authorized.
- Do not call production APIs, spend TTS credits, publish packs/releases, or change the player to bypass language restrictions.
- ClassicUA maintainer granted project-specific permission for translation use, adaptation, AI TTS and distribution (see `docs/CLASSICUA_PERMISSION.md`). Follow the requested attribution and maintain provenance. Use invented text in committed fixtures; do not commit source snapshots, bulk translation corpora or audit dumps by default. Any change to that policy or content publication requires an explicit scoped task and independent third-party rights review.
- Keep `build/` and `dist/` ignored, and preserve Stage 1 diagnostic archive determinism.
- Stage 4C `adapters/reviewed_bridge.py` may bind *independently reviewed* Quest mapping decisions to exact audited effective ClassicUA fields, but **only as pending Ukrainian candidates**. It must refuse stale/missing source or target evidence and duplicate source-to-target binding; no real reviewed joins, content approvals or CLI integration exist yet.
- The opt-in `auto_approve_one_to_one` schema-v2 option applies to local, private content approval **only after** human-reviewed Stage 3 JoinProof, uniquely paired current canonical identity, a single provider candidate, reviewed rights and non-AI source. Auto decisions are distinguishable (`auto_approved_1to1`; no fabricated human text/grammar attestations), require independent revalidation on import, and may not override manual/changed source versions. Do not auto-approve ID mappings, commit translated bodies to Git, generate playable packs, or auto-publish. Default is disabled.
- Stage 4B.2 `tools/review_ui_server.py` binds to 127.0.0.1 only, uses audited pinned UA/EN fields, renders text safely and rejects CSRF/Host/origin violations. Explicit UI mapping approval must delegate a complete human-supplied independent two-reviewer JoinProof to the existing Stage 3 gate; never synthesize evidence or reviewer attestations. Separate content review requires explicit text/grammar/AI/rights attestations and exact version/context binding. Only ignored private `build/` storage may contain reviewed text/history; metadata-only reports and Git must not contain source bodies. Preserve Stage 4B schema-v2 decisions, Stage 3 proofs, atomic/conflict-safe translation ledger writes and separate explicit revalidated inert import. No runtime activation, CDNs or public serving. See `docs/TRANSLATION_APPROVALS.md`.
- Stage 4B workbench `tools/stage4b_workbench.py` may propose Quest ID/event **candidates**, but never auto-approves. Manual reject/defer decisions are pinned to source/target revisions and evidence digests (workbench schema v2), fail closed on changes, and are not canonical joins. Only an independently inspected, explicit `JoinProof` with separate evidence and mapping reviewers can enter the audited Stage 3 `review_file` schema. Identity approval never approves content/grammar/AI/rights/audio/runtime. The default/CI workbench must keep all real approval counts zero until humans independently supply proofs.
- Use canonical Spoken identities, never guessed mappings from translated names. Do not treat ClassicUA item IDs as Spoken page IDs or numeric Gossip hashes as Spoken moment IDs.
- The source policy now accepts schema v2 with `save_translations` booleans. Preserve schema-v1 optional `store_locally` controls and private `build/` approval ledger from Stage 4B.2; v1 has no opt-in to the future Git-backed curated store. The source resolver has no Git-backed translation writer. Do not silently commit ClassicUA text, raw imported copies, newer source revisions, auto-generated packs or translations from mocks. See `docs/TRANSLATION_STORAGE_POLICY.md` for future `translations/ukUA/` layout and update review gates.
- Honor the explicit order and membership of `config/translation_sources.json` (see `docs/TRANSLATION_SOURCE_CHAIN.md`), including English-only or no English. Empty `sources: []` or `{}` means actual WoW client `GetLocale()` with **no source calls**; never spoof it. Given an indexed canonical Spoken object list, process providers in sequential passes, passing only not-yet-translated objects to each next provider. Track provider and provisional status for each ID; report per-source found/remaining/total and differentiate candidates from **approved** translations. `another` is stub-only and `own_translator` mock-only; neither may silently approve mappings, text, rights, audio or publication. Never generate an override from an unresolved record.
- The translation provider pipeline (`adapters/translation_sources.py`) is an **offline prototype**, not connected to the Stage 3 report CLI or a production pack builder. Stage 4A can now read the **real pinned Spoken ID inventory and verified original English wording** through `tools/stage4_coverage.py`, but **does not bind any ClassicUA field without separately approved source→target mapping evidence**. Preserve its single-record/batch first-real-candidate semantics; require matching UTF-8 content fingerprint and provenance. Any candidate remains pending independent identity/content/rights review. Rejected candidates' retry with lower-priority sources is **future design**, not implemented behavior.
- An explicit `original_english` is an offline source selection, **not** proof of per-record English text fallback in a live Spoken module. In particular, Places has no per-record fallback in the pinned baseline. Empty provider policy means real client locale **for every canonical ID**, including Places/Bosses or any ID lacking a verified English original, and no provider calls, not English. Track `original_verified` independently and never construe locale selection as proof of localized text.
- Use exactly four upstream Spoken module targets: `Spoken_Quests` (**includes Gossip**), `Spoken_Places`, `Spoken_Readables` and `Spoken_Bosses`. Treat local Ukrainian addon identity separately from these upstream targets. Historic Zones/Books labels are superseded.
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
- `VERSION` is the single source of truth for the **project** version (currently `0.0.1`). Read it with `uv run --locked python tools/version.py show`; never add another hardcoded project-version constant.
- Project and addon versions are independent. In particular, the diagnostic addon's `.toc` version is `0.1.0`; do not synchronize it with `VERSION`, change its proven archive, or alter dependency versions in `sources.lock.json` as part of a project bump.
- Use the repository's strict numeric `MAJOR.MINOR.PATCH` policy: PATCH for fixes, MINOR for features; during 0.x, breaking changes may use MINOR but must be labeled **BREAKING** in the changelog. The first stable MAJOR requires explicit approval and `--approve-stable`; do not assume Stage 2B or Stage 3 completion implies a release.
- During ordinary development, describe notable changes under `CHANGELOG.md` > `[Unreleased]`. **Do not bump versions automatically for every commit, fix, feature or completed stage.** Bump only when the task expressly requests release/version preparation.
- For a requested bump, first inspect Git state, version and changelog. Use `uv run --locked python tools/version.py bump patch|minor|major --dry-run` to preview, then the supported bump command. The CLI updates **only** `VERSION`: prepare the matching new dated changelog section separately, preserve history, and run `uv run --locked python tools/version.py check`. A check failure between the bump and changelog edit is expected; do not bypass validation.
- CI validates version/changelog consistency. If verifying a project tag, use `uv run --locked python tools/version.py check --tag vX.Y.Z`. Never create, move, push tags, merge release PRs, publish GitHub Releases or publish Community Packs without explicit authorization and required content permissions.
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
   `uv run --locked python tools/version.py check`
   `uv run --locked python tools/build.py`
   `uv run --locked python -m unittest discover -s tests -v`
   Stage 1 tests require pinned Spoken and system Lua 5.4.
4. For optional real-source audits, run:
   `uv run --locked python tools/classicua_audit.py --source /absolute/path/to/clean-pinned-ClassicUA`
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
