"""Runtime build bridge: active source choices override only exact pinned NPC text."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from adapters.sqlite_translation_store import enable_sqlite
from adapters.source_revision_store import SourceReviewStore, CHECKS
from tools.gossip_coverage import classicua_hash
from tools.source_revision_review import gossip_contexts
from tools import build_ukrainian as builder


class SourceSelectedBuildTests(unittest.TestCase):
    def test_exact_human_selected_source_overrides_default_in_private_zip(self):
        source = [{"source": "gossip", "npcType": "creature", "npcId": 42,
                   "npcName": "Synthetic NPC", "originalText": "Hello traveler."}]
        trusted = gossip_contexts(source)
        key, proof = next(iter(trusted.items()))
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "translations.sqlite3"
            store = SourceReviewStore(db)
            store.ingest({"provider": "another", "revision": "b" * 40,
                "records": [{"domain": "gossip", "target_id": key[1],
                    "english_sha256": proof["english_sha256"],
                    "context_sha256": proof["context_sha256"],
                    "ukrainian_text": "Альтернативний переклад",
                    "source_ref": "another:synthetic"}]}, trusted)
            candidate = store.candidates()[0]
            store.decide(candidate["id"], "approved", "human",
                         {k: True for k in CHECKS}, trusted)
            store.activate(candidate["id"], "human", trusted)
            state = Mock()
            state.inventory.revision = "a" * 40
            state.source.revision = "b" * 40
            state.inventory.contexts = {}
            state.translation_action.return_value = {"report": {
                "total_spoken_records": 1, "machine_one_to_one_imported": 1,
                "human_reviewed_imported_total": 0}}
            preview = {1: {"accept": {"text": "Синтетичний квест", "reviewed": False}}}
            captured = {}
            def write_zip(files):
                captured.update(files)
                return Path("dist/synthetic.zip"), "c" * 64
            with enable_sqlite(db), patch.object(
                builder, "validate_source_paths"), patch.object(
                builder, "build_state", return_value=state), patch.object(
                builder, "current_quest_texts", return_value=(preview, 1, 0)), patch.object(
                builder, "unknown_faction_import_counts",
                return_value={"machine_provisional": 0, "human_reviewed": 0}), patch.object(
                builder, "read_classicua_inflections", return_value={}), patch.object(
                builder, "local_gossip_titles",
                return_value={"horde": {}, "alliance": {}}), patch.object(
                builder, "local_gossip_texts", return_value={
                    "byNpc": {}, "common": {classicua_hash("Hello traveler."): "Стара версія"}}), patch(
                "tools.gossip_translation_review.load_reviewed_gossip", return_value={}), patch(
                "tools.gossip_coverage.read_pinned_corpus", return_value=source), patch.object(
                builder, "import_reason_for_quest", return_value={"quest_id": 97279}), patch.object(
                builder, "write_zip", side_effect=write_zip), patch(
                "tools.import_build_inventory.collect_build_rows", return_value=[]):
                result = builder.build(Path("/unused/classicua"), Path("/unused/spoken"))
            lua = captured["Spoken_Quests_UA/GossipTranslations.lua"].decode("utf-8")
            self.assertIn("Альтернативний переклад", lua)
            self.assertIn("[42] = {", lua)
            self.assertEqual(result["explicit_source_gossip_selections"], 1)
            # Fallback remains in the common table. NPC-specific choice has
            # precedence in GossipFrame.TranslatedText.
            self.assertIn("Стара версія", lua)


if __name__ == "__main__":
    unittest.main()
