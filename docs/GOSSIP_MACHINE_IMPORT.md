# ClassicUA Gossip 1:1 machine import (private local tests)

This workflow records **provisional hash-based machine identity**, never a
human canonical Spoken join, quality review, rights attestation or publication
approval. It makes no AI-provider calls and adds no audio. The two installed
folders remain `Spoken_Ukrainian` and `Spoken_Quests_UA`.

## Run the workflow

1. Keep clean local ClassicUA and Spoken checkouts at `sources.lock.json` pins.
   Normal imports/builds never update those pins or external repositories.
2. Initialize the existing locked Python environment and inspect candidates:

   ```bash
   uv sync --locked
   uv run --locked python tools/gossip_machine_import.py status \
     --classicua ../ClassicUA --spoken ../spoken-wow
   ```

3. Explicitly import the eligible candidates, or use the local Review UI:

   ```bash
   uv run --locked python tools/gossip_machine_import.py import \
     --classicua ../ClassicUA --spoken ../spoken-wow
   uv run --locked python tools/review_ui_server.py \
     --classicua ../ClassicUA --spoken ../spoken-wow
   ```

   In **Автоімпорт Gossip 1:1 · ClassicUA**, choose **Імпортувати перевірені 1:1**.
   Filter the NPC/hash table by status. Totals distinguish canonical NPC/hash
   wordings, unique normalized English, import units, human groups and unknown
   contexts. Import changes SQLite; it does not build/install a ZIP.

4. Build the local test ZIP and inspect the independently persisted inventory:

   ```bash
   uv run --locked python tools/build_ukrainian.py \
     --classicua ../ClassicUA --spoken ../spoken-wow
   uv run --locked python tools/translation_db.py imports
   ```

   The builder refreshes **both** Quest and Gossip machine imports on every
   invocation and revalidates pinned sources. There is no skip-import option.
   The SQLite recorded-import report and latest-successful-ZIP report are
   different measurements. Candidate discovery itself imports nothing.

## Identity and precedence

- Read the committed pinned Spoken corpus, with a verified creature/vehicle
  NPC ID and English original. Deduplicate repeated identical normalized
  English occurrences; never use translated NPC names as identity proof.
- Compute the ClassicUA-compatible hash and retain the normalized English
  SHA-256 independently. Different English texts sharing a hash are excluded
  globally, including common fallbacks. Conflicting creature/vehicle contexts
  are excluded; a common fallback cannot bypass such a conflict.
- Prefer the effective ClassicUA NPC/hash field, then effective `!common`.
  Use audited parser/load/override semantics, exact source file SHA-256,
  source revision, origin/override provenance, English/context hashes and text
  SHA-256. Dynamic `!code`, unknown NPC contexts and unmatched hashes are
  excluded. UTF-8 and WoW placeholders are retained unchanged.
- ClassicUA contains **English hashes**, not independently recoverable English
  source bytes. Exact English is verified against Spoken; a hash match remains
  provisional even when no collision is observed in that corpus.
- AI-marked entries follow the existing explicit `allow_ai_transations` policy.
  No source absent from the policy, or forbidden private retention, is imported.
  AI/rights/grammar approval is never synthesized.
- Any existing manual Gossip version (pending, approved, rejected or deferred,
  including historical versions) blocks machine replacement of that wording.
  Source-review decisions/selections also block the affected machine target.
  A common fallback is suppressed if it could bypass a blocked NPC/hash.
- Explicitly imported current human versions and explicit source selections
  retain their existing validation and precedence. Conflicting human imports
  and selections still fail closed. The manual missing-translation queue is
  unchanged; machine import never writes its approvals or attestations.

## Status definitions

| Status | Meaning |
|---|---|
| `eligible` | Current unique candidate; not imported yet |
| `machine_1to1_provisional` | Exact current evidence provisionally imported; `approval_status=unreviewed` |
| `pending_update` | A previously seen target changed, disappeared, or was blocked; history retained and no automatic reactivation |
| `pending` / `approved` / `rejected` / `deferred` | Separate existing manual decisions, never machine-generated |
| `source_selected` | Automation blocked by source review; inspect Source Revision Review for the actual decision/active selection |
| `conflict` | Hash/context ambiguity, conflicting manual states, or a blocked common context |
| `untranslated` | No eligible ClassicUA match |

A changed revision, file/effective text or target binding invalidates the
machine import. New evidence is saved as `pending_update`; old versions survive.
Returning to an earlier source does not automatically reactivate the import.
Use the existing **Source Revision Review** capture → five human checks →
separate activate workflow for an override, then rebuild. Do not edit SQLite
or invent approvals to clear a pending update. The browser never captures or
selects a new source automatically.

## SQLite interpretation

Schema **v5** adds a sixth strict document ledger,
`gossip-machine-one-to-one.json`, inside existing `ledger_documents`; no new
translation-body table is needed. Executed CLIs use the durable database outside
`build/`, honoring `SPOKEN_TRANSLATION_DB` / `XDG_DATA_HOME`. Library tests retain
isolated JSON support. Migration is non-destructive, validated and transactional.

`build_import_units.text_sha256` stores metadata fingerprints for actually
serialized Gossip text. Legacy snapshots keep an empty/unknown fingerprint;
unknown fingerprints are reported, never guessed. `build_import_head` identifies
the most recently successful ZIP even when it reuses an older immutable snapshot.
Identical builds do not append duplicate snapshots or translation versions.

`gossip_counts` separates unique Ukrainian text fingerprints, NPC/hash occurrences,
distinct NPC IDs, common fallback translations and recorded human English groups.
A common import has one record regardless of its many verified NPC bindings.
Recorded human ledgers contain English groups, so those are explicitly counted as
groups; actual NPC occurrences are measured from the successful build. Manual and
human-reviewed provider routes and explicit source selections remain separate.
Unique-text totals do not count missing historical fingerprints as known text.
No text bodies enter inventory tables, reports or Git.

## WoW: Forever acceptance (still required)

1. Back up the local translation database with `tools/translation_db.py backup`.
2. Build the ZIP above. Install its two folders manually in a **local test**
   client, retaining the official unmodified Spoken addons. No installer change
   or public release is part of this workflow.
3. With runtime ClassicUA disabled, visit an imported NPC-specific case and a
   common greeting/reply case. Verify Ukrainian glyphs, placeholders, repeated
   greetings, and that matching remains scoped to the right NPC/English hash.
4. Hold/release Shift to verify English original/restoration. Visit an unmatched
   or excluded context and confirm native English remains.
5. Enable runtime ClassicUA and verify the Ukrainian addon yields to it. Check
   manual/source-selected overrides, NPC Quest titles and native QuestFrame
   behavior for regressions.
6. Rebuild twice and compare ZIP SHA-256 and SQLite inventory. Record client
   version, NPC IDs, English hashes and observed results privately.

Python/Lua simulations and ZIP checks are **not live-client acceptance**.
This feature translates the existing native Gossip UI only; it does not unlock
Spoken narrator captions, Compendium text or text-only audio playback.

## Pinned-source implementation check (2026-11-18)

Spoken `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`, ClassicUA
`1770d208ad853d23d61105cf510d53804770d916`; isolated SQLite acceptance store:

| Measurement | Before | After |
|---|---:|---:|
| Verified matching NPC/hash wordings / 7,429 valid corpus wordings | 2,382 | 2,382 |
| Recorded provisional Gossip import units in fresh SQLite | 0 | 216 |
| Embedded NPC-specific Gossip units | 100 raw source entries | 3 verified machine imports |
| Embedded common fallback units | 327 raw source entries | 213 verified machine imports |
| Unmatched canonical NPC/hash wordings / 7,429 | 5,047 | 5,047 |

The 216 imported texts have 2,382 verified corpus placements (3 NPC-specific,
2,379 common placements). The SQLite ZIP inventory counts **3 explicit NPC/hash
entries and 213 global common entries**, not 2,382 duplicated translations.
All 216 Ukrainian fingerprints are distinct in this pinned audit. This is
structural/provisional coverage; no human Gossip approvals were manufactured.
The previous raw-source ZIP included unmatched source hashes; the new build
excludes them without reducing observed matching corpus coverage.

Two real local builds produced SHA-256
`2acc9f690f456f5eaa2e3c638af4a48327aa1dcc48cdaa4b47fb9e3f7ab55f3c`,
216 Gossip versions/imports and one successful immutable snapshot. The complete
360-test suite passed, including synthetic human-import preservation and actual
ZIP inventory tests; live-client acceptance is still pending.
