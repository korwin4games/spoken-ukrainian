# Spoken Ukrainian 🇺🇦

**[English](README.md) | [Українська](README.uk.md)**

**Spoken Ukrainian** is a community project bringing Ukrainian text localization and, in the future, Ukrainian voice narration to [Spoken](https://github.com/rusty-key/spoken-wow) for **World of Warcraft Forever**. It is developed as an independent collection of Spoken Community Packs; the original Spoken Player remains a separate dependency.

> **Development status:** Ukrainian language registration and an original text-only **Places diagnostic pack** have been implemented and manually tested in Forever. The ClassicUA source adapter is implemented. Full Ukrainian quest, dialogue, book, location and boss-story packs **have not yet been released**.

## Local Spoken Ukrainian Quest test build

The build produces two independently installable AddOns: **Spoken Ukrainian** (`Spoken_Ukrainian`) and the Quest module **Spoken Ukrainian: Quests** (`Spoken_Quests_UA`). Official `Spoken` and `Spoken_Quests` are unchanged. **Every build MUST auto-import current ClassicUA 1:1 Quest translations**; bad/missing pinned checkouts, import errors, or no unambiguous Quest translations fail the build.

```sh
python3 tools/build_ukrainian.py --classicua ../ClassicUA --spoken ../spoken-wow
```

**ClassicUA AI translations:** optional `allow_ai_transations` (literal key spelling) defaults to `false`, but the checked-in `config/translation_sources.json` explicitly sets it to **`true`** for `classicua`. This permits **provisional local** imports only for candidates passing all strict 1:1/verified-original/source checks; it does not constitute human approval. Setting it back to `false` and rebuilding removes AI rows from the active test pack without deleting private local history. AI content absent from the Spoken narrated corpus cannot be imported.

Unzip the private `dist/Spoken_Ukrainian_Quest_Local_Test.zip` directly into `Interface/AddOns/`. In WoW use `/spokenuk preview on` to test an opt-in **separate** Quest translation frame. It is **not** Spoken's native captions: pinned Spoken 3.9.0 requires actual audio metadata to enqueue Quest subtitles, and this pack neither fakes audio nor patches upstream. Machine-matched text is conspicuously marked provisional; do not distribute this test build. [Exact game test steps and limitations](docs/QUEST_LOCAL_TEST_BUILD.md).

## Architecture and translation flow

Spoken Ukrainian prepares Ukrainian content **offline** for the **unmodified Spoken Player**. Discovering a translation does **not** approve its canonical Spoken identity, text quality, content rights or runtime compatibility.

### Current implementation priorities (November 2026)

**First:** (P0) **Places** lore; (P1) **Books and Notes** via `Spoken_Readables`; (P2) **Bosses** stories; (P3) **Azeroth's Compendium interface** (tabs, titles, controls, search, messages); (P4) **Quests/Gossip**. Existing Quest review tools remain available.

Compendium is the shared `Spoken` window, **not a separate fifth content pack**. Its UI labels can be translated **after** Places/Readables/Bosses content. ClassicUA provides Ukrainian **place names but not full zone stories**; [UA VoiceOver: Books & Lore](https://www.curseforge.com/wow/addons/ua-voiceover-books-lore) claims ~900 Ukrainian zone/subzone stories and 1000+ voiced book pages, now an **unverified candidate source** pending archive, rights and canonical-ID audit. Places has a text-only diagnostic; Readables/Bosses need supported language selection. See [prioritized roadmap](docs/PRODUCT_PRIORITIES_2026_11.md) and [Places source audit](docs/PLACES_SOURCE_AUDIT.md).

### Four approved modules

| Official module | Planned Ukrainian content |
| --- | --- |
| `Spoken_Quests` | Quests **and Gossip** (one module, not two) |
| `Spoken_Places` | Zone/subzone lore (formerly Spoken Zones) |
| `Spoken_Readables` | Books, letters, notes, plaques (formerly Spoken Books) |
| `Spoken_Bosses` | Dungeon and raid boss stories |

These are **official module targets**, not a player fork. Four independently installable Ukrainian content packs are planned. ClassicUA does **not** supply authored Places/Bosses stories. See the [approved product and fallback policy](docs/APPROVED_MODULES_AND_FALLBACK.md).

### Translation sources and priorities

The default offline provider order is configured in [`config/translation_sources.json`](config/translation_sources.json):

```json
{
  "schema_version": 2,
  "sources": [
    {"name": "classicua", "save_translations": true, "auto_approve_one_to_one": true, "allow_ai_transations": true},
    {"name": "another", "save_translations": false},
    {"name": "own_translator", "save_translations": true},
    {"name": "original_english", "save_translations": false}
  ]
}
```

| Source | Current state | Role |
| --- | --- | --- |
| `classicua` | Implemented adapter | Read audited effective ClassicUA translation fields; mappings still need review |
| `another` | Offline stub | Future independently licensed source; currently finds nothing |
| `own_translator` | Non-publishable mock | Does **not** count as a translation or consume a record |
| `original_english` | Explicit fallback | Select original English for still-unresolved records; never count as Ukrainian |

You can **reorder or remove** source objects. For example, putting `own_translator` before `classicua` changes priority (the translator is still a mock); leaving only `original_english` selects English only. **`{"schema_version":2,"sources":[]}` or `{}` means the genuine WoW client language**, with no provider calls; an actual `deDE` client is not forced to English. The offline caller must supply the client locale. Older schema v1 name arrays remain supported, with all save flags disabled. Omitting `original_english` does not silently reinsert it. A missing or invalid config file is an error.

**Naming and in-game validation:** PR #17 provides **Quest Translation Import · Spoken_Quests (offline)**, **not** an installable AddOn. The official `Spoken_Quests` module is unchanged; PR #18 now creates a **local-only test** Quest pack `Spoken_Quests_UA` alongside the new `Spoken_Ukrainian` base addon. The existing `SpokenCommunity_ukrainian-diagnostic` is for **Places** and remains unchanged. The imported texts appear only in an opt-in independent quest preview, **not native Spoken captions**: [game test plan](docs/QUEST_LOCAL_TEST_BUILD.md).

**Bulk ClassicUA 1:1 import:** the local Review UI has an **Auto-import 1:1 · ClassicUA** button. It refreshes current candidates, applies only eligible one-to-one machine content approvals, and imports current eligible versions to an **inert private local snapshot**. A source breakdown table shows total canonical Spoken identities (all modules), unreviewed 1:1 candidate pairs, independently approved mappings, actual imported translations per provider, untranslated records and coverage percentage. The same table is printed by:

```sh
python3 tools/review_ui_server.py --classicua /path/to/ClassicUA --spoken /path/to/spoken-wow --auto-import-one-to-one
```

Strictly unique Quest ID/event pairs with a single verified Spoken identity context and original-English fingerprint may also be saved to a separate **provisional machine-import store** (`build/machine-one-to-one.json`) without a fabricated Stage 3 JoinProof. They are clearly labeled and counted separately from human-reviewed imports, cannot be treated as publication-ready, and never overwrite reviewed/manual text. Ambiguous source/target, missing originals, AI markers, or changed upstream text remain blocked/pending. The default config enables this mode for ClassicUA, but no real approved joins currently exist, so genuine coverage can remain zero. Content is stored in ignored `build/translation-reviews.json`, not Git or the live WoW AddOn. [Workflow and safeguards](docs/TRANSLATION_APPROVALS.md).

**Optional `auto_approve_one_to_one: true`** (ClassicUA only initially, defaults to `false` when omitted; enabled for ClassicUA in the project's current config) allows an independently verified one-to-one source→Spoken mapping and unique rights-cleared candidate to be marked `auto_approved_1to1` by the local Review UI's explicit Refresh operation. This saves text/decision only in the private ignored `build/translation-reviews.json`, with **no invented human grammar/text checks**. Changed upstream versions, competing candidates and manually edited content remain review-required. Explicit inert import, eventual Git-backed export, runtime activation and release are separate gates. [Approval policy](docs/TRANSLATION_APPROVALS.md).

**The `save_translations` flag is per provider** and opts verified translations into a future Git-backed storage workflow (`translations/ukUA/`). It does not save anything during source discovery: canonical ID, rights and content checks remain mandatory. External imports will live under `imported/<source>/`, separate from manually curated translations, and later source changes will be proposed for review rather than overwriting our edits. `own_translator` is still a mock; its flag currently saves nothing. [Storage/update policy](docs/TRANSLATION_STORAGE_POLICY.md).

### Sequential processing and coverage

1. Start from a list of **verified canonical Spoken IDs** and original English text/identity evidence. The caller currently supplies this list.
2. Each configured source receives **only records still without a real Ukrainian candidate** from earlier sources. Record source, canonical ID, field SHA-256 and `candidate_pending_review` for discoveries.
3. Mocks do not resolve records. Explicit English and empty-config client language are separate statuses, **not Ukrainian translations**.
4. Produce a **metadata-only report** with per-source new candidates, remaining records, and the total. Never export translation bodies.
5. Independently review matching evidence, text/grammar/AI, attribution/rights and runtime behavior **before any pack**.

**Synthetic example, not actual translation coverage:**

| Source | New Ukrainian candidates | Remaining for next source |
| --- | ---: | ---: |
| ClassicUA | 2 | 2 |
| Another (stub) | 0 | 2 |
| Own Translator (mock) | 0 | 2 |
| Original English | 0 (2 English originals) | 0 |
| **Total: 4 records** | **2 pending review** | **2 English-only** |

The report distinguishes candidate counts from `approved_translations` (**currently zero**), English/client selection and unresolved records. This is an **offline prototype**, not yet integrated with `tools/stage3_report.py` or the final Community Pack builder. **No real source↔Spoken joins are approved.**

![Source-resolution architecture](docs/diagrams/translation-pipeline.svg)

[Editable draw.io diagram](docs/diagrams/translation-pipeline.drawio) · [Source chain and accounting specification](docs/TRANSLATION_SOURCE_CHAIN.md) · [Stage 3 identity mapping evidence](docs/STAGE_3_IMPLEMENTATION.md)

### Compatibility and source updates

`ukUA` is a Spoken **content language**, not a Blizzard client locale. Text-only Ukrainian Places diagnostic lore works, but current pinned Spoken has unresolved Quests/Gossip captions, Readables and Bosses display/audio restrictions. **Configurable offline sources do not implement in-game fallback** or fix these limitations. See [Stage 2B](docs/STAGE_2B_COMPATIBILITY.md).

Completed Ukrainian packs should eventually work without requiring the ClassicUA addon at runtime. ClassicUA will remain a **pinned input**, re-audited on approved updates; effective text changes can trigger content/audio review without automatically changing canonical IDs. Pack generation, TTS and publication remain later separately authorized stages.

## ClassicUA and attribution

The project uses **[ClassicUA](https://github.com/greenya/ClassicUA)** as the intended main source of Ukrainian game-text translations and Warcraft terminology. Thank you to its maintainers and contributors for their work.

Maintainer **greenya** granted permission in [ClassicUA issue #100](https://github.com/greenya/ClassicUA/issues/100#issuecomment-6917008199) to use and adapt ClassicUA translations for Spoken Ukrainian and to create and distribute AI TTS narration based on them. The response confirms coverage of the repository's translations, states no additional publication restrictions and requests a project link plus acknowledgement that the translations were adapted.

> **За основу взято адаптовані переклади [ClassicUA](https://github.com/greenya/ClassicUA).**

This attribution applies to **future ClassicUA-derived content**. The existing diagnostic paragraph is original and contains no imported ClassicUA translations. The permission does not automatically cover unrelated artwork, fonts or independently sourced lore, or waive the terms of an eventual TTS provider. See [permission record](docs/CLASSICUA_PERMISSION.md) and [third-party content notes](THIRD_PARTY.md).

## Current status

| Component | Status |
| --- | --- |
| Stage 0 — architecture and source/compatibility review | Complete |
| Stage 1 — `ukUA` registration and original text-only Places diagnostic | Implemented; manually tested in Forever |
| Stage 2A — restricted ClassicUA Lua parser, override resolver and metadata-only audit | Implemented |
| Stage 2B — runtime compatibility of independent Ukrainian text | Offline characterization implemented; [results](docs/STAGE_2B_COMPATIBILITY.md), [manual Forever acceptance pending](docs/STAGE_2B_TESTING.md) |
| Stage 3 — canonical ClassicUA → Spoken ID mapping and update-ready comparison | Offline inventory, review schema and local effective comparison implemented; **0 approved real joins, independent review pending** ([coverage](docs/STAGE_3_IMPLEMENTATION.md)) |
| Configurable source priority and sequential coverage (PR #8) | Offline resolver, policy and candidate metadata reporting implemented; **no approved real content** |
| Stage 4A — real pinned Spoken inventory → source coverage dry-run | Implemented read-only public English text index and offline coverage CLI for verified originals; **0 real source joins, no Ukrainian packs** ([details](docs/STAGE_4A_INVENTORY_COVERAGE.md)) |
| Stage 4B — Quest mapping review workbench | Pinned source/target evidence queue, reject/defer, explicit Stage 3 two-reviewer approval gate; **0 real reviewed joins** ([procedure](docs/STAGE_4B_REVIEW_WORKBENCH.md)) |
| Stage 4C — reviewed Quest candidate binding foundation | Synthetic-only audited effective ClassicUA field verification; **0 real identity joins or approved texts**, no CLI integration ([contract](docs/STAGE_4C_REVIEWED_QUEST_BRIDGE.md)) |
| Stage 4B.2 — local Quest Review UI | Loopback-only Mapping/Translation Review, independent proofs, persistent local versions/content decisions and explicit inert import; **no real approvals or activation** ([guide](docs/STAGE_4B_LOCAL_REVIEW_UI.md)) |
| **Current priority** | **Places → Readables (Books/Notes) → Bosses → Compendium UI → Quests/Gossip** ([roadmap](docs/PRODUCT_PRIORITIES_2026_11.md)) |
| Ukrainian text/audio packs, updater and public releases | Not released |

## Build and test

The current downloadable **local build output is only a diagnostic pack**, not a complete Ukrainian localization.

```sh
python3 tools/version.py check
python3 tools/build.py
python3 -m unittest discover -s tests -v
```

Building requires Python 3. The tests additionally use Git, the system Lua 5.4 shared library and the pinned Spoken source checkout (normally in sibling `../spoken-wow`). Set `SPOKEN_SOURCE=/absolute/path/to/spoken-wow` if yours is elsewhere. These commands do not fetch source code, install packages or access production systems.

The build writes `dist/SpokenCommunity_ukrainian-diagnostic.zip` plus its SHA-256 sidecar. It contains only the addon TOC and `Lore.lua`, with original language/font test text for Elwynn Forest (map 1429). **Do not install the entire repository into AddOns.** See the [Stage 1 installation and testing guide](docs/STAGE_1_TESTING.md) for manual installation.

### Validate offline identities (Stage 3)

```sh
python3 tools/stage3_report.py --classicua /absolute/path/to/clean-pinned-ClassicUA --spoken /absolute/path/to/spoken-wow
```

Writes deterministic metadata only to ignored `build/stage3-report.json`. Optional
`--reviews` validates reviewed attestations. `--candidate` with
`--candidate-manifest` compares a separately reviewed local revision without
changing the active lock. See the [review procedure](docs/STAGE_3_IMPLEMENTATION.md).

### Dry-run source coverage against real Spoken IDs (Stage 4A)

```sh
python3 tools/stage4_coverage.py --spoken /absolute/path/to/clean-pinned-spoken-wow
```

Reads the **real pinned canonical Spoken inventory** and checks original wording for Quests/Gossip/Readables without exporting text; reports a per-source lookup pass, missing-original targets and total counts in ignored `build/stage4-source-coverage.json`. Source identity is deliberately **unbound** until independently approved Stage 3 joins exist, so **no real ClassicUA translation is assigned**; `another` remains a stub and `own_translator` a mock. Empty policy requires an explicit `--client-locale` from the caller. See [Stage 4A scope and limitations](docs/STAGE_4A_INVENTORY_COVERAGE.md).

### Inspect Quest mapping candidates (Stage 4B)

The review workbench audits **both pinned repositories**, produces a metadata-only shortlist of actual Quest ID/event candidates and requires independent speaker/voice/faction/wording evidence before accepting a canonical join:

```sh
python3 tools/stage4b_workbench.py \
  --classicua /absolute/path/to/clean-pinned-ClassicUA \
  --spoken /absolute/path/to/clean-pinned-spoken-wow \
  --faction horde --limit 40
```

Outputs: ignored `build/stage4b-review-queue.json` and a **filterable, spreadsheet-safe** `build/stage4b-review-worksheet.csv` (one row per target/voice variant). The pinned CI attaches both as a short-lived metadata-only artifact. A reviewer can explicitly **reject or defer** individual source/target pairs. **Approval** requires a separate human-supplied Stage 3 `JoinProof` and two distinct reviewers, validated by the existing mapping gate; it never approves Ukrainian wording automatically. No real approvals are committed. See the [Stage 4B guide](docs/STAGE_4B_REVIEW_WORKBENCH.md).

### Reviewed Quest candidate bridge (Stage 4C foundation)

`adapters/reviewed_bridge.py` adds **synthetic-tested**, offline binding of independently approved Stage 3 Quest identity mappings to exact audited ClassicUA effective fields. It rechecks the stored evidence, original/source fingerprints and configured source priority; a found Ukrainian field is still **pending content review**, not an approved translation. The normal Stage 4A command **does not activate this bridge**, and **no real human-approved joins exist yet**. See [Stage 4C contract](docs/STAGE_4C_REVIEWED_QUEST_BRIDGE.md).

### Local Quest review UI (Stage 4B.2)

The **local browser UI** separates Mapping Review from Translation Review. Compare audited UA/EN and speaker/voice/faction variants; reject/defer mappings or submit a complete human-supplied Stage 3 `JoinProof` with **two independent reviewers**. Revalidated joins can supply pending translations. Edit into new versions, inspect provenance/history, and explicitly approve text/grammar/AI/rights. **Approval and import are separate actions**; import creates only an inert local snapshot, with no WoW activation. No real approvals are supplied by this PR.

```sh
python3 tools/review_ui_server.py \
  --classicua /absolute/path/to/clean-pinned-ClassicUA \
  --spoken /absolute/path/to/clean-pinned-spoken-wow
```

Open **http://127.0.0.1:8765/** on the same machine. The server binds only to loopback, makes no internet calls, and keeps private review data in ignored `build/`: metadata in `stage4b-decisions.json` and `stage3-ui-reviews.json`, reviewed text/history/import references in `translation-reviews.json`. Optional provider `store_locally` controls retention. Unchanged bytes/context may reuse approval after audited source updates; changed originals/text/context become stale, and edits are preserved. Existing schema-v2 decisions load unchanged; corrupt/older files require recovery and explicit re-review. See the [UI procedure and recovery guide](docs/STAGE_4B_LOCAL_REVIEW_UI.md) and [approval architecture](docs/TRANSLATION_APPROVALS.md).

Explicit import (same optional paths/policy as your UI session):

```sh
python3 tools/review_ui_server.py \
  --classicua /absolute/path/to/clean-pinned-ClassicUA \
  --spoken /absolute/path/to/clean-pinned-spoken-wow \
  --import-approved
```

Verification: `python3 tools/version.py check`, `python3 tools/build.py`, and `python3 -m unittest discover -s tests -v` (including local HTTP sockets).

### Audit a pinned ClassicUA checkout (Stage 2A)

```sh
python3 tools/classicua_audit.py --source /absolute/path/to/clean-pinned-ClassicUA
```

The adapter reads a **separate, clean** ClassicUA checkout at the revision in [sources.lock.json](sources.lock.json), validates source hashes and resolves the real `classic → sod → forever` load/override behavior. Its metadata-only report is stored in ignored `build/classicua-audit.json`. It does not execute ClassicUA source Lua, export translations into packs or match Spoken canonical IDs. See the [implementation](docs/STAGE_2A_IMPLEMENTATION.md) and [test report](docs/STAGE_2A_TESTING.md).

## Project versions

The root [VERSION](VERSION) is the **project** version (initial baseline `0.0.1`), separate from independently versioned community addons (the diagnostic addon is `0.1.0`). Use `python3 tools/version.py show` and `python3 tools/version.py check`; changes are documented in [CHANGELOG.md](CHANGELOG.md). Tags and GitHub Releases are explicit, reviewed operations; they are not automatically created by version bumps. See [VERSIONING.md](docs/VERSIONING.md).

## Documentation

- [Implementation roadmap](docs/IMPLEMENTATION_PLAN.md) · [Source integration](docs/SOURCE_INTEGRATION.md) · [Compatibility matrix](docs/COMPATIBILITY_MATRIX.md)
- [Stage 3 mapping/update specification](docs/STAGE_3_SPECIFICATION.md) · [Permission record](docs/CLASSICUA_PERMISSION.md) · [Attribution](THIRD_PARTY.md)
- [Stage 4A pinned inventory/coverage CLI](docs/STAGE_4A_INVENTORY_COVERAGE.md) · [Translation source architecture](docs/TRANSLATION_SOURCE_CHAIN.md) · [Editable diagram](docs/diagrams/translation-pipeline.drawio) · [Approved four-module policy](docs/APPROVED_MODULES_AND_FALLBACK.md)
- [Spoken Community Packs guide](https://github.com/rusty-key/spoken-wow/blob/master/community/README.md)

Stage 0 documents preserve the **historical state at the time they were written**, including an earlier unresolved-permission note. The subsequent permission is documented separately rather than rewriting their pinned historical contents.
