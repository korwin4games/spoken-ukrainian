# Source revision history and conflict resolution

This workflow is **local-only** and uses the persistent SQLite database
introduced in PR #24. No upstream source is rewritten. All source bodies,
version differences, decisions and selections remain **private** in
`~/.local/share/spoken-ukrainian/translations.sqlite3` (or
`SPOKEN_TRANSLATION_DB`). The database is excluded from Git.

## Source revision capture

Use clean Git checkouts at the commits in `sources.lock.json`:

```bash
uv sync --locked
uv run --locked python tools/source_revision_review.py capture \
  --classicua ../ClassicUA --spoken ../spoken-wow
uv run --locked python tools/source_revision_review.py revisions
```

The capture uses audited ClassicUA exact NPC ID + English hash data, matched
against the pinned Spoken Gossip corpus. Quest candidates only come from
**independently approved Stage 3 canonical mappings**. It preserves one
immutable snapshot per `(provider, revision)`, with source text, provenance,
context and English hashes. Reimporting an identical snapshot is harmless.
Attempting to silently replace contents under the same revision fails.

The source pin **does not advance automatically**. To compare a newer
ClassicUA revision, first audit and explicitly update `sources.lock.json`
and supporting source manifest/hashes in a separate tested change, then
capture it. Both snapshots remain in SQLite.

## Compare revisions

```bash
uv run --locked python tools/source_revision_review.py diff \
  --provider classicua --before <old-commit-sha> --after <new-commit-sha>
```

The local report enumerates `added`, `removed`, `changed` and
`unchanged` records with before/after text. It never deletes the previous
translation or silently moves a manual selection to a new revision.

## Additional source (Source B)

Export a **verified, private** template of 40 Spoken contexts:

```bash
uv run --locked python tools/source_revision_review.py template \
  --classicua ../ClassicUA --spoken ../spoken-wow \
  --provider another --revision <source-B-commit-sha> \
  --output build/source-review/another-batch-0001.json --limit 40
```

Edit only `ukrainian_text` and `source_ref` for the contexts actually
covered by Source B. `source_ref` must identify a real audited origin.
Leave unknown translation fields empty; they will be skipped. Metadata and
English original must remain exactly as captured from pinned Spoken.

```bash
uv run --locked python tools/source_revision_review.py ingest \
  --classicua ../ClassicUA --spoken ../spoken-wow \
  --input build/source-review/another-batch-0001.json
uv run --locked python tools/source_revision_review.py conflicts
```

**Important:** each input represents one **complete immutable snapshot**
for one `(provider, revision)`. If Source B contains several batches at
the same revision, combine them into a single `records` array before
ingesting. A second, different snapshot with the same provider and revision
will be rejected. The first import doesn't grant rights or approve text.
Untrusted JSON cannot impersonate the pinned ClassicUA provider.

## Review and explicit selection

Find a candidate ID from `conflicts` or a revision diff. A reviewer must
personally attest all five checks for any approval:

```bash
uv run --locked python tools/source_revision_review.py review \
  --classicua ../ClassicUA --spoken ../spoken-wow \
  --candidate <candidate-sha256> --decision approved --reviewer <reviewer> \
  --checked-text --checked-grammar --checked-ai --checked-rights \
  --checked-all-contexts

uv run --locked python tools/source_revision_review.py activate \
  --classicua ../ClassicUA --spoken ../spoken-wow \
  --candidate <candidate-sha256> --reviewer <reviewer>
```

`approved` alone does not activate; activation requires another explicit
action. Source priorities from `config/translation_sources.json` determine
**advisory recommendation only**; they never replace a manual choice.
Different provider texts show as conflicts without a winning version being
chosen automatically. Rejection/defer revokes an active selection, preserving
the candidate and the audit trail. Selection is frozen to the selected
candidate's **exact source revision and text** when a new source revision is
captured.

A selected source Gossip text is inserted as an NPC-scoped override in the
**private local-test ZIP** only after pinned original/context and human-review
revalidation. This may override ClassicUA's existing default wording.
Two contradictory separately approved Gossip review paths block the build.
For Quests, an active source candidate additionally requires an independently
approved Stage 3 mapping. Ambiguous variants cannot be combined into a
false single spoken moment.

No public release is authorized. Source provenance, permissions, NPC
context, WoW runtime acceptance, glyphs, placeholders and audio still
require independent validation.

All activation, manual clearing, and rejection-triggered revocations are
recorded in an **append-only source selection audit trail** (in addition to
the immutable source versions and decision history). To inspect the
historical choices for a specific context:

```bash
uv run --locked python tools/source_revision_review.py selection-history \
  --domain gossip --target gossip:42:<english-hash>
```


## Browser-based source conflict review

Start the existing localhost review UI with the pinned checkouts:

```bash
uv run --locked python tools/review_ui_server.py \
  --classicua ../ClassicUA --spoken ../spoken-wow
```

Open `http://127.0.0.1:8765/` and use **Source Revision Review ·
ClassicUA / Source B**. Each entry shows its latest provider candidates,
all text variants, source revision, review status and explicitly selected
version. When the selected version belongs to an older source revision, it
is labelled **ACTIVE · OLD REVISION** rather than silently replaced.

To review a version, choose it, provide a reviewer ID, tick all five
independent attestations and click **Approve**. Only after this can
**Явно вибрати активну версію** select it for the private local-test ZIP.
Reject / Defer revokes that candidate's active selection and retains
history. **Прибрати активний вибір** reverts to the normal tested fallback.
All endpoint writes use the same localhost Host/Origin, CSRF, JSON,
request-size and pinned source revalidation guards as Quest/Gossip.
Source capture, private Source B import and revision comparison remain
CLI operations; the UI never fetches untrusted sources automatically.

## Backups

```bash
uv run --locked python tools/translation_db.py backup
```

This includes both existing Quest/Gossip review ledgers and all new source
snapshots, decisions and selections. Keep an off-machine copy.
