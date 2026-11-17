"""Exact ClassicUA English-hash and Spoken NPC Gossip coverage contracts."""
import unittest

from tools.gossip_coverage import classicua_hash, audit_gossip_rows


class GossipCoverageTests(unittest.TestCase):
    def test_hash_matches_live_lua_and_classicua(self):
        self.assertEqual(classicua_hash("Hello traveler."), 3995595454)
        self.assertEqual(classicua_hash("Where is the inn?"), 3242472692)
        self.assertEqual(classicua_hash("Tell me more."), 979258284)
        self.assertEqual(classicua_hash("  Hello  traveler.\u00a0 "), 3995595454)
        self.assertIsNone(classicua_hash(""))
        self.assertIsNone(classicua_hash(None))

    def test_gossip_matches_per_npc_and_common_without_overclaiming(self):
        lines = [
            {"source": "gossip", "npcType": "creature", "npcId": 42,
             "npcName": "Example A", "originalText": "Hello traveler."},
            {"source": "gossip", "npcType": "creature", "npcId": 42,
             "npcName": "Example A", "originalText": "Hello traveler."},
            {"source": "gossip", "npcType": "creature", "npcId": 42,
             "npcName": "Example A", "originalText": "Tell me more."},
            {"source": "gossip", "npcType": "creature", "npcId": 42,
             "npcName": "Example A", "originalText": "Untranslated text."},
            {"source": "gossip", "npcType": "creature", "npcId": 99,
             "npcName": "Example B", "originalText": "Tell me more."},
            {"source": "gossip", "npcType": "creature", "npcId": 100,
             "npcName": "Example C", "originalText": "Unknown text."},
            {"source": "gossip", "npcType": "gameobject", "npcId": 101,
             "originalText": "Tell me more."},
            {"source": "accept", "npcType": "creature", "npcId": 200,
             "originalText": "Tell me more."},
        ]
        classicua = {
            "byNpc": {42: {3995595454: "ua greeting"}},
            "common": {979258284: "ua common"},
        }
        summary, missing = audit_gossip_rows(lines, classicua)
        self.assertEqual(summary["corpus_gossip_rows"], 7)
        self.assertEqual(summary["excluded_non_npc_gossip_rows"], 1)
        self.assertEqual(summary["total_gossip_npcs"], 3)
        self.assertEqual(summary["covered_gossip_npcs"], 2)
        self.assertEqual(summary["fully_covered_gossip_npcs"], 1)
        self.assertEqual(summary["partially_covered_gossip_npcs"], 1)
        self.assertEqual(summary["untranslated_gossip_npcs"], 1)
        self.assertEqual(summary["total_distinct_npc_wordings"], 5)
        self.assertEqual(summary["covered_distinct_npc_wordings"], 3)
        self.assertEqual(summary["untranslated_distinct_npc_wordings"], 2)
        self.assertEqual(summary["wordings_matched_by_npc_hash"], 1)
        self.assertEqual(summary["wordings_matched_by_common_hash"], 2)
        self.assertEqual([r["npc_id"] for r in missing], [42, 100])
        self.assertEqual(missing[0]["untranslated_wordings"], 1)

    def test_missing_original_uses_corpus_text_and_bad_rows_fail(self):
        summary, _ = audit_gossip_rows([
            {"source": "gossip", "npcType": "creature", "npcId": 3,
             "text": "Hello traveler.", "originalText": None}], {
                "byNpc": {}, "common": {3995595454: "ua"},
            })
        self.assertEqual(summary["covered_gossip_npcs"], 1)
        with self.assertRaisesRegex(ValueError, "invalid_spoken_corpus"):
            audit_gossip_rows([None], {"byNpc": {}, "common": {}})


if __name__ == "__main__":
    unittest.main()
