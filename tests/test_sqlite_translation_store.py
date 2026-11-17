"""SQLite persistence, legacy import, review-memory reuse and transactional safety."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from adapters.local_review_store import LocalFile
from adapters.sqlite_translation_store import (
    enable_sqlite, default_db_path, protected_path, backup_database,
    memory_suggestions, connection,
)
from tools.gossip_translation_review import GossipReviews, discover_groups, create_batches
from tools.gossip_coverage import classicua_hash

A = "a" * 40
B = "b" * 40


class SQLiteStorageTests(unittest.TestCase):
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
                             [groups[0]["english_sha256"]]), {})
            reviews.decide(row["id"], "approved", "human",
                           {k: True for k in ("text", "grammar", "ai", "rights", "all_contexts")})
            reviews.import_approved()
            restarted = GossipReviews(groups, A, B, self.gossip_path, self.build)
            self.assertEqual(len(restarted.file.data["versions"]), 1)
            self.assertEqual(len(restarted.file.data["imports"]), 1)
            self.assertEqual(restarted.imported_by_npc(known)[12][
                classicua_hash("Hello traveler.")], "Вітаю, мандрівнику!")
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
