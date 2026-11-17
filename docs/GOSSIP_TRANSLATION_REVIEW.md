# Gossip translation expansion — local review workflow

**Goal:** turn missing NPC Gossip into reviewable Ukrainian translations,
rather than mistaking the 15 NPC-specific ClassicUA records for all coverage.
The pinned Spoken corpus currently contains 5,047 NPC/hash wordings that do
not match ClassicUA; some English lines repeat across many NPCs. The actual
unique group count is printed by the command below and must not be guessed.

## 1. Build a deduplicated private translation queue

Use **clean, exact pinned** Spoken and ClassicUA Git checkouts
from `sources.lock.json`:

```bash
uv sync --locked
uv run --locked python tools/gossip_translation_review.py queue --classicua ../ClassicUA --spoken ../spoken-wow --batch-size 40
```

Files ignored by Git:
- `build/gossip-translation-queue.json`: all grouped English source text,
  NPC IDs, context and source hashes, sorted by number of NPC occurrences.
- `build/gossip-batches/batch-0001.json` etc: 40 unique English
  lines each, with empty `ukrainian_text`. No network/model calls
  are made. To use Codex or a translation model, process these JSON files
  locally; keep their stable IDs/revision/context hashes unchanged. Translate
  *only* `ukrainian_text`. Do not modify WoW placeholders,
  gender/class/race references or game terminology without review.

Do not commit source batches, model outputs, reviewed text, or ledgers.

## 2. Propose translated text — status PENDING

After a batch has every required `ukrainian_text` populated,
submit that private JSON:

```bash
uv run --locked python tools/gossip_translation_review.py propose --classicua ../ClassicUA --spoken ../spoken-wow --input build/gossip-batches/batch-0001.json --provider own_translator
```

Multiple candidate versions are retained, never overwritten. Missing,
duplicate, stale, invalid or empty translations fail closed. The ledger
is `build/gossip-translation-reviews.json`. `manual` and
`own_translator` provenance are distinguishable. **No automatic
translation API is bundled**; this is a reproducible local export/import seam.

## 3. Human Translation Review — status APPROVED / REJECTED / DEFERRED

Inspect English, Ukrainian, every NPC name and ID in the queue, original
dynamic variables, game terminology and source rights. The reviewer must
affirm *all five* distinct checks. No checks are implied automatically:

```bash
uv run --locked python tools/gossip_translation_review.py review --classicua ../ClassicUA --spoken ../spoken-wow --version <exact-version-id> --decision approved --reviewer <reviewer-id> --checked-text --checked-grammar --checked-ai --checked-rights --checked-all-contexts
```

Rejected/deferred versions remain in history. Revising an existing
translation is done by proposing a **new** version, not editing an approved
record in place. Conflicting simultaneously approved versions block imports.

## 4. Explicit import and local test build

```bash
uv run --locked python tools/gossip_translation_review.py import-approved --classicua ../ClassicUA --spoken ../spoken-wow
uv run --locked python tools/build_ukrainian.py --classicua ../ClassicUA --spoken ../spoken-wow
```

**Pending does not import. Approved alone does not import.** Only an
explicitly imported and still approved version with unchanged pinned
source/context enters the **ignored local-test ZIP** as NPC-scoped
English-hash entries. It never overwrites existing ClassicUA NPC or
`!common` translations. The build refuses stale or
revoked imported rows instead of silently shipping them.

This review concerns native Gossip text only, not approved canonical Spoken
mapping, narrator captions, audio generation, license rights to other source
projects or a public release. Repeat manual WoW Forever client testing
(including Cyrillic glyphs, placeholders and Shift-to-English) before release.

## Browser-based Gossip Translation Review

Launch the existing **local-only** review server:

```bash
uv run --locked python tools/review_ui_server.py --classicua ../ClassicUA --spoken ../spoken-wow
```

Open `http://127.0.0.1:8765/` and scroll to **Gossip Translation Review · NPC**.
The list is sorted by shared English wording frequency. Select a group to see
its English original, ALL NPC IDs/names and a Ukrainian translation editor.
**Save as pending version** stores a new manual proposal with provenance; choose
a version from the version history, enter a reviewer ID, personally check all
five explicit attestations (text, grammar, AI, rights, all NPC contexts), then
approve/reject/defer. **Import approved (local)** is a separate action. Pending
or approved-but-not-imported text cannot enter a ZIP.

The Gossip panel and CLI share the same atomic, private
`build/gossip-translation-reviews.json` ledger. Quest Translation Review stays
separate and does NOT review Gossip. The server retains its strict loopback,
Origin, CSRF, content-type and request-size checks.
