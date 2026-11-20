# Spoken Ukrainian CLI

**Spoken 3.10.1 integration (PR #39, Draft):** the active audited pin is `spoken/v3.10.1`. Independent Quest/Gossip text-only ZIPs register through `Spoken:RegisterText`, retain native hooks and require no Ukrainian audio. See [source migration, build/install and WoW acceptance](SPOKEN_3101_TEXT_PACK.md). The manager's shared **Install** action first builds and verifies the selected module and its checksum, then uses the backup/rollback installer. Actual client acceptance is still pending.

**Quest local UI:** For normal Quest translation selection, use the simplified [Translation Manager guide](TRANSLATION_MANAGER.md). Historic advanced review commands remain available for migration and diagnostics, but the Quest screen no longer requires reviewers or attestations.

[Українська](CLI.uk.md)


## Incremental Quest import (only ready records)

Saving a Quest translation or choosing an existing candidate stores the selection in SQLite only. It **does not rebuild a ZIP**. The Quest UI shows three buckets: Imported, Ready to import, and Problematic. The **Create module** button performs a ready-only incremental import: it copies previously imported Quest ID/event texts and provenance from the current checksum-verified ZIP, adding or replacing only ready moments. All other candidate texts are excluded. It rebuilds the ZIP file as a deployment artifact, not as a second database. Gossip is not touched.

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

The [Gossip mapping audit](GOSSIP_MAPPING_AUDIT.md) compares the historical Spoken pin with a separately verified 3.10.1 baseline and writes private evidence under `build/`.

```bash
uv run --locked python tools/gossip_mapping_audit.py --classicua "$CLASSICUA_SOURCE" --spoken-390 "$SPOKEN_SOURCE" --spoken-3101 build/spoken-3.10.1
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

### Installation from Translation Manager

The **WoW path** field defaults to D:\Games\World of Warcraft. After **Create module**, click **Інсталювати** (Install). The server strips trailing separators and appends \_forever_\Interface\AddOns to the game root. With the default value, the target is D:\Games\World of Warcraft\_forever_\Interface\AddOns.

The button installs the last SQLite-tracked, SHA-256-verified ZIP for the selected Quest or Gossip module. It does not rebuild the ZIP. It reuses the existing tools/install_addon.py implementation: validate manifest and dependencies, back up existing Ukrainian addon folders into AddOns\.spoken-ukrainian-backups, safely extract and replace the private folders, and roll back on failure. The UI displays the backup path. Restart WoW afterward.

The WoW root and AddOns folder must exist on the computer hosting Translation Manager. Windows paths require Windows; do not add _forever_ or Interface\AddOns to the input.



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

Use the [local manager](TRANSLATION_MANAGER.md) for routine editing.

1. Select Quest or Gossip and open a verified English original.
2. Choose, type or paste Ukrainian text. Save to SQLite. Copy the Codex prompt if you want to draft externally.
3. Select **Створити модуль** to build the selected ZIP. Quest merges ready moments into its verified archive. Gossip uses current local selections.
4. Close WoW, enter the game root in **WoW path**, and choose **Інсталювати**. The manager builds the selected module, then verifies and installs the ZIP with its shared core. Read the displayed destination and backup path.

The `translation_manager.py reimport` command remains available for private full builds. Pass clean pinned source checkouts and `--confirm`. Use `--dry-run` for a preview, `--db` for a private SQLite path, and `--json` for structured results. `--reset-test-data` applies only to the separate Quest rebuild command. The older Gossip review and machine-import CLIs remain available for archival work.

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


### Gossip ready records and separate IDs

The Gossip manager exposes **npcID** (NPC identifier) and **ID** (the 32-bit English-text hash used by the runtime lookup) separately. For example, `gossip:68:107874079` is shown as npcID `68` and ID `107874079`.

A unique, runtime-safe ClassicUA candidate with verified NPC context is automatically **Ready to import** when it is an exact NPC/common hash match, an audited `whitespace_candidate`, or an independently rechecked `same_template` English match. No Save click is needed before Create module. The source hash is retained for provenance while the installed translation uses the Spoken runtime NPC/English hash. The private ZIP records the route as `pinned_unique`, not human approval. Existing matching ZIP units show Imported.

The Gossip list has a **Match type** filter (e.g. Exact NPC, Exact !common, Whitespace, Same template, One-token edit, Other evidence, No match), combinable with Status and Search. Filtering is performed before server-side pagination; the match type is visible in the list and inspector. A record may have multiple audit evidence types. Only the three strictly permitted categories above are candidates for automatic selection, and only if exact English/template comparison, pinned file provenance, NPC/common scope, and formatting/placeholder checks all pass for **every** runtime original. Distinct possible source records, changed revisions, stale manual selections and unsupported placeholders remain Problematic; `one_token_edit`, mismatched NPC scope, TTS recording variants and other fuzzy leads remain review-only. Automatic selection is not a human translation or rights approval.

