# SQLite Translation Store — local durable persistence

## Scope

Spoken Ukrainian CLIs now keep the following existing review ledgers in **one**
SQLite database, by default at:
- Linux: `$XDG_DATA_HOME/spoken-ukrainian/translations.sqlite3`, or
  `~/.local/share/spoken-ukrainian/translations.sqlite3` when XDG is unset.
- Override the path for all commands with `SPOKEN_TRANSLATION_DB=/path/to/translations.sqlite3`.

**No Docker, PostgreSQL or third-party Python dependencies required.** Both
Gossip and Quest translation version history are durable across regenerations,
repository clones, build cleanup and changes to `dist/`. The database is
outside Git. Use a backup to move this history to a different computer.

## What is stored?

- `ledger_documents`: five independent versioned documents that preserve
  the existing validation and human review decisions exactly:
  - `gossip-translation-reviews.json`
  - `translation-reviews.json`
  - `stage3-ui-reviews.json`
  - `stage4b-decisions.json`
  - `machine-one-to-one.json`
- `translation_memory`: indexed individual historical translations with
  stable English SHA, Ukrainian text, current review status, provider and
  context digest. Indexed rows are updated incrementally, not wholesale
  deleted/reimported on ordinary decisions. It's a searchable *cache*, not
  a substitute for validated evidence or review approvals.
- `schema_migrations`: current schema version (1).

All ledgers, history, and imports are transactional. The system checks the
previous document bytes before a write; concurrent edits reject and require a
reload, rather than silently dropping somebody else's work.

## First-time migration from JSON

1. **Back up** your old repository's `build/` directory before the first
   SQLite-enabled run. It may contain the only existing reviewed translations.
2. Update `main` after this PR is merged.
3. Start the *normal* local review UI or run the Quest or Gossip CLI with the
   same pinned checkouts as before:

```bash
uv sync --locked
uv run --locked python tools/review_ui_server.py --classicua ../ClassicUA --spoken ../spoken-wow
```

Each supported legacy JSON file is loaded using its **existing strict
validator** and imported once to SQLite. Legacy files remain on disk
untouched as extra backups. From then on, the SQLite record is authoritative
and the old JSON will not be read again. Do **not** keep editing the old
JSON expecting it to sync. For an old checkout on another machine, back up
and transfer the SQLite database instead.

Invalid or stale identity reviews fail closed and cannot be silently imported.
If a source revision changes, previously stored translation bodies survive,
but approval for changed source/NPC contexts must be revalidated.

## Explicit initialization, status and backup

`status` is read-only and reports `database_exists: false` when the configured
database is missing. It does not create directories, initialize or migrate SQLite.
For a **new store only**, explicitly run `init` to create the existing schema:

```bash
uv sync --locked
uv run --locked python tools/translation_db.py status
uv run --locked python tools/translation_db.py init
```

`init` preserves existing rows and does not import legacy JSON. To migrate old
ledgers, use the normal review workflow above with the existing pinned sources.
If you expected saved reviews, locate or restore their database instead of
initializing an empty replacement. All these commands accept
`--db /path/to/translations.sqlite3`; `SPOKEN_TRANSLATION_DB` sets the default
for all tools.

Once a database exists, create a backup:

```bash
uv run --locked python tools/translation_db.py status
uv run --locked python tools/translation_db.py backup
# Or specify a path:
uv run --locked python tools/translation_db.py backup --output ~/backups/spoken-translation-2026.sqlite3
```

Online SQLite backups are consistent and include schema, approvals and review
history. The source is opened read-only: backup never initializes or migrates it,
and never creates a missing source database. Paths are resolved after rejecting
symlinks (including parent directories). Missing sources, identical resolved
paths and existing destinations have distinct errors with local source/destination
paths and corrective suggestions. A backup never overwrites an existing file;
choose another `--output` if a timestamped backup already exists. Diagnostics omit
translation bodies and raw database exceptions; redact personal paths before
sharing logs. Keep a separate copy off the machine for disaster recovery.
**Never commit or publish your personal database**, old ignored JSON
ledgers, translation batches or model-generated drafts.

## Reusing approved translations across NPC/source revisions

`gossip_translation_review.py queue` consults the indexed SQLite translation
memory when generating **new** batch files. A unique previously **approved** Ukrainian version (or an unambiguous
existing **pending** draft when no approved version exists) for the same
English hash may prefill the draft field,
saving a repeat model call even when the Spoken source revision or NPC
context differs.

**Important:** This is only a DRAFT. Any new context requires a fresh
proposal, human verification of *all NPC contexts*, an explicit approval,
and a separate import before inclusion in the local test ZIP.
Conflicting approved translations for an English hash are not reused
automatically. Existing edited batch files are never overwritten.

The imported audio/preview handling, pinned ClassicUA translation source,
Quest Stage 3 proof, approval policies and game integration are unchanged.
No LLM model calls occur in database setup or ordinary builds.

## Compatibility / rollback

For direct Python unit tests and library callers, `LocalFile` without a
database context retains the original JSON behavior. Running the three
normal executable CLIs (`review_ui_server.py`, `build_ukrainian.py`,
`gossip_translation_review.py`) enables SQLite by default. To inspect
an old JSON backup, use your existing tools but **don't run two separate
writers on JSON and SQLite for the same project**.

## Schema v5 — Gossip provisional import

A sixth strict ledger, `gossip-machine-one-to-one.json`, uses the same validated
`ledger_documents` persistence, optimistic concurrency and legacy JSON migration.
It retains full versioned machine provenance and separate unreviewed approval
status; it does not populate human approvals or the human translation-memory
index. Schema v5 also adds metadata-only Gossip text fingerprints to build units
and a pointer to the latest successful build snapshot. Existing history survives.
See [Gossip workflow](GOSSIP_MACHINE_IMPORT.md) and [statistics](IMPORT_STATISTICS.md).
