# Local translation approval and explicit import

This is an offline Quest review workflow, independent of the unmodified Spoken
Player. **No real joins or real text approvals have been supplied by this PR.**
It creates no audio, pack, runtime activation or publication. Stage 4A discovery
reports and their zero-approved baseline remain unchanged.

## Separate gates

1. Mapping candidates are hints. A human supplies the complete Stage 4B
   approve-request, including an independently inspected `JoinProof`, pinned
   references, full speaker/voice/gender/faction/wording facts and an evidence
   reviewer. A different mapping reviewer must approve it. The UI delegates to
   `approve_explicit_join`, which replays the existing Stage 3 validation.
   The UI never constructs a proof or fills reviewer attestations from hints.
2. Only revalidated reviewed identities can supply translation candidates through
   `approved_quest_bindings`. Actual effective UTF-8 bytes and origin provenance
   are checked against the audited inventory; only verified English originals
   are accepted. AI-marked inputs remain excluded.
3. Explicit **refresh** stores allowed source candidates as `pending` by default. An **opt-in** `auto_approve_one_to_one` source policy may additionally mark the first unique, validated 1:1 ClassicUA candidate as `auto_approved_1to1` in the private ledger. The identity must already have independently human-approved Stage 3 JoinProof; a mere one-to-one match by names/IDs is insufficient. The automatic decision has fixed provenance and `text=false`, `grammar=false`, `ai=true`, `rights=true` checks so it **never masquerades as a human text/grammar review**. Source changes, existing manual edits or decisions, conflicting candidates, unreviewed rights or AI-marked content cannot auto-approve. Content
   reviewers can reject, defer or approve individual versions. Approval requires
   a named reviewer and four explicit attestations: wording, grammar/templates,
   AI restrictions, and rights/attribution. Reviewer IDs record human statements;
   they are not authenticated accounts or proof of independence.
4. Editing creates a new `manual` version with an editor and **no decisions**.
   Refresh never overwrites it. Multiple approved manual versions for one target
   are a conflict: explicitly reject/defer the superseded version before import.
5. Explicit **import** replays the bridge and eligibility checks and atomically
   replaces an **inert local snapshot**. No installed AddOn consumes this file.
   Repeating import with unchanged evidence writes identical bytes and leaves the
   file mtime unchanged. Approval alone never populates the imported snapshot.

Mapping, content, imported snapshot, audio and runtime support are distinct
states. A later official pack builder would need separate authorization and
runtime/rights gates; this snapshot is not a pack or a publication approval.

## Bulk 1:1 import and coverage report

The default schema-v2 config now explicitly enables `auto_approve_one_to_one: true` for ClassicUA (other providers remain disabled). The setting is optional and defaults to false when omitted. The local Review UI exposes **Auto-import 1:1 · ClassicUA** and the same workflow is available from the terminal:

```sh
python3 tools/review_ui_server.py \\
  --classicua /path/to/pinned/ClassicUA \\
  --spoken /path/to/pinned/spoken-wow \\
  --auto-import-one-to-one
```

It re-audits the pinned checkouts, validates pre-existing independent Stage 3 identity proofs, enumerates audited candidates, requires **global one-to-one** cardinality in both source→target and target→source directions (including conflicting faction/AI candidates), preserves manual/version history, optionally auto-approves only the first unchanged eligible ClassicUA version and revalidates before writing the **inert** imported snapshot. It is idempotent: a second run with unchanged evidence adds no versions or approvals. Old automatic approvals become ineligible for re-import if the cardinality changes. A disabled policy fails closed.

The final table (UI and CLI) always uses the **entire pinned Spoken canonical inventory** for `total_spoken_records` and `untranslated_total`. `unreviewed_one_to_one_candidates` are only structural candidates; `verified_source_to_target_bindings` have valid Stage 3 identity reviews and available source texts; `imported_total` counts actual current inert import references, broken out by provider and separately by manual edits. Numbers are deduplicated by canonical Spoken ID. The table is metadata only, never containing imported text or personal reviewer IDs.

**This does not auto-create Stage 3 mapping proofs.** Quest ID/event intersections and shared Horde/Alliance IDs alone do not prove identity. Existing real independently approved joins are zero unless local users have reviewed them; automatic import can legitimately produce zero and list possible 1:1 candidates separately. Places, Readables and Bosses remain in the overall Spoken denominator but await family-specific verified text bridges. No automatic Git write, public pack generation, live AddOn activation, source revision advancement or release takes place.

## Local storage schema

All paths are inside ignored `build/`; do not force-add them or upload them as CI
artifacts. Defaults:

| File | Contents |
| --- | --- |
| `build/stage4b-decisions.json` | Existing strict schema-v2 reject/defer metadata; no bodies |
| `build/stage3-ui-reviews.json` | Existing Stage 3 `review_file` schema-v1 proofs; no bodies |
| `build/translation-reviews.json` | New schema-v1 private translation versions, content decisions and inert import references |

Optional `--reviews` loads a separate Stage 3 file as a read-only input. New UI
mapping approvals go to `--local-reviews`; duplicate sources across input and
local files are refused. `--decisions`, `--local-reviews` and `--translations`
can select distinct files under `build/`, away from input checkouts/configuration.

Translation schema v1 has exactly `schema_version`, `versions`, and `imports`.
Each version has a stable SHA-256 ID, monotonic creation number, canonical/source
IDs, original text SHA-256, source/target identity context SHA-256, grammar
SHA-256, rights state, exact translated UTF-8 text and its SHA-256, audited base
field SHA-256, provider/manual kind, editor, all provider provenance, and ordered
review decisions. Decisions contain reviewer, status and four boolean checks.
The canonical ID is supplied by the audited bridge, never generated from text.
The English original is reloaded from pinned sources rather than copied to disk.

`imports` contains one `{target_id, version_id}` reference per selected approved
translation; its text and provenance are in the same atomic ledger. References
cannot point to unknown, rejected or deferred versions. Consumers must always
revalidate eligibility; merely reading old `imports` is insufficient. The UI
labels a reference imported only while it is currently eligible. Revoking a
content approval immediately removes its imported reference.

HTTP mapping/content writes re-audit both configured pinned checkouts; changed
configuration requires restart, and changed proof/decision/translation files are
refused instead of using a cached copy. GET text presentation uses the audited
in-memory snapshot.

Writes validate the whole schema, reject duplicate JSON keys/versions/provenance
and import targets, use private mode `0600`, flush and fsync a temporary file,
atomically replace the ledger, and fsync its directory. Symlink paths and writes
outside `build/` are refused. Advisory `.lock` files and optimistic disk checks
refuse concurrent stale writers instead of silently dropping edits. A single
transaction contains the ledger and import references, avoiding partial imports.
This local filesystem locking implementation targets Linux/POSIX (no new packages).

## Sources, updates and comparison

The configured ordered allow-list remains authoritative. Quest review discovery uses
`discover_review_candidates`: every real provider candidate up to the explicit
English boundary is visible for independent approval; mocks do not count.
The runtime-oriented `resolve_translation` still stops at the first candidate.
This split is essential: an unapproved higher-priority version must never hide
an eligible approved lower-priority version. `another` is still a stub; `own_translator`
is still mock-only. Empty policy invokes no providers. The standalone UI cannot
read WoW's client locale, so empty policy offers no offline translation candidates
and does not invent English fallback or localized text.

`SourcePolicy` accepts the optional schema-v1 field:

```json
{
  "schema_version": 1,
  "sources": ["classicua", "another", "own_translator", "original_english"],
  "store_locally": {"classicua": true, "another": false}
}
```

Absent entries default to `true`; only enabled providers may appear and values
must be booleans.

The newer **schema v2** config represents each provider as `{ "name": "classicua", "save_translations": true }`. The boolean controls the same private Review UI storage permission as schema-v1 `store_locally` and additionally opts in to a **future** Git-backed curated translation store. No Git-backed writer exists yet. Schema v1 remains supported without changing its private-ledger default; no schema-v1 provider is implicitly opted into Git storage. See [translation storage policy](TRANSLATION_STORAGE_POLICY.md). `false` permits in-memory viewing/discovery but prevents local
storage, editing, approval and import of that provider's candidate. It does not
automatically erase previously stored history: stop the server and remove private
files if local retention must end. Configuration changes require a server restart.
The root default configuration remains compatible and unchanged.

Source discovery and approval selection are separate. The reusable approval
engine considers only current approved versions, chooses configured provider
priority among them, and gives explicitly approved manual edits precedence.
A pending higher-priority candidate cannot replace a current approved lower one.
Equivalent content from another provider can reuse approval only with the same
canonical/source binding, verified original, exact translated bytes, base field,
rights state, grammar and identity contexts; every provenance is retained.
The UI's end-to-end synthetic test verifies that a pending higher-priority
ClassicUA candidate does not conceal an approved lower-priority candidate.
Tests of a second real provider use synthetic data: the running Quest UI currently
has only the ClassicUA real provider and preserves its existing source resolver.
There is no automatic retry of rejected discoveries through lower providers.

A revision/file-only change does not itself change the content approval key.
After independently revalidating mapping and auditing the new input, unchanged
field bytes, original and context may reuse approval; provenance records the new
revision/file hashes. Changed Ukrainian bytes create a new pending version and
make versions based on the old field stale. Manual text remains in history, but
must be rebased through a new edit/review if its audited base changed. Changed
English, speaker/voice, identity context, grammar, AI eligibility or missing
binding prevents import. Compare version numbers, text, exact hashes, base field,
provenance and reviewers in Translation Review; no fuzzy diff or names-based join
is used.

This PR does **not** implement a pin updater or historical-checkout loader.
Existing Stage 3 files still require their independently audited pinned baseline;
a change of pins needs a separately reviewed compatibility/update task and valid
mapping evidence before content reuse can be attempted. Corrupt/stale proofs fail
closed. Missing current evidence never authorizes importing an old snapshot.

## Recovery and migration

Stop the server before recovery; keep private backups **under ignored `build/`**.
A valid existing Stage 4B schema-v2 decision file loads unchanged, and existing
Stage 3 approvals can be passed with `--reviews`. Neither is converted into text
approval. The new translation ledger is created only on an explicit write.
Schema-v1 old workbench decisions are not upgraded by guessing missing evidence:
archive the old file, select a fresh `--decisions` path and re-review current
pinned evidence. A prior defer may be promoted only with a full independent proof;
its metadata remains. A rejection blocks mapping promotion; archive the old ledger
and explicitly re-review in a fresh session to reconsider it.

For a corrupted/unknown-schema file, restore a known valid private backup or
archive it and start with fresh distinct paths, then re-review. Do not edit hashes
to make stale data pass. For a conflict, stop/restart and load the actual disk
state, compare reviewer decisions, and resolve explicitly; no last-writer-wins
merge occurs. Conflicting duplicate Stage 3 inputs must be reconciled before
startup. `.lock` files carry no approvals and may remain after shutdown.

The engine (`adapters/translation_approvals.py`) has no Quest parsing or HTTP
logic. Other content families can later supply independently verified bindings
to `ReviewCandidate`; their identity/content/runtime review rules are outside
this PR. See the [UI guide](STAGE_4B_LOCAL_REVIEW_UI.md) for commands and security.
