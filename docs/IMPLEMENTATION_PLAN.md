# Spoken Ukrainian implementation plan

Stage 0, 2026-11-16. Planning only. Build the complete Ukrainian equivalent of Spoken French for WoW Forever through native Community Packs. Keep Spoken Player external. `ukUA` is content metadata, not a new client locale. The earlier 15-page translation MVP imposes no requirements.

Baseline: Spoken `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`; ClassicUA `1770d208ad853d23d61105cf510d53804770d916` (7.1.1). See [source contracts](SOURCE_INTEGRATION.md), [module compatibility](COMPATIBILITY_MATRIX.md), and [permissions](LEGAL_AND_ATTRIBUTION.md).

## ADR-001: independent Community Packs repository

Status: selected for the proposed implementation.

Spoken discovers community languages through metadata and exposes native pack formats. A collaborator directed the Ukrainian proposal to the [Community Packs guide](https://github.com/rusty-key/spoken-wow/issues/1123#issuecomment-6906425492). Use an independent `spoken-ukrainian` repository containing adapters, deterministic mapping, provenance, validation and packaging. Install the player and its modules separately.

A player fork would duplicate queue, UI, settings and client compatibility maintenance without resolving source identity, grammar or permission questions. Community Packs supply the intended extension boundary. However, the inspected player has limitations for Ukrainian Quest/Gossip captions, audio-free Readables and non-client Bosses story selection. Reproduce those limitations and seek general upstream extensions before considering player modifications. Do not monkey-patch player internals from a pack.

This decision separates three outcomes: offline translation preparation, runtime Ukrainian text display, and actual audio playback. Registration proves only the first integration boundary. Text-only Places lore is the first supported display test; it does not establish full Ukrainian support across modules.

## Proposed repository and data flow

```text
spoken-ukrainian/
  README.md
  LICENSE                         original tooling only
  THIRD_PARTY.md                   content grants and notices
  sources.lock.json               commits, file hashes and contract/client versions
  adapters/classicua/             ordered parsing, overrides, grammar inventory
  adapters/spoken/                pinned public identity/reference readers
  mapping/                       small reviewed crosswalk decisions
  validation/                    identity, grammar, coverage and rights checks
  packaging/                     Lua/TOC serializers and deterministic ZIP tools
  packs/                         metadata and original diagnostic inputs
  tests/fixtures/                synthetic data and strict client API fixtures
  docs/                          operations, permissions and game test records
  build/                         ignored derived records, reports and staged addons
  dist/                          ignored local archives and manifests
```

Prefer a small Node toolchain for orchestration and packaging, reusing appropriate pure upstream quoting/naming helpers with notices and parity tests. Use a real Lua-aware parser or a reviewed restricted interpreter for source adapters. Stage 0's regex inventory is not a production parser. Do not execute arbitrary upstream Lua with host filesystem or network access. Preserve long strings, sparse positional slots, comments and nested keys.

Read permitted pinned source snapshots; resolve actual TOC/XML order and merge semantics; derive ephemeral normalized records; join to canonical Spoken identities; validate; then emit native pack files and sidecar reports. After input acquisition the build must operate offline, without production credentials, private APIs, Postgres or a droplet. Official sync/export/release wrappers are outside this design.

Translation edits remain upstream or with the separately identified lore author. Immutable snapshots and ignored derived output are build inputs, not another editable translation database. Hand-kept manifests store only crosswalk decisions, exclusions and review attestations tied to source hashes. Changed source hashes invalidate review. Do not modify upstream generated Lua or obtain a replacement corpus from production APIs.

## Current execution priority update (2026-11-16)

The original table below remains the **dependency/gate architecture**, not a fixed implementation queue. The user changed the **near-term feature order** to **(1) Compendium UI, (2) Places lore, (3) Readables Books and Notes, (4) Bosses stories**. Quests and Gossip review tools and already completed groundwork remain available, but cease to be the first-wave bottleneck. See [active prioritized roadmap](PRODUCT_PRIORITIES_2026_11.md) for distinct supported surfaces, English-original indexing, story rights and upstream selection blockers. Compendium is the core shared window, **not a fifth content module**. Keep the Player unchanged and preserve all compatibility/permission gates. This priority update does not change the configured translation provider order.

## Dependency-aware roadmap

| Stage | Dependencies | Deliverables and acceptance criteria |
| --- | --- | --- |
| 0: architecture | None | Four planning documents with pinned revisions, real source semantics, runtime limitations and rights gates. No implementation or translation import. |
| 1: registration and diagnostic lore | Stage 0 | One local Places Community Pack registers `ukUA` and displays original diagnostic prose in Forever with unmodified Spoken and no audio. Detailed task specification below. |
| 2A: source adapters | Stage 1 conventions; import permission boundary settled | Parser, layer resolver, separate faction views, template/AI inventory and provenance reports. Synthetic tests require no ClassicUA text. Actual-source analysis stays outside tracked content. |
| 2B: rights and display contracts | Parallel with 2A | Resolve ClassicUA permission and contributor authority. Reproduce module display gates in strict tests and Forever; determine whether upstream extensions exist. No fork by default. |
| 3: identity mapping | 2A and permitted reference inputs | Deterministic quest/Gossip/page/map/encounter crosswalks; every accepted mapping has evidence; ambiguous records are rejected and counted. |
| 4: reviewed text integration | 3, applicable text rights, supported display contract per module | Native text artifacts, reviewed terminology/grammar and documented game results. Places may proceed independently using original or cleared lore. Other display surfaces wait for demonstrated support. |
| 5: audio feasibility decision | Reviewed text integration and TTS permissions | Evaluate existing Spoken generation, contribution, archive and take-delivery capabilities; record access, provider quality/cost and ownership constraints before choosing infrastructure. No generation authorized by this plan. |
| 6: real audio and complete packs | Stage 5 decision and explicit later authorization | Cleared Ukrainian recordings with stable identities, real files/durations, accurate captions/timings and deterministic packs. Verify each module and faction split. |
| 7: publication and maintenance | Rights, content and game-test gates; explicit release task | Release assets and approved Community Pack listings for supported sections. Optional umbrella installer after real packs exist. Bosses listing needs upstream support or an agreed separate route. |

If a display contract remains unavailable, mark that module blocked while supported modules and offline mapping continue. Do not compensate with fake audio entries, silent files, arbitrary IDs or copied player code.

## Stage 2 acceptance and tests

Report raw declarations, unique effective keys, overwritten predecessors, AI flags, missing fields, grammar classes and source locations. Distinguish source, mapped, reviewed, display-capable and voiced coverage.

Tests must cover whole-row replacement by a sparse later quest; empty Forever tables preserving Classic readables; inherited SoD entries; Gossip per-hash merge and whole `!code` replacement; object namesakes; faction-before-shared precedence; AI-disabled behavior; case/capitalization templates; numeric captures; malformed constructs and Lua long strings. Unknown constructs fail with a useful source location. Never infer sparse quest slots using Lua array length.

Default publication policy should exclude unreviewed AI-marked content. Preserve the flag even for excluded rows. Do not silently substitute an older human row where ClassicUA replaces it with a Forever AI row, because that changes effective source behavior.

## Stage 3 acceptance and tests

Quests preserve ID/event and validate eligibility, speaker and alternate wording. Gossip proves NPC/page identity against canonical Spoken moments; ClassicUA hashes never become Spoken stems. Readables resolve owner IDs and real page chains. Places retain English canonical keys. Bosses resolve encounter/creature evidence rather than translated names.

Fixtures include duplicate readable titles, namesakes with different `h1`, unknown owners, shared pages, missing middle pages, unmatched Gossip options, several greetings for one NPC, multiple voices for one line, faction/shared collisions and subzone slug collisions. Golden vectors compare naming and UTF-8 checksums with pinned upstream implementations. Do not remint canonical IDs to resolve ambiguous joins.

Coverage reports state their denominator: effective source units, target units and mapped intersections differ. Raw row counts cannot be added into a Forever completion percentage. Unavailable page-chain or speaker evidence leaves a rejected mapping rather than introducing a private production dependency.

## Stage 4 runtime and content validation

For every claimed module, demonstrate Ukrainian on an actual supported Forever client, initially `enUS`. A harness with `GetLocale()` forced to `ukUA` or `frFR` does not prove this. Test ClassicUA enabled and disabled because its hooks change displayed text. Record the exact surface translated: game frame, narrator caption, Compendium page or Places lore window.

Test male/female characters, class/race/name templates, Ukrainian glyphs, punctuation and Unicode apostrophes. Exercise absent/disabled packs, unsupported formats, missing translations/audio, English fallback and Stay Silent. Separate matching keys from labels. Places/Bosses stories require distinct authorship or translation work; a name dictionary is not story coverage. No readable page quota is imposed.

If an upstream extension is needed, specify a general capability: separate text from audio availability, independent content-language selection, and explicit fallback. Add a failing test against the unmodified baseline and reproduce in game before proposing an upstream fix. Keep the independent project a consumer of the eventual contract.

## Audio and release decisions

Determine whether maintainers provide an authorized route through existing Spoken text/take infrastructure. Public pack installation does not imply generation or private archive access. If access is unavailable, compare authorized alternatives before choosing architecture. Do not add a generation CLI, call a provider or run a sync as part of the feasibility evaluation.

Later audio acceptance requires reviewed Ukrainian pronunciation, recording text separated from player-dependent display templates, voice identity, file presence, correct duration/timings, exact paths, stale-take detection and rights records. Keep audio outside git under the eventual approved storage design.

Packaging checks reject missing permissions/notices, fake audio, invalid folders, traversal, duplicate archive paths and unpinned inputs. Eventually use separate faction quest packs and Gossip under section `quests`, plus Readables and Places. Pack IDs/language/section become immutable after registration. The diagnostic ID should not accidentally become the full product's identity. A French-style meta installer is later distribution convenience, not the implementation.

## Risks and unresolved decisions

| Question | Decision or evidence still needed |
| --- | --- |
| ClassicUA redistribution and TTS rights | Issue 100 had no reply. Obtain a scoped grant and authority; block affected publication. |
| Independent Ukrainian text display | Places supported. Reproduce Quests/Gossip, Readables and Bosses restrictions and coordinate upstream extensions. |
| ClassicUA coexistence | Test hook order and actual strings delivered to Spoken for quest, gossip and readable events. |
| Forever version | Source TOCs specify Interface 16001. Record actual game build, client locale and installable Spoken release. TOC compatibility alone is insufficient. |
| Ukrainian fonts | Verify `і ї є ґ І Ї Є Ґ` in menus and lore. If needed, select a separately licensed font. Do not copy ClassicUA assets. |
| Complete Places/Bosses prose | Plan separately cleared translation/authorship with per-story provenance. ClassicUA provides terminology candidates. |
| Grammar rendering and recording | Inventory first; convert only proven equivalents. Never strip unresolved templates or bake in tester identities. |
| Minimum player release | Establish an installable release implementing the inspected contract before claiming support. |
| Bosses distribution | Manager lacks a Bosses section. Do not mislabel it as Places without upstream agreement. |

## Stage 0 verification

Inspected repository guides, Community Packs, player language/API code, all requested module source paths, naming helpers and relevant packaging/store boundaries; ClassicUA TOC/XMLs, entries and runtime resolver; licenses, French product page and both issue discussions. Source inventory is structural, not a completed crosswalk or game-tested coverage result.

Only the four requested documents are added. No translations, addon changes, generated data edits, production writes, database changes, paid calls or packages are part of this stage. Code suites and in-game tests were not run for this documentation-only change. Verify whitespace and local documentation links.

## Stage 1 implementation specification for the next Codex task

Create the independent `spoken-ukrainian` workspace/repository when authorized by the next task. Implement a single local diagnostic Places Community Pack, leaving the external Spoken installation unmodified.

1. Use local test ID `ukrainian-diagnostic`, folder/TOC `SpokenCommunity_ukrainian-diagnostic`. Do not publish or reserve the ID.
2. TOC declares Interface `16001`, dependencies `Spoken, Spoken_Places`, `X-SpokenPlaces-Language: ukUA`, `X-SpokenPlaces-Lore: 1`, names Ukrainian/Українська, diagnostic title and local project version. No Quests data-module keys or audio registry.
3. Register one combined zones table and an empty subzones table through `SpokenPlaces:RegisterLoreData`. Use existing map ID `1429` for Elwynn, verifying that the installed Forever map API recognizes it. Write original short Ukrainian diagnostic prose explicitly identified as a language/font test rather than game lore. Copy no ClassicUA wording, Spoken story, art or font.
4. Package a deterministic local ZIP containing exactly that folder. Emit its SHA-256 and byte size locally. No GitHub/site calls, database access, audio files, `Sounds.lua`, TTS or release submission.
5. Test folder/TOC consistency, dependency/load order, `ukUA` as a non-client language, disabled-pack behavior, combined lore registration, selection/reload and archive path safety. Check no audio registry or sound playback is requested by the diagnostic pack. Use actual pinned unmodified language/module code where feasible; stubs must not invent a Ukrainian client locale.
6. Manually install with an unmodified released Spoken build in Forever on `enUS`. Record build/release/locale. Confirm Ukrainian appears in Voice Language and Places Text Language. Explicitly select Places Ukrainian and reload; unlock unfound Places if needed, open the Elwynn diagnostic lore page in Azeroth's Compendium, and verify text and glyphs. Expect no narration from this pack. Switch back to English and reload; disable/remove the pack and verify ordinary behavior.
7. Test once with ClassicUA disabled, then enabled if available. Record Lua errors, missing glyphs and fallback behavior. Report font failures and evaluate a licensed font instead of bypassing rendering guards.

Deliver source, reproducible local build command, local artifact, tests with actual results, and a manual test record/screenshots where available. If no game client is accessible, state that in-game acceptance remains pending. Registration alone does not prove other modules' translation support.

Excluded: ClassicUA import, full translation corpus, readable quota, upstream edits, monkey patches, fake/silent audio, generation pipeline, paid requests, production services, database changes and publication. Do not implement this milestone during Stage 0.
