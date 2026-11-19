"""Import provenance tests: distinct stages, no double counts, source fidelity."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from adapters.import_statistics import (
    CATEGORIES, recorded_rows, report, store_successful_build,
    latest_successful_build, read_recorded_imports, _validate_build_rows,
)
from adapters.sqlite_translation_store import enable_sqlite, connection
from adapters.source_revision_store import SourceReviewStore, CHECKS
from tools.gossip_translation_review import GossipReviews, discover_groups
from tools.import_build_inventory import collect_build_rows
from tools.source_revision_review import gossip_contexts

SPOKEN_REV = "a" * 40
CLASSICUA_REV = "b" * 40
SHA64 = "c" * 64


class ImportStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / "build"
        self.build.mkdir()
        self.db = self.root / "data/translations.sqlite3"

    def test_snapshot_source_and_entity_counts_are_not_cumulative(self):
        rows = [
            {"domain": "quests", "unit": "42:accept", "entity": "42",
             "source": "classicua", "route": "machine_1to1"},
            {"domain": "quests", "unit": "42:progress", "entity": "42",
             "source": "manual", "route": "reviewed"},
            {"domain": "gossip", "unit": "npc:77:55", "entity": "77",
             "source": "another", "route": "source_selected"},
            {"domain": "gossip", "unit": "npc:77:56", "entity": "77",
             "source": "classicua", "route": "pinned_source"},
            {"domain": "gossip_common", "unit": "common:77", "entity": "common",
             "source": "classicua", "route": "pinned_source"},
            {"domain": "gossip_titles", "unit": "title:horde:42", "entity": "42",
             "source": "classicua", "route": "pinned_source"},
        ]
        first = store_successful_build(self.db, artifact_sha256=SHA64,
             spoken_revision=SPOKEN_REV, classicua_revision=CLASSICUA_REV, rows=rows)
        self.assertEqual(first["total_text_records"], 6)
        self.assertEqual(first["categories"]["quests"], 2)
        self.assertEqual(first["categories"]["gossip"], 2)
        self.assertEqual(first["categories"]["gossip_common"], 1)
        self.assertEqual(first["categories"]["places"], 0)
        self.assertEqual(first["categories"]["readables"], 0)
        quest_manual = next(r for r in first["rows"] if r["source"] == "manual")
        self.assertEqual(quest_manual["unique_entities"], 1)
        again = store_successful_build(self.db, artifact_sha256=SHA64,
             spoken_revision=SPOKEN_REV, classicua_revision=CLASSICUA_REV,
             rows=list(reversed(rows)))
        self.assertFalse(again["new_snapshot"])
        self.assertEqual(first["snapshot_id"], again["snapshot_id"])
        latest = latest_successful_build(self.db)
        self.assertEqual(latest["total_text_records"], 6)
        changed = [dict(row) for row in rows]
        changed[2]["source"] = "classicua"
        third = store_successful_build(self.db, artifact_sha256=SHA64,
             spoken_revision=SPOKEN_REV, classicua_revision=CLASSICUA_REV, rows=changed)
        self.assertTrue(third["new_snapshot"])
        self.assertNotEqual(first["snapshot_id"], third["snapshot_id"])
        self.assertEqual(latest_successful_build(self.db)["snapshot_id"], third["snapshot_id"])
        with connection(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM build_import_snapshots").fetchone()[0], 2)

    def test_duplicate_packed_text_fails_closed(self):
        row = {"domain": "gossip", "unit": "npc:77:55", "entity": "77",
               "source": "another", "route": "source_selected"}
        with self.assertRaisesRegex(ValueError, "duplicate_build_inventory_unit"):
            store_successful_build(self.db, artifact_sha256=SHA64,
                spoken_revision=SPOKEN_REV, classicua_revision=CLASSICUA_REV,
                rows=[row, dict(row)])
        with self.assertRaisesRegex(ValueError, "invalid_build_inventory_row"):
            _validate_build_rows([{**row, "domain": "unknown"}])
        self.assertIsNone(latest_successful_build(self.db))

    def test_inert_review_imports_do_not_count_pending_drafts(self):
        corpus = [{"source": "gossip", "npcType": "creature", "npcId": 88,
                   "npcName": "Synthetic", "originalText": "Hello traveler."}]
        groups, _ = discover_groups(corpus, {"byNpc": {}, "common": {}},
                                    SPOKEN_REV, CLASSICUA_REV)
        with enable_sqlite(self.db):
            local = GossipReviews(groups, SPOKEN_REV, CLASSICUA_REV,
                    self.build / "gossip-translation-reviews.json", self.build)
            base = {k: groups[0][k] for k in
                    ("group_id", "english_sha256", "context_sha256")}
            local.propose([{**base, "ukrainian_text": "Вітаю!"}], "own_translator")
            result = read_recorded_imports(self.db)
            self.assertEqual(result["recorded_imports"]["total_text_records"], 0)
            version = local.file.data["versions"][0]
            local.decide(version["id"], "approved", "human",
                 {k: True for k in ("text", "grammar", "ai", "rights", "all_contexts")})
            self.assertEqual(read_recorded_imports(self.db)["recorded_imports"]["total_text_records"], 0)
            local.import_approved()
            result = report(self.db)
            self.assertEqual(result["recorded_imports"]["total_text_records"], 1)
            self.assertEqual(result["recorded_imports"]["rows"][0]["source"], "own_translator")
            self.assertEqual(result["recorded_imports"]["categories"]["gossip"], 1)
            self.assertIsNone(result["latest_successful_build"])
            local.decide(version["id"], "rejected", "human",
                 {k: False for k in ("text", "grammar", "ai", "rights", "all_contexts")})
            self.assertEqual(report(self.db)["recorded_imports"]["total_text_records"], 0)

    def test_source_selection_separate_until_built(self):
        corpus = [{"source": "gossip", "npcType": "creature", "npcId": 42,
                   "npcName": "Synthetic", "originalText": "Hello traveler."}]
        trusted = gossip_contexts(corpus)
        key, proof = next(iter(trusted.items()))
        source = SourceReviewStore(self.db)
        source.ingest({"provider": "another", "revision": "d" * 40,
                       "records": [{"domain": "gossip", "target_id": key[1],
                                   "english_sha256": proof["english_sha256"],
                                   "context_sha256": proof["context_sha256"],
                                   "ukrainian_text": "Вітаю, мандрівнику!",
                                   "source_ref": "another:synthetic"}]}, trusted)
        version = source.candidates()[0]
        source.decide(version["id"], "approved", "human",
                      {k: True for k in CHECKS}, trusted)
        source.activate(version["id"], "human", trusted)
        report_data = report(self.db)
        self.assertEqual(report_data["recorded_imports"]["total_text_records"], 0)
        self.assertEqual(report_data["selected_not_necessarily_built"]["total_text_records"], 1)
        self.assertIsNone(report_data["latest_successful_build"])
        source.clear_selection("gossip", key[1], "human", trusted)
        self.assertEqual(report(self.db)["selected_not_necessarily_built"]["total_text_records"], 0)

    def test_selected_source_is_attributed_to_exact_gossip_npc_only(self):
        empty = {"versions": [], "imports": []}
        state = SimpleNamespace(
            machine_imports=SimpleNamespace(file=SimpleNamespace(data=empty)),
            translations=SimpleNamespace(file=SimpleNamespace(data=empty)))
        rows = collect_build_rows(
            state, {}, {"common": {55: "Звичайний fallback"},
                        "byNpc": {42: {321: "Альтернативний переклад"},
                                  43: {322: "ClassicUA переклад"}}},
            {}, {}, [{"target_id": "gossip:42:321", "provider": "another"}],
            [], {}, self.db)
        by_unit = {r["unit"]: r for r in rows}
        self.assertEqual(by_unit["npc:42:321"]["source"], "another")
        self.assertEqual(by_unit["npc:42:321"]["route"], "source_selected")
        self.assertEqual(by_unit["npc:43:322"]["source"], "classicua")
        self.assertEqual(by_unit["common:55"]["domain"], "gossip_common")

    def test_selected_source_is_attributed_to_exact_quest_moment_only(self):
        from hashlib import sha256
        text = "Альтернативний переклад"
        empty = {"versions": [], "imports": []}
        state = SimpleNamespace(
            machine_imports=SimpleNamespace(file=SimpleNamespace(data=empty)),
            translations=SimpleNamespace(file=SimpleNamespace(data=empty)))
        rows = collect_build_rows(
            state, {42: {"accept": {"text": "Альтернативний переклад",
                                   "reviewed": True}}},
            {"common": {}, "byNpc": {}}, {}, {}, [],
            [{"target_id": "q:42:accept", "provider": "another",
              "ukrainian_text": "Альтернативний переклад"}], {}, self.db)
        self.assertEqual(rows, [{
            "domain": "quests", "unit": "42:accept", "entity": "42",
            "source": "another", "route": "source_selected",
            "text_sha256": sha256(text.encode()).hexdigest()}])

    def test_build_provenance_uses_only_displayed_quest_events(self):
        machine = {"versions": [{
            "id": "m", "target_id": "q:42:accept", "text": "Прийняти"
        }], "imports": [{"target_id": "q:42:accept", "version_id": "m"}]}
        reviewed = {"versions": [{
            "id": "h", "target_id": "q:42:progress", "text": "Продовжити",
            "kind": "manual", "provenance": [{"provider": "classicua"}]
        }], "imports": [{"target_id": "q:42:progress", "version_id": "h"}]}
        state = SimpleNamespace(machine_imports=SimpleNamespace(
            file=SimpleNamespace(data=machine)),
            translations=SimpleNamespace(file=SimpleNamespace(data=reviewed)))
        preview = {42: {
            "accept": {"text": "Прийняти", "reviewed": False},
            "progress": {"text": "Продовжити", "reviewed": True},
            "complete": {"text": "Некоректний варіант", "reviewed": False}}}
        with self.assertRaisesRegex(ValueError, "build_import_quest_provenance_missing"):
            collect_build_rows(state, preview, {"common": {}, "byNpc": {}}, {},
                               {}, [], [], {}, self.db)
        preview[42].pop("complete")
        rows = collect_build_rows(state, preview,
                {"common": {321: "X"}, "byNpc": {77: {55: "Y"}}},
                {"horde": {42: "Назва"}, "alliance": {}},
                {}, [], [], {}, self.db)
        self.assertEqual(len(rows), 5)
        self.assertEqual(sum(r["domain"] == "quests" for r in rows), 2)
        self.assertEqual(sum(r["source"] == "manual" for r in rows), 1)
        self.assertEqual(sum(r["domain"] == "gossip_common" for r in rows), 1)
        self.assertEqual(sum(r["domain"] == "gossip_titles" for r in rows), 1)


if __name__ == "__main__":
    unittest.main()
