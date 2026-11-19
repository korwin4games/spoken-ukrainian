"""SQLite persistence, legacy import, review-memory reuse and transactional safety."""
import json
from contextlib import closing, redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest
from unittest.mock import patch

from adapters.local_review_store import LocalFile
from adapters.sqlite_translation_store import (
    enable_sqlite, default_db_path, protected_path, backup_database,
    memory_suggestions, connection, _memory_versions,
)
from tools.gossip_translation_review import GossipReviews, discover_groups, create_batches
from tools.gossip_coverage import classicua_hash
from tools.translation_db import main as translation_db_main

A = "a" * 40
B = "b" * 40


class SQLiteStorageTests(unittest.TestCase):
    def test_opening_current_wal_database_preserves_filesystem_and_sqlite_generation(self):
        with connection(self.db) as db:
            db.execute("PRAGMA journal_mode=WAL")
        with closing(sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True)) as observer:
            version = observer.execute("PRAGMA data_version").fetchone()[0]
            stamp = self.db.stat()
            with patch("adapters.sqlite_translation_store._initialize_schema") as initialize:
                with connection(self.db) as db:
                    self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                initialize.assert_not_called()
            self.assertEqual(observer.execute("PRAGMA data_version").fetchone()[0], version)
            self.assertEqual(self.db.stat().st_ctime_ns, stamp.st_ctime_ns)
            self.assertEqual(self.db.stat().st_mtime_ns, stamp.st_mtime_ns)

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.build = root / "build"
        self.db = root / "data" / "translations.sqlite3"
        self.gossip_path = self.build / "gossip-translation-reviews.json"

    @staticmethod
    def check_document(data):
        if set(data) != {"schema_version", "versions", "imports"}:
            raise ValueError("invalid_synthetic_ledger")
        if data["schema_version"] != 1 or type(data["versions"]) is not list:
            raise ValueError("invalid_synthetic_ledger")
        return dict(data)

    def test_migrate_existing_legacy_json_without_erasing_old_file(self):
        self.build.mkdir()
        legacy = {"schema_version": 1, "versions": [{"id": "synthetic"}], "imports": []}
        legacy_path = self.build / "stage4b-decisions.json"
        legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
        original = legacy_path.read_bytes()
        with enable_sqlite(self.db):
            store = LocalFile(legacy_path, self.build, legacy, self.check_document)
            self.assertEqual(store.data, legacy)
            self.assertEqual(legacy_path.read_bytes(), original)
            store.save({"schema_version": 1, "versions": [
                {"id": "synthetic"}, {"id": "new"}], "imports": []})
            # JSON is retained as an untouched migration backup.
            self.assertEqual(legacy_path.read_bytes(), original)
            restarted = LocalFile(legacy_path, self.build, legacy, self.check_document)
            self.assertEqual(len(restarted.data["versions"]), 2)
            restarted.save({"schema_version": 1,
                            "versions": [{"id": "synthetic"}, {"id": "new"}, {"id": "newer"}],
                            "imports": []})
            self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(list(self.db.parent.glob("*.sqlite3"))), 1)
            # A stale writer must NOT overwrite a later transaction.
            with self.assertRaisesRegex(ValueError, "local_review_conflict_restart_and_reload"):
                store.save({"schema_version": 1, "versions": [], "imports": []})

    def test_multiple_ledgers_use_one_db_without_name_overlap(self):
        self.build.mkdir()
        empty = {"schema_version": 1, "versions": [], "imports": []}
        with enable_sqlite(self.db):
            g = LocalFile(self.build / "stage4b-decisions.json", self.build, empty, self.check_document)
            q = LocalFile(self.build / "stage3-ui-reviews.json",
                          self.build, empty, self.check_document)
            g.save({"schema_version": 1, "versions": [{"id": "g"}], "imports": []})
            q.save({"schema_version": 1, "versions": [{"id": "q"}], "imports": []})
            with connection(self.db) as db:
                rows = db.execute("SELECT ledger_name, revision FROM ledger_documents").fetchall()
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(rev == 2 for _, rev in rows))

    def test_gossip_proposal_approval_persists_and_reuses_by_english_sha(self):
        known = {"common": {}, "byNpc": {}}
        corpus = [{"source": "gossip", "npcType": "creature", "npcId": 12,
                   "npcName": "Synthetic A", "originalText": "Hello traveler."}]
        groups, _ = discover_groups(corpus, known, A, B)
        self.build.mkdir()
        with enable_sqlite(self.db):
            reviews = GossipReviews(groups, A, B, self.gossip_path, self.build)
            proposal = {k: groups[0][k] for k in
                        ("group_id", "english_sha256", "context_sha256")}
            proposal["ukrainian_text"] = "Вітаю, мандрівнику!"
            reviews.propose([proposal], "manual")
            row = reviews.file.data["versions"][0]
            self.assertEqual(memory_suggestions(self.db, "gossip",
                             [groups[0]["english_sha256"]]),
                             {groups[0]["english_sha256"]: "Вітаю, мандрівнику!"})
            reviews.decide(row["id"], "approved", "human",
                           {k: True for k in ("text", "grammar", "ai", "rights", "all_contexts")})
            reviews.import_approved()
            restarted = GossipReviews(groups, A, B, self.gossip_path, self.build)
            self.assertEqual(len(restarted.file.data["versions"]), 1)
            self.assertEqual(len(restarted.file.data["imports"]), 1)
            self.assertEqual(restarted.imported_by_npc(known)[12][
                classicua_hash("Hello traveler.")], "Вітаю, мандрівнику!")
            destination = self.db.parent / "review-history.sqlite3"
            before = self.db.read_bytes()
            backup_database(self.db, destination)
            self.assertEqual(self.db.read_bytes(), before)
            with sqlite3.connect(self.db) as source, sqlite3.connect(destination) as target:
                self.assertEqual(target.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
                self.assertEqual(list(source.iterdump()), list(target.iterdump()))
            with enable_sqlite(destination):
                restored = GossipReviews(groups, A, B, self.gossip_path, self.build)
                self.assertEqual(restored.file.data, restarted.file.data)
                self.assertEqual(restored.imported_by_npc(known), restarted.imported_by_npc(known))
            # New NPC context changes the proof: old translation stays in DB,
            # reappears only as a pending DRAFT, with no inherited approval.
            rows = corpus + [{"source": "gossip", "npcType": "creature",
                              "npcId": 15, "npcName": "Synthetic B",
                              "originalText": "Hello traveler."}]
            new_groups, _ = discover_groups(rows, known, A, B)
            changed = GossipReviews(new_groups, A, B, self.gossip_path, self.build)
            self.assertFalse(changed.current(row))
            with self.assertRaisesRegex(ValueError, "stale_gossip_import"):
                changed.imported_by_npc(known)
            folder = self.build / "batches"
            create_batches(new_groups, A, B, folder, 40)
            batch = json.loads((folder / "batch-0001.json").read_text(encoding="utf-8"))
            self.assertEqual(batch["entries"][0]["ukrainian_text"], "Вітаю, мандрівнику!")
            # Never erase existing text if queue regenerated.
            create_batches(new_groups, A, B, folder, 40)
            batch2 = json.loads((folder / "batch-0001.json").read_text(encoding="utf-8"))
            self.assertEqual(batch2, batch)

    def test_backup_is_complete_and_never_overwrites(self):
        self.build.mkdir()
        empty = {"schema_version": 1, "versions": [], "imports": []}
        with enable_sqlite(self.db):
            store = LocalFile(self.build / "stage4b-decisions.json", self.build, empty, self.check_document)
            store.save({"schema_version": 1, "versions": [{"id": "saved"}], "imports": []})
        destination = self.db.parent / "backups" / "backup.sqlite3"
        backup_database(self.db, destination)
        with sqlite3.connect(destination) as db:
            data = db.execute("SELECT payload FROM ledger_documents").fetchone()[0]
        self.assertEqual(json.loads(data)["versions"], [{"id": "saved"}])
        with self.assertRaisesRegex(ValueError, "sqlite_backup_target_already_exists"):
            backup_database(self.db, destination)

    def test_malformed_legacy_ledger_does_not_create_migrated_row(self):
        self.build.mkdir()
        (self.build / "stage4b-decisions.json").write_text('{"versions":[],"versions":[]}', encoding="utf-8")
        with enable_sqlite(self.db):
            with self.assertRaises(ValueError):
                LocalFile(self.build / "stage4b-decisions.json", self.build, {}, self.check_document)
            with connection(self.db) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM ledger_documents").fetchone()[0], 0)

    def test_translation_memory_large_history_without_unbounded_placeholders(self):
        # Source histories can contain thousands of retained review versions.
        with connection(self.db) as db:
            db.execute("BEGIN IMMEDIATE")
            revisions = [{"id": f"v{i:06d}", "english_sha256": f"h{i:06d}",
                          "context_sha256": f"c{i:06d}", "provider": "manual",
                          "group_id": f"g{i:06d}", "text": f"Синтетика {i}",
                          "decisions": []} for i in range(1800)]
            _memory_versions(db, "gossip-translation-reviews.json",
                             {"versions": revisions})
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM translation_memory").fetchone()[0], 1800)
            # Re-indexing with fewer rows removes only obsolete entries.
            _memory_versions(db, "gossip-translation-reviews.json",
                             {"versions": revisions[:450]})
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM translation_memory").fetchone()[0], 450)
            db.commit()

    def test_existing_backup_is_never_overwritten(self):
        with connection(self.db):
            pass
        destination = self.db.parent / "backups" / "existing.sqlite3"
        destination.parent.mkdir()
        destination.write_bytes(b"unrelated pre-existing backup")
        with self.assertRaisesRegex(ValueError, "sqlite_backup_target_already_exists"):
            backup_database(self.db, destination)
        self.assertEqual(destination.read_bytes(), b"unrelated pre-existing backup")

    def run_cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = translation_db_main(list(args))
        return result, stdout.getvalue(), stderr.getvalue()

    def test_missing_backup_source_is_explicit_and_creates_nothing(self):
        destination = Path(self.tmp.name) / "backups" / "copy.sqlite3"
        with self.assertRaisesRegex(ValueError, "sqlite_backup_source_missing"):
            backup_database(self.db, destination)
        result, _, error = self.run_cli("backup", "--db", str(self.db), "--output", str(destination))
        self.assertEqual(result, 1)
        for text in ("sqlite_backup_source_missing", "does not exist", "init", "restore",
                     str(self.db), str(destination)):
            self.assertIn(text, error)
        self.assertFalse(self.db.parent.exists())
        self.assertFalse(destination.parent.exists())

    def test_backup_rejects_identical_and_normalized_paths(self):
        with connection(self.db):
            pass
        before = self.db.read_bytes()
        child = self.db.parent / "child"
        child.mkdir()
        for destination in (self.db, child / ".." / self.db.name):
            with self.subTest(destination=destination):
                with self.assertRaisesRegex(ValueError, "sqlite_backup_same_path"):
                    backup_database(self.db, destination)
                result, _, error = self.run_cli("backup", "--db", str(self.db),
                                                "--output", str(destination))
                self.assertEqual(result, 1)
                self.assertIn("Choose a different --output", error)
        self.assertEqual(self.db.read_bytes(), before)

    def test_backup_symlinks_are_rejected_before_resolution(self):
        with connection(self.db):
            pass
        root = Path(self.tmp.name)
        link = root / "link.sqlite3"
        link.symlink_to(self.db)
        dangling = root / "dangling.sqlite3"
        dangling.symlink_to(root / "absent.sqlite3")
        parent_link = root / "linked-data"
        parent_link.symlink_to(self.db.parent, target_is_directory=True)
        output = root / "copy.sqlite3"
        for source, destination in ((link, output), (dangling, output),
                                    (self.db, link), (self.db, dangling),
                                    (parent_link / self.db.name, output),
                                    (self.db, parent_link / "copy.sqlite3")):
            with self.subTest(source=source, destination=destination):
                with self.assertRaisesRegex(ValueError, "sqlite_translation_db_symlink"):
                    backup_database(source, destination)
                result, _, error = self.run_cli("backup", "--db", str(source),
                                                "--output", str(destination))
                self.assertEqual(result, 1)
                self.assertIn("without symlinks", error)
        self.assertFalse(output.exists())
        self.assertFalse((root / "absent.sqlite3").exists())

    def test_backup_does_not_recreate_source_removed_after_validation(self):
        with connection(self.db):
            pass
        destination = self.db.parent / "copy.sqlite3"
        connect = sqlite3.connect

        def remove_source_then_connect(*args, **kwargs):
            self.db.unlink()
            return connect(*args, **kwargs)

        with patch("adapters.sqlite_translation_store.sqlite3.connect", remove_source_then_connect):
            with self.assertRaises(sqlite3.OperationalError):
                backup_database(self.db, destination)
        self.assertFalse(self.db.exists())
        self.assertFalse(destination.exists())

    def test_backup_copies_existing_schema_without_initializing_or_migrating(self):
        self.db.parent.mkdir()
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE existing_history (decision TEXT)")
            db.execute("INSERT INTO existing_history VALUES ('synthetic approval')")
        before = self.db.read_bytes()
        destination = self.db.parent / "copy.sqlite3"
        backup_database(self.db, destination)
        self.assertEqual(self.db.read_bytes(), before)
        with sqlite3.connect(destination) as db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),
                             [("existing_history",)])
            self.assertEqual(db.execute("SELECT * FROM existing_history").fetchall(),
                             [("synthetic approval",)])

    def test_cli_explicit_init_status_backup_and_existing_destination(self):
        result, output, error = self.run_cli("status", "--db", str(self.db))
        self.assertEqual((result, error), (0, ""))
        self.assertFalse(json.loads(output)["database_exists"])
        self.assertFalse(self.db.parent.exists())
        self.assertEqual(self.run_cli("init", "--db", str(self.db))[0], 0)
        before = self.db.read_bytes()
        self.assertEqual(self.run_cli("status", "--db", str(self.db))[0], 0)
        self.assertEqual(self.db.read_bytes(), before)
        destination = self.db.parent / "copy.sqlite3"
        result, output, error = self.run_cli("backup", "--db", str(self.db), "--output", str(destination))
        self.assertEqual((result, error), (0, ""))
        self.assertIn(str(destination), output)
        backup_bytes = destination.read_bytes()
        result, _, error = self.run_cli("backup", "--db", str(self.db), "--output", str(destination))
        self.assertEqual(result, 1)
        self.assertIn("Choose an unused --output", error)
        self.assertIn(str(destination), error)
        self.assertEqual(destination.read_bytes(), backup_bytes)
        self.assertEqual(self.db.read_bytes(), before)

    def test_backup_diagnostics_omit_raw_errors_and_escape_path_controls(self):
        destination = self.db.parent / "copy\n.sqlite3"
        with patch("tools.translation_db.backup_database",
                   side_effect=sqlite3.DatabaseError("private translation body")):
            result, _, error = self.run_cli("backup", "--db", str(self.db),
                                            "--output", str(destination))
        self.assertEqual(result, 1)
        self.assertNotIn("private translation body", error)
        self.assertIn("sqlite_store_error: DatabaseError", error)
        self.assertIn(json.dumps(str(destination)), error)
        self.assertIn("readable SQLite database", error)

    def test_path_and_context_restore(self):
        original = os.environ.get("SPOKEN_TRANSLATION_DB")
        with enable_sqlite(self.db):
            self.assertEqual(Path(os.environ["SPOKEN_TRANSLATION_DB"]), self.db)
        self.assertEqual(os.environ.get("SPOKEN_TRANSLATION_DB"), original)
        bad = Path(self.tmp.name) / "db-link.sqlite3"
        bad.symlink_to(self.db)
        with self.assertRaisesRegex(ValueError, "sqlite_translation_db_symlink"):
            protected_path(bad)


if __name__ == "__main__":
    unittest.main()
