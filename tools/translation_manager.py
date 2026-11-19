#!/usr/bin/env python3
"""Browse and rebuild the private Quest and Gossip module."""
import argparse
from contextlib import contextmanager, nullcontext
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Lock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.sqlite_translation_store import (
    DB_ENV, LEDGER_NAMES, backup_database, connection, default_db_path, enable_sqlite, protected_path,
)

from adapters.local_review_store import file_lock, strict_json
from tools.build_ukrainian import ARCHIVES, MODULE_DOMAINS, QUEST_MODULE

MODULE = QUEST_MODULE
MANAGER_WORKER_TIMEOUT_SECONDS = 600
SOURCE_INPUTS = ("sources.lock.json", "config/translation_sources.json", "tests/stage3_sources.json")
REVIEW_ONLY = ("save_translation", "register_candidate", "review_mapping", "withdraw_quest_approval")
WORKER_ERRORS = frozenset({
    "manager_confirmation_required", "manager_invalid_options", "manager_unknown_module",
    "manager_reimport_already_running", "manager_state_changed_retry_reimport",
    "manager_source_configuration_changed", "manager_unsafe_database_path",
    "no_unambiguous_quest_imports_for_local_test_pack", "one_to_one_auto_import_not_enabled_for_source",
    "public_revision_mismatch", "public_checkout_modified", "public_checkout_root_required",
    "pinned_classicua_revision_mismatch", "pinned_spoken_revision_mismatch",
    "manager_invalid_review_request", "manager_review_checks_required", "manager_review_context_blocked",
    "manager_invalid_translation_format", "manager_candidate_unavailable", "manager_candidate_not_built",
    "manager_item_not_found", "source_quest_selection_requires_approved_stage3_mapping",
    "source_candidate_pinned_context_mismatch", "explicit_human_join_request_required",
    "current_version_text_and_editor_required", "current_reviewed_identity_required",
    "duplicate_gossip_version", "duplicate_translation_edit",
    "conflicting_quest_runtime_variants",
    "invalid_quest_runtime_review",
})
DOMAINS = "('quest','gossip')"
MODULE_LEDGERS = (
    "stage4b-decisions.json", "stage3-ui-reviews.json", "translation-reviews.json",
    "machine-one-to-one.json", "gossip-translation-reviews.json", "gossip-machine-one-to-one.json",
)
TABLE_SCOPES = {
    "ledger_documents": "ledger_name IN (" + ",".join(repr(s) for s in MODULE_LEDGERS) + ")",
    "quest_runtime_reviews": "1",
    "translation_memory": f"domain IN {DOMAINS}",
    "source_candidate_decisions": f"candidate_id IN (SELECT id FROM source_candidates WHERE domain IN {DOMAINS})",
    "source_active_selections": f"domain IN {DOMAINS}",
    "source_selection_events": f"domain IN {DOMAINS}",
    "agent_assessments": f"json_extract(payload, '$.candidate.domain') IN {DOMAINS}",
}
AGENT_SCOPE = "(SELECT candidate_id FROM agent_assessments WHERE " + TABLE_SCOPES["agent_assessments"] + ")"
TABLE_SCOPES.update({name: "candidate_id IN " + AGENT_SCOPE
                     for name in ("agent_imports", "agent_stale_evidence")})


def module_scopes(module):
    domain = MODULE_DOMAINS[module]
    ledgers = [name for name in MODULE_LEDGERS if name.startswith("gossip-") == (domain == "gossip")]
    return {table: ("ledger_name IN (" + ",".join(repr(name) for name in ledgers) + ")"
                    if table == "ledger_documents" else scope.replace(DOMAINS, f"('{domain}')"))
            for table, scope in TABLE_SCOPES.items()
            if table != "quest_runtime_reviews" or domain == "quest"}


def reset_test_state(db, module=MODULE):
    """Discard only scoped test decisions and imports in the staged database."""
    from adapters.auto_one_to_one import EMPTY as quest_machine
    from adapters.gossip_machine import EMPTY as gossip_machine
    from adapters.mapping import review_file
    from adapters.review_workbench import empty_decisions
    from adapters.translation_approvals import EMPTY as quest_review
    from tools.gossip_translation_review import EMPTY as gossip_review

    assert set(MODULE_LEDGERS) <= LEDGER_NAMES
    scopes = module_scopes(module)
    for table in reversed(scopes):
        if table != "ledger_documents":
            db.execute(f"DELETE FROM {table} WHERE {scopes[table]}")
    # Seed documents rather than deleting them: legacy JSON remains untouched
    # and cannot silently repopulate this test scope during the fresh build.
    db.executemany("""INSERT INTO ledger_documents(ledger_name, payload, revision)
        VALUES (?, ?, 1) ON CONFLICT(ledger_name) DO UPDATE SET
        payload=excluded.payload, revision=revision+1, updated_at=CURRENT_TIMESTAMP""",
        [(name, json.dumps(value, sort_keys=True)) for name, value in zip(MODULE_LEDGERS,
            (empty_decisions(), review_file([]), quest_review, quest_machine, gossip_review, gossip_machine))
         if name.startswith("gossip-") == (MODULE_DOMAINS[module] == "gossip")])


def db_stamp(db):
    digest = sha256()
    for statement in db.iterdump():
        if statement.startswith('INSERT INTO "schema_migrations"'):
            continue  # A fresh staged and promoted schema can have different timestamps.
        digest.update(statement.encode("utf-8") + b"\n")
    return digest.hexdigest()


def file_stamp(path):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("manager_unsafe_archive_path")
    return sha256(path.read_bytes()).hexdigest() if path.exists() else None


def verify_quest_zip(archive, identity, text_hash):
    from zipfile import ZipFile
    from adapters.spoken import literal_data

    with ZipFile(archive) as bundle:
        lua = bundle.read(f"{QUEST_MODULE}/Translations.lua")
    _, quest, event = identity.split(":")
    assignment = b"\nSpokenUkrainian.QuestTranslations = "
    _, separator, table = lua.partition(assignment)
    if not separator:
        raise ValueError("manager_candidate_not_built")
    rows = literal_data(separator + table, "SpokenUkrainian.QuestTranslations")
    entry = rows.get(int(quest), {}).get(event, {})
    if (not entry.get("reviewed") or not isinstance(entry.get("text"), str)
            or sha256(entry["text"].encode("utf-8")).hexdigest() != text_hash):
        raise ValueError("manager_candidate_not_built")


@contextmanager
def manager_lock(directory):
    if directory.is_symlink():
        raise ValueError("manager_unsafe_workspace")
    directory.mkdir(mode=0o700, exist_ok=True)
    try:
        with file_lock(directory / ".translation-manager.lock", blocking=False):
            yield
    except BlockingIOError:
        raise ValueError("manager_reimport_already_running") from None


def source_stamps():
    return [file_stamp(ROOT / path) for path in SOURCE_INPUTS]


def staged_zip(workspace):
    return workspace.with_suffix(".zip")


@contextmanager
def manager_workspace(directory):
    with manager_lock(directory), TemporaryDirectory(prefix=".translation-manager-", dir=directory) as staging:
        workspace = Path(staging)
        incoming = staged_zip(workspace)
        try:
            yield workspace
        finally:
            for path in (incoming, incoming.with_suffix(".zip.sha256"), incoming.with_suffix(".zip.tmp")):
                path.unlink(missing_ok=True)


def promote(db_path, staged, baseline, archive, incoming, archive_baseline, workspace, reset, module=MODULE,
            *, expected_sha=None):
    """Commit scoped SQLite rows and publish the ZIP; roll back on normal failures."""
    checksum = archive.with_suffix(".zip.sha256")
    old_zip, old_checksum = workspace / "previous.zip", workspace / "previous.sha256"
    with connection(db_path) as db:
        db.execute("ATTACH DATABASE ? AS staged", (str(staged),))
        db.execute("BEGIN IMMEDIATE")
        moved = []
        try:
            if db_stamp(db) != baseline or (file_stamp(archive), file_stamp(checksum)) != archive_baseline:
                raise ValueError("manager_state_changed_retry_reimport")
            # Materialize agent child scopes before deleting their parent assessments.
            scopes = module_scopes(module)
            for table in reversed(scopes):
                if not reset and table.startswith("source_"):
                    continue
                db.execute(f"DELETE FROM main.{table} WHERE {scopes[table]}")
            for table, scope in scopes.items():
                if not reset and table.startswith("source_"):
                    continue
                # Subqueries in child scopes must see the staged parents.
                stage_scope = scope.replace("FROM agent_assessments", "FROM staged.agent_assessments")
                db.execute(f"INSERT INTO main.{table} SELECT * FROM staged.{table} WHERE {stage_scope}")
            if incoming is None:
                db.commit()
                return
            for table in ("build_import_snapshots", "build_import_units"):
                db.execute(f"INSERT OR IGNORE INTO main.{table} SELECT * FROM staged.{table}")
            db.execute("DELETE FROM main.module_build_heads WHERE module=?", (module,))
            db.execute("INSERT INTO main.module_build_heads SELECT * FROM staged.module_build_heads WHERE module=?",
                       (module,))
            # Copy to same-filesystem temporary paths so replace is atomic per file.
            digest = file_stamp(incoming)
            if expected_sha is not None and digest != expected_sha:
                raise ValueError("manager_state_changed_retry_reimport")
            incoming_checksum = incoming.with_suffix(".zip.sha256")
            incoming_checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
            for target, new, old in ((archive, incoming, old_zip), (checksum, incoming_checksum, old_checksum)):
                if target.exists():
                    shutil.copyfile(target, old)
                os.replace(new, target)
                moved.append((target, old))
            db.commit()
        except BaseException:
            db.rollback()
            for target, old in reversed(moved):
                if old.exists():
                    os.replace(old, target)
                else:
                    target.unlink()
            raise


def prepare_import(state, spoken, db_path, skipped, module):
    from adapters.translation_agent import AGENT, TranslationAgent, assessment_rows
    from tools.build_ukrainian import local_gossip_texts
    from tools.gossip_coverage import read_pinned_corpus
    from tools.gossip_translation_review import GossipReviews, discover_groups
    from tools.translation_agent import evidence

    domain = MODULE_DOMAINS[module]
    if domain == "gossip":
        lines = read_pinned_corpus(spoken, state.inventory.revision)
        groups, _ = discover_groups(lines, local_gossip_texts(state),
                                    state.inventory.revision, state.source.revision)
        reviews = GossipReviews(groups, state.inventory.revision, state.source.revision)
        reviews.import_approved(skipped=skipped)
    rows = evidence(state, spoken, db_path, revalidate=False)
    agent_module = "quests" if domain == "quest" else "gossip"
    agent = TranslationAgent(db_path, lambda: rows)
    with connection(db_path) as db:
        assessed = {r["candidate"]["id"] for r in assessment_rows(db, latest=True) if r["agent"] == AGENT}
    # A machine-only Quest hint cannot become an agent-eligible mapping.
    ids = [r["id"] for r in rows if r["domain"] == domain and r["identity_verified"] and r["rights_evidence"]
           and r["id"] not in assessed]
    for offset in range(0, len(ids), 100):
        agent.run("batch", module=agent_module, candidate_ids=ids[offset:offset + 100], limit=100)
    return agent.run("import-verified", module=agent_module, confirm=True)


def reimport(classicua, spoken, db_path, *, module=MODULE, reset=False, dry_run=False, confirm=False,
             review=None, stage_in=None):
    """The CLI and localhost UI run the same staged operation."""
    from tools.build_ukrainian import DIST, build, local_test_state
    from tools.manager_inventory import load_inventory

    if type(module) is not str or module not in MODULE_DOMAINS:
        raise ValueError("manager_unknown_module")
    if any(type(v) is not bool for v in (reset, dry_run, confirm)):
        raise ValueError("manager_invalid_options")
    if review is not None and (reset or dry_run):
        raise ValueError("manager_invalid_review_request")
    if not dry_run and not confirm:
        raise ValueError("manager_confirmation_required")
    classicua, spoken = Path(classicua).resolve(), Path(spoken).resolve()
    db_path = protected_path(db_path)
    if db_path.suffix not in (".sqlite", ".sqlite3", ".db") or any(
            db_path.resolve().is_relative_to(p) for p in (classicua, spoken, ROOT / "addons")) or (
            db_path.exists() and (not db_path.is_file() or db_path.stat().st_nlink != 1)):
        raise ValueError("manager_unsafe_database_path")
    archive = ARCHIVES[module]
    review_only = review is not None and review[0] in REVIEW_ONLY
    if stage_in is not None and (stage_in.parent != DIST.resolve()
                                 or not stage_in.name.startswith(".translation-manager-")
                                 or stage_in.is_symlink() or not stage_in.is_dir()):
        raise ValueError("manager_unsafe_workspace")
    with (manager_workspace(DIST) if stage_in is None else nullcontext(stage_in)) as workspace:
        staged = workspace / "translations.sqlite3"
        incoming = staged_zip(workspace)
        if db_path.exists():
            backup_database(db_path, staged)
        archive_baseline = (file_stamp(archive), file_stamp(archive.with_suffix(".zip.sha256")))
        pins = source_stamps()
        with connection(staged) as db:
            baseline = db_stamp(db)
            if reset:
                db.execute("BEGIN IMMEDIATE")
                reset_test_state(db, module)
                db.commit()
        skipped = []
        with enable_sqlite(staged):
            agent = {}
            state_for_inventory = None
            selected_hash = None

            def before_import(state):
                nonlocal selected_hash
                if review is None:
                    return
                from tools.manager_review import apply_review
                action, payload = review
                previous = load_inventory(classicua, spoken, staged, archive, state=state, module=module)
                row = previous.detail(module=module, identity=payload.get("identity"))
                selected_hash = apply_review(action, payload, module, row, state, spoken, staged)

            def prepare(state):
                nonlocal state_for_inventory
                state_for_inventory = state
                agent.update(prepare_import(state, spoken, staged, skipped, module))
            if review_only:
                before_import(local_test_state(classicua, spoken))
            else:
                result = build(classicua, spoken, module=module, before_import=before_import if review else None,
                           prepare=prepare, destination=incoming, skipped=skipped)
                view = load_inventory(classicua, spoken, staged, incoming, skipped=skipped,
                                      state=state_for_inventory, module=module)
                if selected_hash:
                    built = view.detail(module=module, identity=review[1]["identity"])["built"]
                    if not built or built["text_sha256"] != selected_hash:
                        raise ValueError("manager_candidate_not_built")
                    if module == QUEST_MODULE:
                        verify_quest_zip(incoming, review[1]["identity"], selected_hash)
                summary = view.summary()
        if pins != source_stamps():
            raise ValueError("manager_source_configuration_changed")
        if stage_in is not None and not dry_run:
            (workspace / "promotion.json").write_text(
                json.dumps([baseline, archive_baseline, pins]), encoding="ascii")
        if review_only:
            if stage_in is None:
                promote(db_path, staged, baseline, archive, None, archive_baseline, workspace, False, module)
            return {"module": module, "build": "review_saved"}
        if not dry_run and stage_in is None:
            promote(db_path, staged, baseline, archive, incoming, archive_baseline, workspace,
                    reset or (review is not None and review[0] == "confirm_candidate"), module,
                    expected_sha=result["sha256"])
        return {"module": module, "dry_run": dry_run, "reset_test_data": reset,
                "build": "preview" if dry_run else "success", "artifact": None if dry_run else str(archive),
                "sha256": result["sha256"], "summary": summary, "agent": agent,
                "skipped": [{"id": key, "reason": reason} for key, reason in skipped],
                "inventory": result["import_inventory"]}


class ManagerUI:
    """Keep SQLite environment changes isolated from other server threads."""
    def __init__(self, classicua, spoken, db_path):
        self.classicua, self.spoken = Path(classicua).resolve(), Path(spoken).resolve()
        self.db_path = protected_path(db_path)
        self._lock = Lock()
        self._cached = None
        self._stamp = None
        self._pins = None

    def validate_checkouts(self):
        """Validate Git identity and tracked cleanliness without rebuilding the catalog."""
        from adapters.classicua.source import GitSource, SourceError
        from adapters.spoken import PublicSource

        pin_file = (ROOT / "sources.lock.json").read_bytes()
        pins = json.loads(pin_file)
        try:
            GitSource(self.classicua, pins["classicua"]["revision"])
        except (SourceError, OSError):
            raise ValueError("manager_classicua_checkout_invalid") from None
        try:
            PublicSource(self.spoken, pins["spoken"])
        except (ValueError, OSError):
            raise ValueError("manager_spoken_checkout_invalid") from None
        return (pin_file, (ROOT / "config/translation_sources.json").read_bytes(),
                (ROOT / "tests/stage3_sources.json").read_bytes())

    def action(self, action, payload):
        module = payload.get("module")
        if type(module) is not str or module not in MODULE_DOMAINS:
            raise ValueError("manager_unknown_module")
        mutations = ("confirm_candidate", *REVIEW_ONLY)
        if action == "reimport" or action in mutations:
            review = None if action == "reimport" else (action, {k: v for k, v in payload.items() if k != "module"})
            options = payload if review is None else {"module": module, "confirm": True}
            allowed = {"module", "reset", "dry_run", "confirm"}
            if set(options) - allowed or any(type(options[k]) is not bool for k in set(options) - {"module"}):
                raise ValueError("manager_invalid_options")
            return self._run_worker(action, module, options, review)
        return self._browse(action, module, payload)

    def _run_worker(self, action, module, options, review):
        from tools.build_ukrainian import DIST

        # The server owns the lock and staging files, even if subprocess.run kills the child.
        with manager_workspace(DIST) as workspace:
            flags = {"reset": "--reset-test-data", "dry_run": "--dry-run", "confirm": "--confirm"}
            try:
                worker = subprocess.run(
                    [sys.executable, str(ROOT / "tools/translation_manager.py"), "reimport", "--json",
                     "--module", module, "--classicua", str(self.classicua), "--spoken",
                     str(self.spoken), "--db", str(self.db_path), "--stage-in", str(workspace.resolve()),
                     *(flag for key, flag in flags.items() if options.get(key)), *(("--review-stdin",) if review else ())],
                    cwd=ROOT, capture_output=True, check=False, timeout=MANAGER_WORKER_TIMEOUT_SECONDS,
                    input=json.dumps(review).encode("utf-8") if review else None)
            except subprocess.TimeoutExpired:
                raise ValueError("manager_reimport_timed_out_check_build") from None
            except OSError:
                raise ValueError("manager_reimport_worker_unavailable") from None
            if worker.returncode < 0:
                raise ValueError("manager_reimport_worker_terminated")
            if not worker.stdout.strip():
                raise ValueError("manager_reimport_worker_empty_response")
            try:
                result = json.loads(worker.stdout)
            except (ValueError, RecursionError):
                raise ValueError("manager_reimport_worker_invalid_response") from None
            if not isinstance(result, dict):
                raise ValueError("manager_reimport_worker_invalid_response")
            if worker.returncode != 0:
                reason = result.get("error")
                raise ValueError(reason if isinstance(reason, str) and reason in WORKER_ERRORS
                                 else "manager_reimport_failed")
            review_only = action in REVIEW_ONLY
            dry_run = options.get("dry_run", False)
            expected = "preview" if dry_run else "success"
            if review_only:
                if result != {"module": module, "build": "review_saved"}:
                    raise ValueError("manager_reimport_worker_invalid_response")
            elif (result.get("build") != expected or result.get("module") != module
                    or not all(isinstance(result.get(key), dict) for key in ("summary", "agent"))
                    or not (dry_run or isinstance(result.get("sha256"), str))
                    or not isinstance(result.get("skipped"), list)):
                raise ValueError("manager_reimport_worker_invalid_response")
            if not dry_run:
                self._promote_worker_result(workspace, module, action, options.get("reset", False), result)
            return result

    def _promote_worker_result(self, workspace, module, action, reset, result):
        try:
            baseline, archive_baseline, pins = json.loads(
                (workspace / "promotion.json").read_text(encoding="ascii"))
            archive_baseline = tuple(archive_baseline)
        except (OSError, ValueError, TypeError):
            raise ValueError("manager_reimport_worker_invalid_response") from None
        if pins != source_stamps():
            raise ValueError("manager_source_configuration_changed")
        review_only = action in REVIEW_ONLY
        try:
            promote(self.db_path, workspace / "translations.sqlite3", baseline, ARCHIVES[module],
                    None if review_only else staged_zip(workspace), archive_baseline, workspace,
                    reset or action == "confirm_candidate", module,
                    expected_sha=None if review_only else result["sha256"])
        except (ValueError, OSError, RuntimeError, sqlite3.Error) as error:
            reason = str(error)
            raise ValueError(reason if reason in WORKER_ERRORS else "manager_reimport_failed") from None

    def _browse(self, action, module, payload):
        from tools.manager_inventory import load_inventory

        if action not in ("list", "detail", "stats"):
            raise ValueError("manager_invalid_action")
        allowed = ({"module", "query", "kind", "filter_by", "status", "offset", "limit"}
                   if action == "list" else {"module", "identity"} if action == "detail" else {"module"})
        if set(payload) - allowed:
            raise ValueError("manager_invalid_options")

        def stamp():
            paths = (self.db_path, ARCHIVES[module])
            def stat(path):
                try:
                    result = path.stat()
                except FileNotFoundError:
                    return None
                return result.st_ino, result.st_mtime_ns, result.st_size
            return tuple(stat(path) for path in paths)

        with self._lock:
            pins = self.validate_checkouts()
            before = (module, stamp())
            if self._cached is None or pins != self._pins or self._stamp != before:
                view = load_inventory(self.classicua, self.spoken, self.db_path, ARCHIVES[module], module=module)
                if self.validate_checkouts() != pins:
                    raise ValueError("manager_source_configuration_changed")
                after = (module, stamp())
                if before != after:
                    # First access can initialize SQLite or migrate a legacy ledger.
                    view = load_inventory(self.classicua, self.spoken, self.db_path, ARCHIVES[module], module=module)
                    if after != (module, stamp()) or self.validate_checkouts() != pins:
                        raise ValueError("manager_state_changed_retry_reimport")
                    before = after
                self._cached = view
                self._pins = pins
                self._stamp = before
            view = self._cached
        if action == "stats":
            return {"module": module, "summary": view.summary(), "build": view.build}
        return view.page(**payload) if action == "list" else view.detail(**payload)


def main(argv=None):
    from tools.review_ui_server import _reason

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("reimport",))
    parser.add_argument("--module", choices=tuple(MODULE_DOMAINS), default=MODULE)
    parser.add_argument("--classicua", type=Path, required=True)
    parser.add_argument("--spoken", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=os.environ.get(DB_ENV) or default_db_path())
    parser.add_argument("--reset-test-data", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--review-stdin", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--stage-in", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        review = None
        if args.review_stdin:
            review = strict_json(sys.stdin.buffer.read(262145))
            if (type(review) is not list or len(review) != 2
                    or review[0] not in ("confirm_candidate", *REVIEW_ONLY)
                    or type(review[1]) is not dict):
                raise ValueError("manager_invalid_review_request")
        result = reimport(args.classicua, args.spoken, args.db, module=args.module,
                          reset=args.reset_test_data, dry_run=args.dry_run, confirm=args.confirm, review=review,
                          stage_in=args.stage_in)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, sqlite3.Error,
            subprocess.SubprocessError) as error:
        reason = _reason(error)
        if args.json:
            print(json.dumps({"build": "failed", "error": reason}))
        else:
            print("Reimport failed:", reason, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{args.module} · {result['build']}")
        for domain in (MODULE_DOMAINS[args.module],):
            row = result["summary"][domain]
            print(f"{domain}: {row['included']}/{row['total']} in ZIP, "
                  f"{row['recorded']} backed by DB imports, {row['missing']} missing, "
                  f"{row['conflicts']} candidate conflicts, "
                  f"{row['multiple_originals']} with multiple verified originals, "
                  f"{row['pending_review']} pending review")
            print("  Not in ZIP by status:", row["not_included_by_status"])
            print("  Mapping:", row["mapping_states"], "· translation:", row["translation_states"])
            print("  Import:", row["import_states"], "· in a review queue:", row["in_review_queue"])
            print("  Agent warnings:", row["agent_warnings"],
                  "· unverified alternative matches:", row["unverified_alternatives"])
        print("Gossip serialized units:", result["summary"]["gossip_archive_units"])
        print("Agent import: eligible", result["agent"]["eligible"],
              "· skipped", result["agent"]["skipped"])
        reasons = result["skipped"] + result["agent"]["reasons"]
        for entry in reasons:
            print(f"  {entry.get('id') or entry.get('candidate_id')} · {entry['reason']}")
        if result["artifact"]:
            print("ZIP:", result["artifact"])
        print("SHA-256:", result["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
