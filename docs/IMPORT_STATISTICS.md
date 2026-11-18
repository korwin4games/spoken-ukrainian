# Translation Import Statistics · SQLite

Spoken Ukrainian reports two distinct things. The **review import ledger**
counts translations whose versions were explicitly imported (or machine 1:1
provisionally imported) into SQLite; the **effective ZIP inventory** counts
the texts actually serialized into the latest successful local-test ZIP.
These totals **are not interchangeable**.

## Where to see the tables

Start the regular UI with pinned clean local checkouts:

```bash
uv run --locked python tools/review_ui_server.py \
  --classicua ../ClassicUA --spoken ../spoken-wow
```

Open `http://127.0.0.1:8765/` → **Translation Import Statistics · SQLite**.

The section refreshes after successful Quest/Gossip Review POST actions and
Source Review selection changes. It also has a manual refresh button.
Before the first build, the ZIP panel explicitly says no inventory exists.

The same metadata-only report is available from the CLI:

```bash
uv run --locked python tools/translation_db.py imports
# Custom database: --db /absolute/path/to/translations.sqlite3
```

## Categories and units

| Category | Record counted | Unique entities |
|---|---|---|
| Quests | One accepted `quest ID + event` (accept/progress/complete), not every NPC wording | Distinct quest IDs |
| Gossip | One NPC ID + exact English-text hash | Distinct NPC IDs |
| Gossip (common) | One global/common exact-English hash | Common fallback group (not an NPC) |
| Gossip Quest Titles | One faction + quest ID title | Distinct quest IDs |
| Places | Embedded text entries when implemented | Distinct places |
| Readables (Books & Notes) | Embedded text entries when implemented | Distinct books/notes |
| Bosses | Embedded text entries when implemented | Distinct bosses |
| Compendium UI | Embedded UI strings when implemented | Distinct UI keys |

Future categories show **zero**, not inferred imported text. Common Gossip
fallbacks are separate from NPC-scoped lines to avoid inventing NPC counts.

Each table groups by **category × source × route**. Source is `classicua`,
`another`, `own_translator`, `manual`, or (for identical approved text
supported by more than one real source) a joined provenance string.
Routes distinguish `machine_1to1` (not human reviewed), `reviewed`,
`source_selected` and `pinned_source`.

## Immediately after Import

`recorded_imports` is recomputed from the strict, existing SQLite Quest and
Gossip review ledgers; it does not need another full ZIP build. Candidate
discovery, proposed text, pending approval and rejected versions count as
**zero imports**. Selecting a source variant is displayed in a separate
`selected_not_necessarily_built` section: a selected version is not
misrepresented as already embedded in an addon.

For Quests, the recorded count is **canonical event target references**.
For Gossip, the recorded count is **imported unique English groups**, not
NPC/hash occurrences, because the group can affect multiple NPCs. The
later ZIP inventory expands the real NPC/hash placements separately.

The original validated JSON ledger data remain authoritative (now stored
as SQLite documents). The statistics never create, revoke or modify
approval; they only inspect it.

## After a successful local-test build

```bash
uv run --locked python tools/build_ukrainian.py \
  --classicua ../ClassicUA --spoken ../spoken-wow
uv run --locked python tools/translation_db.py imports
```

After ZIP creation, an **immutable metadata-only snapshot** is saved under
SQLite tables `build_import_snapshots` and `build_import_units` (schema v4):
archive SHA-256, exact pinned source revisions, source/category/route and
unit/entity identifiers. No Ukrainian or English translation bodies are
duplicated into the inventory tables. Rebuilding identical source/content/
provenance is idempotent; changed provenance or included content creates a
new snapshot, keeping historical snapshots.

For Quest ZIP output, the counter follows the *actually rendered* unique
Quest/event moments; it excludes ambiguous variants skipped by the builder.
For Gossip ZIP output, it includes actual ClassicUA NPC/common entries,
explicitly imported manual/AI-reviewed NPC wordings, and source-selected
overrides attributed to the winning provider. Titles are shown separately.

If a ZIP build fails, no new successful-build snapshot is recorded.
Review imports and selected source versions may still exist in their
respective tables.

## Safety

- This report is **local-only**, through the existing loopback HTTP server.
  No new network service or public export is created.
- It preserves existing evidence, rights, manual review and source pinning.
  It never treats source candidates as imported text.
- It never prints or checks in private translation bodies.
- **Backups:** `uv run --locked python tools/translation_db.py backup`
  includes both import inventories and all previous approval/history records.
- The ZIP remains a **private test build**, not a release. The numbers are
  auditable metadata, not a claim that NPC/text rendering works in WoW.

## Gossip machine imports (schema v5)

See [the step-by-step Gossip import workflow](GOSSIP_MACHINE_IMPORT.md).
The sixth strict SQLite document records machine Gossip imports separately
from all human decisions. `machine_1to1` covers matched NPC/hash imports and
one record per matched common hash; unmatched ClassicUA hashes no longer enter
new local ZIPs merely because they occur in the source. Source selections and
human imports keep their existing precedence and validation.

Each report section now includes `gossip_counts`: unique translation-text
fingerprints, actual NPC/hash occurrences, distinct NPC IDs, common fallback
translations and recorded reviewed English groups. Per-route rows additionally
show `unique_translation_texts` and `unknown_text_fingerprints`. Historical
snapshots without fingerprints report unknown counts; zero known fingerprints
is not a claim that the archive contained no text. A common fallback is counted
once, never once per possible NPC. NPC occurrence counts belong to the NPC table;
the common table does not fabricate an expanded runtime coverage count.

Schema v5 adds `build_import_units.text_sha256` and the single-row
`build_import_head` pointer. Immutable snapshots remain intact; the head follows
the last successful build even when an older identical snapshot is reused.

The `agent_verified` route counts explicitly recorded local-test agent imports
separately from assessments, machine imports and human decisions. Known stale,
superseded and manually blocked versions do not count as current imports.
The ZIP section follows the route that supplied the actual serialized text.
A common fallback remains one entry in the aggregate Gossip counts even when
both the machine ledger and the agent ledger have recorded it. The route rows
show that each ledger recorded the import.
