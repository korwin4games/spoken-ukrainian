# Spoken Ukrainian CLI

**Quest local UI:** For normal Quest translation selection, use the simplified [Translation Manager guide](TRANSLATION_MANAGER.md). Historic advanced review commands remain available for migration and diagnostics, but the Quest screen no longer requires reviewers or attestations.

[Українська](CLI.uk.md)


## Incremental Quest import (only ready records)

Saving a Quest translation or choosing an existing candidate stores the selection in SQLite only. It **does not rebuild a ZIP**. The Quest UI shows three buckets: Imported, Ready to import, and Problematic. The **Import all (N)** button performs a ready-only incremental import: it copies previously imported Quest ID/event texts and provenance from the current checksum-verified ZIP, adding or replacing only ready moments. All other candidate texts are excluded. It rebuilds the ZIP file as a deployment artifact, not as a second database. Gossip is not touched.

The same operation is available through the CLI:

```bash
uv run --locked python tools/translation_manager.py reimport --module Spoken_Quest_UA --classicua ../ClassicUA --spoken ../spoken-wow --confirm --import-ready
```

The legacy command without `--import-ready` remains a separate full rebuild. A first import can start without an existing ZIP if no prior build is recorded. Otherwise, the ready-only operation fails closed if a previously recorded Quest ZIP is missing, untracked, modified, or has stale import metadata. Back up your DB/ZIP before a recovery or full rebuild. Never treat a SQLite-only selection as already installed in WoW.

## Setup and source pins

Install Git, uv and Python 3.12 (uv can install the version in `.python-version`). Tests require the Lua 5.4 shared library; CI uses `liblua5.4-0` on Ubuntu. Node is needed only for the Review UI JavaScript syntax check. Clone sibling repositories, then detach them at the revisions in [sources.lock.json](../sources.lock.json). These setup commands fetch upstream repositories. Project commands use local, clean checkouts and fail when a pin or audited file hash differs. In the examples, run from the project root and replace uppercase values such as `CANDIDATE_ID` with real IDs reported by the local workflow.

```bash
git clone https://github.com/korwin4games/spoken-ukrainian.git
cd spoken-ukrainian
uv python install 3.12
uv sync --locked
git clone https://github.com/rusty-key/spoken-wow.git ../spoken-wow
git clone https://github.com/greenya/ClassicUA.git ../ClassicUA
SPOKEN_PIN=$(uv run --locked python -c 'import json; print(json.load(open("sources.lock.json"))["spoken"]["revision"])')
CLASSICUA_PIN=$(uv run --locked python -c 'import json; print(json.load(open("sources.lock.json"))["classicua"]["revision"])')
git -C ../spoken-wow switch --detach "$SPOKEN_PIN"
git -C ../ClassicUA switch --detach "$CLASSICUA_PIN"
export SPOKEN_SOURCE="$(realpath ../spoken-wow)"
export CLASSICUA_SOURCE="$(realpath ../ClassicUA)"
```

## Database, environment and statistics

`SPOKEN_TRANSLATION_DB` selects the durable SQLite file across commands. Otherwise it is under `$XDG_DATA_HOME/spoken-ukrainian` or `~/.local/share/spoken-ukrainian`. Commands with `--db` override the environment; `SPOKEN_SOURCE` supplies the test checkout. The CI scripts also use `CLASSICUA_SOURCE` for explicit flags. `UV_CACHE_DIR` can redirect uv's cache to a writable location.

`status` reports the selected file and ledger counts without creating the database. `init` creates or migrates the schema; normal review commands migrate validated legacy ledgers. `backup` creates a SQLite snapshot including approval, agent and import history. `--output` applies to backup and must name a new non-symlink destination. If data appears missing, locate the original database before initializing another. `imports` reports recorded machine, human and agent imports, explicit selections and actual latest ZIP inventory as separate JSON sections. See [SQLite storage](SQLITE_TRANSLATION_STORE.md) and [import statistics](IMPORT_STATISTICS.md).

```bash
uv run --locked python tools/translation_db.py status
uv run --locked python tools/translation_db.py init
uv run --locked python tools/translation_db.py backup --output /tmp/spoken-translations-backup.sqlite3
uv run --locked python tools/translation_db.py imports
```

## Source policy and offline audits

Edit [translation_sources.json](../config/translation_sources.json) using the [source-chain contract](TRANSLATION_SOURCE_CHAIN.md). Order determines the offline provider pass. Empty list/object requires the actual client locale for coverage. Stub/mock providers do not supply real translations. Retention and AI-marker policy remain independent of source order and approval. A file-path or source-pin error means inspect the checkout before retrying.

`classicua_audit.py` takes a pinned `--source` and optional `--output` for effective metadata. `stage3_report.py` reads both pins and emits metadata; `--reviews` supplies independent joins, and `--candidate` with `--candidate-manifest` supplies a separately verified update comparison. `stage4_coverage.py` takes `--spoken`, optional `--policy`, `--client-locale` and `--output`; it reports source candidates and the full canonical inventory. `gossip_coverage.py` writes an ignored JSON report and NPC CSV. Keep outputs under ignored `build/`. See [Stage 3](STAGE_3_IMPLEMENTATION.md), [Stage 4A](STAGE_4A_INVENTORY_COVERAGE.md) and [Gossip coverage](GOSSIP_COVERAGE_AUDIT.md).

```bash
uv run --locked python tools/classicua_audit.py --source "$CLASSICUA_SOURCE" --output build/classicua-audit.json
uv run --locked python tools/stage3_report.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --output build/stage3-report.json
uv run --locked python tools/stage4_coverage.py --spoken "$SPOKEN_SOURCE" --policy config/examples/client-language.json --client-locale enUS
uv run --locked python tools/gossip_coverage.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE"
```

## Quest identity, review and machine import

The workbench writes a metadata JSON queue and a CSV worksheet. Use `--faction alliance|horde`, `--offset`, `--limit`, `--output`, `--worksheet-output` and optional `--reviews`. With `--decisions`, a complete `--source-id --target-id --decision --reason --reviewer` records a rejection/deferral; `--help` lists exact reason codes. Alternatively `--approve-request` validates an independently supplied two-human Stage 3 JoinProof. A stale decision/proof or mismatched identity is refused. See [workbench](STAGE_4B_REVIEW_WORKBENCH.md).

The loopback server uses `--port` (8765 by default), optional `--decisions`, `--reviews`, `--local-reviews`, `--translations` and `--policy`. In Translation Review, inspect the original, edit, record a human decision and then import. `--import-approved` runs the explicit approved Quest import without serving HTTP. `--auto-import-one-to-one` executes the Quest machine workflow instead. These flags are mutually exclusive. Machine candidates remain provisional, and unknown/ambiguous evidence is excluded by the existing gates. See [human approvals](TRANSLATION_APPROVALS.md).

```bash
uv run --locked python tools/stage4b_workbench.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --faction horde --limit 40
uv run --locked python tools/stage4b_workbench.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --decisions build/stage4b-decisions.json --source-id SOURCE_ID --target-id TARGET_ID --decision deferred --reason insufficient_evidence --reviewer REVIEWER
uv run --locked python tools/stage4b_workbench.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --approve-request build/join-proof.json
uv run --locked python tools/review_ui_server.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --port 8765
uv run --locked python tools/review_ui_server.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --import-approved
uv run --locked python tools/review_ui_server.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --auto-import-one-to-one
```

## Gossip review, optional Codex drafts and machine import

`queue` writes private deduplicated groups and batches without replacing drafts; `--batch-size` accepts 1–100. Edit a private batch, then `propose --input` adds a pending version under provider `manual` or `own_translator`. `status` inspects the ledger. `review` needs the exact `--version`, reviewer and decision; approval requires all five checks. `import-approved` explicitly records current human-approved groups. Stale/conflicting text or incomplete attestations fail. The optional Codex draft helper does preflight by default; `--apply` explicitly invokes Codex once for the selected batch and may use model quota. It saves a draft. See [Gossip manual workflow](GOSSIP_TRANSLATION_REVIEW.md).

The separate `gossip_machine_import.py status|import` prints metadata counts or persists current ClassicUA provisional exact matches. Common entries count once; changed evidence becomes pending update. See [machine import](GOSSIP_MACHINE_IMPORT.md).

```bash
uv run --locked python tools/gossip_translation_review.py queue --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --batch-size 40
uv run --locked python tools/gossip_translate_codex.py --input build/gossip-batches/batch-0001.json
uv run --locked python tools/gossip_translate_codex.py --input build/gossip-batches/batch-0001.json --apply
uv run --locked python tools/gossip_translation_review.py propose --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --provider manual --input build/gossip-batches/batch-0001.json
uv run --locked python tools/gossip_translation_review.py status --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE"
uv run --locked python tools/gossip_translation_review.py review --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --version VERSION_ID --reviewer REVIEWER --decision approved --checked-text --checked-grammar --checked-ai --checked-rights --checked-all-contexts
uv run --locked python tools/gossip_translation_review.py import-approved --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE"
uv run --locked python tools/gossip_machine_import.py status --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE"
uv run --locked python tools/gossip_machine_import.py import --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE"
```

## Source revision and provider comparison

`capture` stores the current audited ClassicUA snapshot. `template` writes a private batch with `--provider`, `--revision`, `--output`, `--offset`, `--limit`; fill Ukrainian and cite its source, then use `ingest --input`. A candidate file cannot impersonate ClassicUA or change pinned English. Snapshot revisions are immutable. `revisions` lists available names and pins. `diff` compares revisions within one provider. `compare-providers` requires a genuinely different `--other-provider`. Both take `--before`, `--after`, `--change all|added|removed|changed|unchanged`, `--offset` and `--limit` (1–100). A missing snapshot requires capture/ingest first. Reports include paired text and provenance, so keep them private.

`conflicts` summarizes versions. `review` needs `--candidate`, `--decision approved|rejected|deferred`, `--reviewer`, and the five named checks for approval. `activate` explicitly chooses an approved, current candidate. `clear` requires `--domain quest|gossip`, `--target` and `--reviewer`. `active` revalidates current selections, optionally by domain. `selection-history` lists earlier activation/clear events for a target. `--db` selects the same database as the other tools. Use pinned flags for capture, template, ingest, review, activate, clear and active. See [source review](SOURCE_REVISION_REVIEW.md).

```bash
uv run --locked python tools/source_revision_review.py capture --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE"
uv run --locked python tools/source_revision_review.py template --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --provider another --revision SOURCE_B_REV --output build/source-b.json --limit 40
uv run --locked python tools/source_revision_review.py ingest --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --input build/source-b.json
uv run --locked python tools/source_revision_review.py revisions
uv run --locked python tools/source_revision_review.py diff --provider classicua --before PRIOR_CLASSICUA_REV --after "$CLASSICUA_PIN" --change changed
uv run --locked python tools/source_revision_review.py compare-providers --provider classicua --other-provider another --before "$CLASSICUA_PIN" --after SOURCE_B_REV --change all
uv run --locked python tools/source_revision_review.py conflicts
uv run --locked python tools/source_revision_review.py review --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --candidate CANDIDATE_ID --reviewer REVIEWER --decision approved --checked-text --checked-grammar --checked-ai --checked-rights --checked-all-contexts
uv run --locked python tools/source_revision_review.py activate --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --candidate CANDIDATE_ID --reviewer REVIEWER
uv run --locked python tools/source_revision_review.py active --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --domain gossip
uv run --locked python tools/source_revision_review.py clear --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --domain gossip --target TARGET_ID --reviewer REVIEWER
uv run --locked python tools/source_revision_review.py selection-history --domain gossip --target TARGET_ID
```

## Translation Review Agent

Use `status` or `report` to page through candidates and counts. `history` shows timestamped assessments including stale evidence. `review one` takes one exact `--candidate`; `review batch` takes a repeatable list. `review pending` explicitly processes the next bounded batch of previously unassessed candidates. Common selectors are `--module all|quests|gossip`, `--status`, `--limit 1..100`, `--offset`, `--db`; `--json` gives structured output. `--dry-run` on reviews evaluates without saving. Optional `--model-assessment build/model-notes.json` on one record appends separately generated advisory notes. No model process is started by this tool. See [schema and assessment rules](REVIEW_ASSISTANT_AGENT.md).

`import-verified` requires `--dry-run` or `--confirm`. Preview and execution report eligible, would-import, imported, already-imported, skipped and conflict counts with candidate IDs and reason codes. A confirmed call considers the entire selected module by default; `--candidate` optionally restricts the set. `--limit` bounds review batches, result pages, and explicit ID lists. Successful operations, including a successful preview with skips, exit 0; invalid input or evidence/storage failures exit 1; argparse syntax errors exit 2. Use status to refresh stale IDs and the human review flow to resolve conflicts. Import only makes entries eligible for private builds; a subsequent build checks the evidence again.

```bash
uv run --locked python tools/translation_agent.py status --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --module gossip --status unreviewed --json
uv run --locked python tools/translation_agent.py review one --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --candidate CANDIDATE_ID --dry-run
uv run --locked python tools/translation_agent.py review one --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --candidate CANDIDATE_ID --model-assessment build/model-notes.json
uv run --locked python tools/translation_agent.py review batch --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --candidate CANDIDATE_ID --candidate SECOND_CANDIDATE_ID
uv run --locked python tools/translation_agent.py review pending --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --module quests --limit 25
uv run --locked python tools/translation_agent.py report --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --status needs_human_review --json
uv run --locked python tools/translation_agent.py history --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --candidate CANDIDATE_ID --json
uv run --locked python tools/translation_agent.py import-verified --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --dry-run --json
uv run --locked python tools/translation_agent.py import-verified --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --module quests --confirm
uv run --locked python tools/translation_agent.py import-verified --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --module gossip --confirm
```

## Local build, installation and validation

`build_ukrainian.py` revalidates pinned checkouts and automatically refreshes Quest and Gossip machine imports, then checks existing agent imports before creating the private deterministic ZIP and SHA-256 under `dist/`. Missing/dirty sources, stale human evidence and a build without safe Quest moments can stop the command. `install_addon.py` accepts an exact WoW Forever `--addons` directory and optional `--archive`; use `--dry-run` for its plan. The real install writes the two private addon folders and preserves official Spoken. On unsafe paths/archives, exit without installing. See [local build and game checks](QUEST_LOCAL_TEST_BUILD.md).

`build.py` takes no options and builds the separate historical diagnostic archive and checksum. The tests exercise pinned entries and Lua simulations. `version.py show` displays the project version, `check [--tag vX.Y.Z]` validates metadata/tag alignment, and `bump patch|minor|major --dry-run` previews a change. A real bump writes VERSION and requires synchronized metadata, lock and changelog. The first stable major requires `--approve-stable`. See [version policy](VERSIONING.md).

For diagnostics, check the pins and clean status, make sure all review and build commands use the same SQLite file, and restart the local UI after changes to pins or policy. A missing provider needs an explicit capture or ingest. Keep database backups, proposals, model notes, comparison text and generated archives private. Agent and machine status are advisory and authorize only private testing. Public distribution and official Spoken narrator/caption support have separate gates. See [architecture](ARCHITECTURE_UNMODIFIED_SPOKEN.md).

```bash
uv run --locked python tools/build_ukrainian.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE"
uv run --locked python tools/install_addon.py --addons "/path/to/Forever/Interface/AddOns" --dry-run
uv run --locked python tools/install_addon.py --addons "/path/to/Forever/Interface/AddOns" --archive dist/Spoken_Quest_UA_Local_Test.zip
uv run --locked python tools/build.py
uv run --locked python -m unittest discover -s tests -v
node --test tests/manager_frontend.test.cjs
uv run --locked python tools/version.py show
uv run --locked python tools/version.py check
uv run --locked python tools/version.py bump patch --dry-run
```

## Unified Translation Manager

`translation_manager.py reimport` applies the same staged operation as the
localhost manager. The supported modules are `Spoken_Quest_UA` and `Spoken_Gossip_UA`. The
checkout flags name the clean pinned repositories; `--db` can select a private
SQLite database. Use `--dry-run` to build an isolated preview, and `--confirm`
to promote the validated state and ZIP. `--reset-test-data` clears only the
selected module's test review/import histories and manual source choices.
The summary distinguishes database records, effective Quest moments, Gossip
occurrences and serialized common units. It reports mapping, translation and
import states separately, with review queue coverage, agent warnings by
assessed version and unverified Gossip alternatives by NPC/hash occurrence.
The summary counts candidate conflicts (`conflicts`) and rows with multiple
verified English originals (`multiple_originals`) separately.
Use **Save translation** or **Save selection** for a Quest moment in the
Manager. **Import all** applies only ready Quest moments. The Quest ZIP and
Gossip ZIP have separate build heads. Use the
[Manager example](TRANSLATION_MANAGER.md#приклад-перевірки-quest) for selecting
between translations and testing the Quest Journal and font in WoW: Forever.
`--json` includes detailed results
and failure codes. Exit 0 indicates preview or successful promotion, 1 a
failed operation, and 2 invalid CLI syntax. See the [manager guide](TRANSLATION_MANAGER.md).

```bash
uv run --locked python tools/translation_manager.py reimport --module Spoken_Quest_UA --classicua ../ClassicUA --spoken ../spoken-wow --reset-test-data --dry-run --json
uv run --locked python tools/translation_manager.py reimport --module Spoken_Quest_UA --classicua ../ClassicUA --spoken ../spoken-wow --confirm
uv run --locked python tools/translation_manager.py reimport --module Spoken_Gossip_UA --classicua ../ClassicUA --spoken ../spoken-wow --confirm
```

### Manager cache and timings

The server keeps one catalog per module and shares the parsed, pinned source
inputs between them. Search, filters, pagination and details reuse those
catalogs. Each browse still checks both Git checkouts for the expected revision
and cleanliness. Source pin, manifest or provider policy changes reload the
shared inputs. Database commits, database replacement, legacy ledger changes,
or a changed module ZIP invalidate affected catalog reads. SQLite
`PRAGMA data_version` detects external commits that are still in the WAL.
Successful promotion clears the catalogs. A failed worker leaves the current
catalog eligible for reuse if its input fingerprints match.

Set `SPOKEN_MANAGER_TIMING=1` in the environment before launching
`review_ui_server.py`. Lines marked `manager_timing` report stages, module,
action and milliseconds. The logs omit translation bodies and reviewer data.
Compare builds using the same source commits and copies of the same private
SQLite database and ZIPs. Start a fresh server, open Quest, repeat the list or
search, switch to Gossip, repeat, then switch back and forth. Use `api` for
server dispatch latency and `api_response` to include response serialization
and writing. The first visit to each module is a catalog miss. A first visit
to Gossip after Quest can already reuse the shared sources.
