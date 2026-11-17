# Translation source architecture — approved product policy

**Status:** configurable **offline prototype**, not a game addon, approved translation corpus, TTS system or release. Source selection and publication are independent of the unchanged Spoken Player. The pinned Spoken/ClassicUA source revisions and VERSION remain unchanged.

## Complete indexed list, then sequential provider passes

1. Read the **complete indexed set of Spoken objects**: verified canonical ID plus the original English text. Stage 3 must independently verify the source↔target identity; a translated title or numeric ClassicUA hash is **not** a canonical Spoken ID.
2. Read the ordered **allow-list** in [config/translation_sources.json](../config/translation_sources.json). Only listed sources run. Any subset/order is supported, including English first/only or a list without English.
3. Each source receives **only the remaining unresolved objects**. When it returns a real Ukrainian candidate, mark that object with its **source name**, SHA-256 and `candidate_pending_review` and remove it from subsequent lookup passes. A missing result leaves it available for the next source.
4. **Mocks do not translate.** `own_translator` currently returns an unpublishable placeholder and never marks a record translated or consumes it. `another` currently returns no results (stub); neither uses the network.
5. Explicit `original_english` handles all still-untranslated objects and stops searching; English is **not** a Ukrainian translation. If English is omitted, remaining objects remain unresolved **without overriding existing WoW/Spoken text**.
6. Review and publication are **separate gates**: canonical mapping, wording, grammar, AI, attribution/rights and runtime compatibility. All discovered Ukrainian candidates remain unapproved until independent review; **no real Stage 3 joins are approved yet**. No text/audio packs are generated.

The current adapter is [`adapters/translation_sources.py`](../adapters/translation_sources.py), using read-only already-audited ClassicUA effective fields provided by its caller. Single-record and batch resolution both stop at the first real candidate; a mock is skipped, and English fallback is selected only for records still unresolved when reached. Translation candidate field SHA-256 must match the actual in-memory UTF-8 text bytes. [Tests](../tests/test_translation_sources.py) use invented text. It does not download/modify upstream repositories or execute Lua.

### Configurable priority examples

Default:

```json
{"schema_version":1,"sources":["classicua","another","own_translator","original_english"]}
```

Own-first:

```json
{"schema_version":1,"sources":["own_translator","classicua","original_english"]}
```

English only:

```json
{"schema_version":1,"sources":["original_english"]}
```

**Empty `sources: []` or `{}`**: choose actual WoW **client language**, with no translation providers. The caller must supply the genuine client locale from `GetLocale()`; the offline Python process cannot read it itself. `deDE` therefore stays `deDE`, not English. This special mode differs from explicit `original_english`, which selects English regardless of client locale. A missing or whitespace-only config file is **invalid**, not empty configuration.

Changing the config requires rerunning the offline build/preparation workflow when that is implemented; this JSON file does **not** dynamically reconfigure the installed Spoken addon.

### Example coverage accounting

**Illustration only — not real translations or current source coverage.** Suppose 1,000 indexed Spoken objects:

| Source | New Ukrainian translation candidates | Still available for next source | Total |
| --- | ---: | ---: | ---: |
| ClassicUA | 650 | 350 | 1,000 |
| Another | 200 | 150 | 1,000 |
| Own Translator (future real implementation; currently only mock) | 100 | 50 | 1,000 |
| Original English | 0 Ukrainian (50 English originals) | 0 | 1,000 |
| **Final** | **950 candidates** | **50 English-only** | **1,000** |

Every object appears **once** in the final result; its metadata includes canonical Spoken ID, assigned source (if any), status and non-text SHA-256. The report separates `total`, `translation_candidates_pending_review`, `approved_translations`, `untranslated_no_source`, `original_english_fallback`, `client_language` and per-source counts including `remaining_for_next_source`. Mock output is excluded from translated counts. Until reviewed, the report's `approved_translations` is **0**, irrespective of candidate volume. Raw translated and original text never appear in the report.

### Local review persistence

The Quest Review UI uses a separate all-candidates discovery function over
independently reviewed Quest bindings. Unlike runtime/Stage 4A first-match
resolution, review discovery enumerates **all real providers** up to the
explicit English fallback boundary, so a pending higher-priority candidate
cannot hide an approved lower-priority one. Source priority still determines
which *eligible approved* translation is selected for inert import.
The optional schema-v1 `store_locally` map controls retention per enabled provider
(default true); for example `"store_locally":{"classicua":false}` permits only
in-memory review of that provider. Stub/mock behavior and Stage 4A reporting do
not change. Editing, equivalent-version approval reuse and deterministic inert
import live in a separate private approval ledger; unapproved candidates cannot
replace eligible approved content. See [approval architecture](TRANSLATION_APPROVALS.md)
for eligibility, complete schema, source-update limits and recovery.

### Independent real-world constraints

The approved four official module targets are `Spoken_Quests` (Quests + Gossip), `Spoken_Places` (Zones + Subzones), `Spoken_Readables` (Books / Notes), `Spoken_Bosses` (boss stories). Community Pack packaging and voice fallback are separate concerns. Official pinned Spoken has **no per-record Places English lore fallback**, and independent Ukrainian subtitles/Compendium or audio-free Readables remain blocked as documented in [Stage 2B](STAGE_2B_COMPATIBILITY.md). Never spoof `GetLocale()`, invent source-to-target joins, fake audio files, silently change the player or claim that offline provider coverage proves in-game translation.

Editable [draw.io architecture](diagrams/translation-pipeline.drawio) · [SVG diagram](diagrams/translation-pipeline.svg).
