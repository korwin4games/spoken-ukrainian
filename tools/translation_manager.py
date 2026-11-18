#!/usr/bin/env python3
"""Browse and rebuild the private Quest and Gossip module."""
import argparse
from contextlib import contextmanager
import fcntl
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

MODULE = "Spoken_Quests_UA"
DOMAINS = "('quest','gossip')"
MODULE_LEDGERS = (
    "stage4b-decisions.json", "stage3-ui-reviews.json", "translation-reviews.json",
    "machine-one-to-one.json", "gossip-translation-reviews.json", "gossip-machine-one-to-one.json",
)
TABLE_SCOPES = {
    "ledger_documents": "ledger_name IN (" + ",".join(repr(s) for s in MODULE_LEDGERS) + ")",
    "translation_memory": f"domain IN {DOMAINS}",
    "source_candidate_decisions": f"candidate_id IN (SELECT id FROM source_candidates WHERE domain IN {DOMAINS})",
    "source_active_selections": f"domain IN {DOMAINS}",
    "source_selection_events": f"domain IN {DOMAINS}",
    "agent_assessments": f"json_extract(payload, '$.candidate.domain') IN {DOMAINS}",
}
AGENT_SCOPE = "(SELECT candidate_id FROM agent_assessments WHERE " + TABLE_SCOPES["agent_assessments"] + ")"
TABLE_SCOPES.update({name: "candidate_id IN " + AGENT_SCOPE
                     for name in ("agent_imports", "agent_stale_evidence")})


def reset_test_state(db):
    """Discard only scoped test decisions and imports in the staged database."""
    from adapters.auto_one_to_one import EMPTY as quest_machine
    from adapters.gossip_machine import EMPTY as gossip_machine
    from adapters.mapping import review_file
    from adapters.review_workbench import empty_decisions
    from adapters.translation_approvals import EMPTY as quest_review
    from tools.gossip_translation_review import EMPTY as gossip_review

    assert set(MODULE_LEDGERS) <= LEDGER_NAMES
    for table in reversed(TABLE_SCOPES):
        if table != "ledger_documents":
            db.execute(f"DELETE FROM {table} WHERE {TABLE_SCOPES[table]}")
    # Seed documents rather than deleting them: legacy JSON remains untouched
    # and cannot silently repopulate this test scope during the fresh build.
    db.executemany("""INSERT INTO ledger_documents(ledger_name, payload, revision)
        VALUES (?, ?, 1) ON CONFLICT(ledger_name) DO UPDATE SET
        payload=excluded.payload, revision=revision+1, updated_at=CURRENT_TIMESTAMP""",
        [(name, json.dumps(value, sort_keys=True)) for name, value in zip(MODULE_LEDGERS,
            (empty_decisions(), review_file([]), quest_review, quest_machine, gossip_review, gossip_machine))])


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


@contextmanager
def manager_lock(directory):
    if directory.is_symlink():
        raise ValueError("manager_unsafe_workspace")
    directory.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(directory / ".translation-manager.lock", os.O_CREAT | os.O_NOFOLLOW | os.O_RDWR, 0o600)
    with os.fdopen(fd, "rb") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("manager_reimport_already_running") from None
        yield


def promote(db_path, staged, baseline, archive, incoming, archive_baseline, workspace, reset):
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
            for table in reversed(TABLE_SCOPES):
                if not reset and table.startswith("source_"):
                    continue
                db.execute(f"DELETE FROM main.{table} WHERE {TABLE_SCOPES[table]}")
            for table, scope in TABLE_SCOPES.items():
                if not reset and table.startswith("source_"):
                    continue
                # Subqueries in child scopes must see the staged parents.
                stage_scope = scope.replace("FROM agent_assessments", "FROM staged.agent_assessments")
                db.execute(f"INSERT INTO main.{table} SELECT * FROM staged.{table} WHERE {stage_scope}")
            for table in ("build_import_snapshots", "build_import_units"):
                db.execute(f"INSERT OR IGNORE INTO main.{table} SELECT * FROM staged.{table}")
            db.execute("DELETE FROM main.build_import_head")
            db.execute("INSERT INTO main.build_import_head SELECT * FROM staged.build_import_head")
            # Copy to same-filesystem temporary paths so replace is atomic per file.
            digest = file_stamp(incoming)
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


def prepare_import(state, spoken, db_path, skipped):
    from adapters.translation_agent import AGENT, TranslationAgent, assessment_rows
    from tools.build_ukrainian import local_gossip_texts
    from tools.gossip_coverage import read_pinned_corpus
    from tools.gossip_translation_review import GossipReviews, discover_groups
    from tools.translation_agent import evidence

    lines = read_pinned_corpus(spoken, state.inventory.revision)
    groups, _ = discover_groups(lines, local_gossip_texts(state),
                                state.inventory.revision, state.source.revision)
    reviews = GossipReviews(groups, state.inventory.revision, state.source.revision)
    reviews.import_approved(skipped=skipped)
    rows = evidence(state, spoken, db_path, revalidate=False)
    agent = TranslationAgent(db_path, lambda: rows)
    with connection(db_path) as db:
        assessed = {r["candidate"]["id"] for r in assessment_rows(db, latest=True) if r["agent"] == AGENT}
    # A machine-only Quest hint cannot become an agent-eligible mapping.
    ids = [r["id"] for r in rows if r["identity_verified"] and r["rights_evidence"]
           and r["id"] not in assessed]
    for offset in range(0, len(ids), 100):
        agent.run("batch", candidate_ids=ids[offset:offset + 100], limit=100)
    return agent.run("import-verified", confirm=True)


def reimport(classicua, spoken, db_path, *, module=MODULE, reset=False, dry_run=False, confirm=False):
    """The CLI and localhost UI run the same staged operation."""
    from tools.build_ukrainian import ARCHIVE, DIST, build
    from tools.manager_inventory import load_inventory

    if module != MODULE:
        raise ValueError("manager_unknown_module")
    if any(type(v) is not bool for v in (reset, dry_run, confirm)):
        raise ValueError("manager_invalid_options")
    if not dry_run and not confirm:
        raise ValueError("manager_confirmation_required")
    classicua, spoken = Path(classicua).resolve(), Path(spoken).resolve()
    db_path = protected_path(db_path)
    if db_path.suffix not in (".sqlite", ".sqlite3", ".db") or any(
            db_path.resolve().is_relative_to(p) for p in (classicua, spoken, ROOT / "addons")) or (
            db_path.exists() and (not db_path.is_file() or db_path.stat().st_nlink != 1)):
        raise ValueError("manager_unsafe_database_path")
    archive = ARCHIVE
    source_inputs = (ROOT / "sources.lock.json", ROOT / "config/translation_sources.json",
                     ROOT / "tests/stage3_sources.json")
    with manager_lock(DIST), TemporaryDirectory(prefix=".translation-manager-", dir=DIST) as staging:
        workspace = Path(staging)
        staged = workspace / "translations.sqlite3"
        incoming = DIST / (workspace.name + ".zip")
        checksum = incoming.with_suffix(".zip.sha256")
        try:
            if db_path.exists():
                backup_database(db_path, staged)
            archive_baseline = (file_stamp(archive), file_stamp(archive.with_suffix(".zip.sha256")))
            pins = [file_stamp(path) for path in source_inputs]
            with connection(staged) as db:
                baseline = db_stamp(db)
                if reset:
                    db.execute("BEGIN IMMEDIATE")
                    reset_test_state(db)
                    db.commit()
            skipped = []
            with enable_sqlite(staged):
                agent = {}
                state_for_inventory = None
                def prepare(state):
                    nonlocal state_for_inventory
                    state_for_inventory = state
                    agent.update(prepare_import(state, spoken, staged, skipped))
                result = build(classicua, spoken, prepare=prepare, destination=incoming, skipped=skipped)
                view = load_inventory(classicua, spoken, staged, incoming, skipped=skipped,
                                      state=state_for_inventory)
                summary = view.summary()
            if pins != [file_stamp(path) for path in source_inputs]:
                raise ValueError("manager_source_configuration_changed")
            if not dry_run:
                promote(db_path, staged, baseline, archive, incoming, archive_baseline, workspace, reset)
            return {"module": module, "dry_run": dry_run, "reset_test_data": reset,
                    "build": "preview" if dry_run else "success", "artifact": None if dry_run else str(archive),
                    "sha256": result["sha256"], "summary": summary, "agent": agent,
                    "skipped": [{"id": key, "reason": reason} for key, reason in skipped],
                    "inventory": result["import_inventory"]}
        finally:
            incoming.unlink(missing_ok=True)
            checksum.unlink(missing_ok=True)


class ManagerUI:
    """Keep SQLite environment changes isolated from other server threads."""
    def __init__(self, classicua, spoken, db_path):
        self.classicua, self.spoken = Path(classicua).resolve(), Path(spoken).resolve()
        self.db_path = protected_path(db_path)
        self._lock = Lock()
        self._cached = None
        self._stamp = None

    def action(self, action, payload):
        from tools.build_ukrainian import ARCHIVE
        from tools.manager_inventory import load_inventory

        if payload.get("module") != MODULE:
            raise ValueError("manager_unknown_module")
        if action == "reimport":
            allowed = {"module", "reset", "dry_run", "confirm"}
            if set(payload) - allowed or any(type(payload[k]) is not bool for k in set(payload) - {"module"}):
                raise ValueError("manager_invalid_options")
            flags = {"reset": "--reset-test-data", "dry_run": "--dry-run", "confirm": "--confirm"}
            try:
                worker = subprocess.run(
                    [sys.executable, str(ROOT / "tools/translation_manager.py"), "reimport", "--json",
                     "--module", MODULE, "--classicua", str(self.classicua), "--spoken",
                     str(self.spoken), "--db", str(self.db_path),
                     *(flag for key, flag in flags.items() if payload.get(key))],
                    cwd=ROOT, capture_output=True, check=False, timeout=600)
            except subprocess.TimeoutExpired:
                raise ValueError("manager_reimport_timed_out_check_build") from None
            result = json.loads(worker.stdout)
            if worker.returncode != 0:
                raise ValueError(result.get("error", "manager_reimport_failed"))
            return result
        if action not in ("list", "detail"):
            raise ValueError("manager_invalid_action")
        allowed = ({"module", "query", "kind", "filter_by", "status", "offset", "limit"}
                   if action == "list" else {"module", "identity"})
        if set(payload) - allowed:
            raise ValueError("manager_invalid_options")

        def stamp():
            paths = (self.db_path, ARCHIVE, ROOT / "sources.lock.json", ROOT / "config/translation_sources.json")
            return tuple((p.stat().st_ino, p.stat().st_mtime_ns) if p.exists() else None for p in paths)

        with self._lock:
            if self._cached is None or self._stamp != stamp():
                self._cached = load_inventory(self.classicua, self.spoken, self.db_path, ARCHIVE)
                self._stamp = stamp()
            view = self._cached
        return view.page(**payload) if action == "list" else view.detail(**payload)


def main(argv=None):
    from tools.review_ui_server import _reason

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("reimport",))
    parser.add_argument("--module", choices=(MODULE,), default=MODULE)
    parser.add_argument("--classicua", type=Path, required=True)
    parser.add_argument("--spoken", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=os.environ.get(DB_ENV) or default_db_path())
    parser.add_argument("--reset-test-data", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = reimport(args.classicua, args.spoken, args.db, module=args.module,
                          reset=args.reset_test_data, dry_run=args.dry_run, confirm=args.confirm)
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
        print(f"{MODULE} · {result['build']}")
        for domain in ("quest", "gossip"):
            row = result["summary"][domain]
            print(f"{domain}: {row['included']}/{row['total']} in ZIP, "
                  f"{row['recorded']} backed by DB imports, {row['missing']} missing, "
                  f"{row['conflicts']} conflicts, {row['pending_review']} pending review")
            print("  Not in ZIP by status:", row["not_included_by_status"])
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
