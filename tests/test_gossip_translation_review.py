"""Review gate, prioritization, version and source evidence for NPC Gossip."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.gossip_translation_review import (
    GossipReviews, discover_groups, normalized, validate_ledger, create_batches,
)
from tools.gossip_coverage import classicua_hash

A = "a" * 40
B = "b" * 40

def npc(n, text):
    return {"source": "gossip", "npcType": "creature", "npcId": n,
            "npcName": "Synthetic speaker", "originalText": text}

class GossipReviewTests(unittest.TestCase):
    def setup_data(self):
        rows = [npc(42, "Hello  traveler."), npc(42, " Hello traveler. "),
                npc(99, "Hello traveler."), npc(100, "Other wording."),
                npc(101, "Shared known."), npc(102, "NPC known."),
                {"source":"gossip","npcType":"gameobject","npcId":77,
                 "originalText":"Other wording."},
                {"source":"accept","npcType":"creature","npcId":3,
                 "originalText":"Other wording."}]
        known = {"common": {classicua_hash("Shared known."): "Вже є"},
                 "byNpc": {102: {classicua_hash("NPC known."): "Вже є"}}}
        groups, stats = discover_groups(rows, known, A, B)
        return groups, stats, known

    def test_groups_are_deduplicated_and_scoped(self):
        groups, stats, _ = self.setup_data()
        self.assertEqual(stats["untranslated_npc_wordings_queued"], 3)
        self.assertEqual(stats["unique_english_texts_to_translate"], 2)
        self.assertEqual(stats["repeated_occurrences_deduplicated"], 1)
        self.assertEqual(stats["non_npc_rows"], 1)
        self.assertEqual(groups[0]["occurrence_count"], 2)
        self.assertEqual([x["npc_id"] for x in groups[0]["contexts"]], [42, 99])
        self.assertEqual(normalized("  Hello \u00a0 traveler. "), "hello traveler.")

    def test_pending_never_imported_approval_and_explicit_import(self):
        groups, _, existing = self.setup_data()
        with TemporaryDirectory() as d:
            root = Path(d) / "build"
            store = GossipReviews(groups, A, B, root / "reviews.json", root)
            p = {k: groups[0][k] for k in
                 ("group_id", "english_sha256", "context_sha256")}
            p["ukrainian_text"] = "Вітаю, мандрівнику!"
            self.assertEqual(store.propose([p], "own_translator"), 1)
            row = store.file.data["versions"][0]
            self.assertEqual(store.import_approved(), 0)
            self.assertEqual(store.imported_by_npc(existing), {})
            with self.assertRaisesRegex(ValueError, "explicit_gossip_attestation_required"):
                store.decide(row["id"], "approved", "reviewer",
                             {"text": True, "grammar": True, "ai": True, "rights": True,
                              "all_contexts": False})
            checks = {k: True for k in ("text", "grammar", "ai", "rights", "all_contexts")}
            self.assertEqual(store.decide(row["id"], "approved", "reviewer", checks), "approved")
            self.assertEqual(store.imported_by_npc(existing), {})
            self.assertEqual(store.import_approved(), 1)
            output = store.imported_by_npc(existing)
            self.assertEqual(output[42][classicua_hash("Hello traveler.")], "Вітаю, мандрівнику!")
            self.assertEqual(output[99][classicua_hash("Hello traveler.")], "Вітаю, мандрівнику!")
            self.assertNotIn(102, output)
            self.assertEqual(store.decide(row["id"], "rejected", "reviewer",
                {k: False for k in checks}), "rejected")
            self.assertEqual(store.file.data["imports"], [])
            old = deepcopy(groups)
            old[0]["context_sha256"] = "c" * 64
            stale = GossipReviews(old, A, B, root / "reviews.json", root)
            with self.assertRaisesRegex(ValueError, "stale_or_unknown_gossip_version"):
                stale.decide(row["id"], "approved", "reviewer", checks)

    def test_unapproved_and_conflicting_versions_fail_closed(self):
        groups, _, existing = self.setup_data()
        with TemporaryDirectory() as d:
            root = Path(d) / "build"
            store = GossipReviews(groups, A, B, root / "reviews.json", root)
            p = {k: groups[0][k] for k in
                 ("group_id", "english_sha256", "context_sha256")}
            p["ukrainian_text"] = "Варіант один"
            store.propose([p], "manual")
            v = store.file.data["versions"][0]
            invalid = deepcopy(store.file.data)
            invalid["imports"] = [{"group_id": v["group_id"], "version_id": v["id"]}]
            with self.assertRaisesRegex(ValueError, "invalid_gossip_review_import"):
                validate_ledger(invalid)
            with self.assertRaisesRegex(ValueError, "duplicate_gossip_version"):
                store.propose([p], "manual")
            p["ukrainian_text"] = "Варіант два"
            store.propose([p], "manual")
            checks = {k: True for k in ("text","grammar","ai","rights","all_contexts")}
            for v in list(store.file.data["versions"]):
                store.decide(v["id"], "approved", "reviewer", checks)
            with self.assertRaisesRegex(ValueError, "conflicting_gossip_approved_versions"):
                store.import_approved()
            self.assertEqual(store.imported_by_npc(existing), {})

    def test_reviewed_never_overwrites_classicua(self):
        groups, _, existing = self.setup_data()
        with TemporaryDirectory() as d:
            root = Path(d) / "build"
            store = GossipReviews(groups, A, B, root / "reviews.json", root)
            p = {k: groups[0][k] for k in
                 ("group_id", "english_sha256", "context_sha256")}
            p["ukrainian_text"] = "Вітаю!"
            store.propose([p], "manual")
            store.decide(store.file.data["versions"][0]["id"], "approved", "human",
                         {k: True for k in ("text","grammar","ai","rights","all_contexts")})
            store.import_approved()
            existing["common"][classicua_hash("Hello traveler.")] = "Оригінал"
            with self.assertRaisesRegex(ValueError, "reviewed_gossip_classicua_conflict"):
                store.imported_by_npc(existing)

    def test_private_batch_schema_and_provenance(self):
        groups, _, _ = self.setup_data()
        with TemporaryDirectory() as d:
            path = Path(d) / "batches"
            self.assertEqual(create_batches(groups, A, B, path, 1), 2)
            import json
            batch = json.loads((path / "batch-0001.json").read_text(encoding="utf-8"))
            self.assertEqual(batch["entries"][0]["ukrainian_text"], "")
            self.assertEqual(batch["spoken_revision"], A)
            self.assertEqual(batch["classicua_revision"], B)
            self.assertIn("english_original", batch["entries"][0])
            # Rebuilding the queue MUST NOT wipe translated draft batches.
            batch["entries"][0]["ukrainian_text"] = "Збережений локальний чернетковий переклад"
            original = path / "batch-0001.json"
            original.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(create_batches(groups, A, B, path, 1), 2)
            self.assertEqual(json.loads(original.read_text())["entries"][0]["ukrainian_text"],
                             "Збережений локальний чернетковий переклад")
            batch["entries"][0]["context_sha256"] = "c" * 64
            original.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError,
                                        "stale_gossip_batch_move_aside_before_regeneration"):
                create_batches(groups, A, B, path, 1)

if __name__ == "__main__":
    unittest.main()
