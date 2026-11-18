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
from tools import gossip_machine_import


class SourceSelectedBuildTests(unittest.TestCase):
    def test_exact_human_selected_source_overrides_default_in_private_zip(self):
        self.build_gossip_case(conflict=False)

    def test_conflicting_npc_does_not_remove_shared_common(self):
        for manager in (False, True):
            with self.subTest(manager=manager):
                self.build_gossip_case(conflict=True, manager=manager)

    def build_gossip_case(self, *, conflict, manager=False):
        source = [{"source": "gossip", "npcType": "creature", "npcId": 42,
                   "npcName": "Synthetic NPC", "originalText": "Hello traveler."}]
        source.append(dict(source[0], npcId=43))
        hashed = classicua_hash("Hello traveler.")
        skipped = [] if manager else None
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
                gossip_machine_import,
                "GossipMachineImport", return_value=Mock(
                    build_lookup=Mock(return_value={"byNpc": {}, "common": {
                        classicua_hash("Hello traveler."): "Стара версія"}}),
                    page=Mock(return_value={}))), patch.object(
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
                "tools.gossip_translation_review.load_reviewed_gossip",
                return_value={42: {hashed: "Раніше схвалений переклад"}} if conflict else {}), patch(
                "tools.gossip_coverage.read_pinned_corpus", return_value=source), patch.object(
                builder, "import_reason_for_quest", return_value={"quest_id": 97279}), patch.object(
                builder, "write_zip", side_effect=write_zip), patch(
                "tools.import_build_inventory.collect_build_rows", return_value=[]) as collect:
                result = builder.build(Path("/unused/classicua"), Path("/unused/spoken"), skipped=skipped)
            lua = captured["Spoken_Quests_UA/GossipTranslations.lua"].decode("utf-8")
            if conflict:
                from lua_runtime import run_lua
                self.assertNotIn("Альтернативний переклад", lua)
                self.assertNotIn("Раніше схвалений переклад", lua)
                self.assertEqual(result["explicit_source_gossip_selections"], 0)
                if manager:
                    self.assertEqual(skipped, [(key[1], "conflicting_human_reviewed_gossip_selection")])
                self.assertEqual(collect.call_args.kwargs["excluded_gossip"], {(42, hashed): "reviewed+source_selected"})
                run_lua(lua + r'''
_G = _G or _ENV
local npc = 42
function UnitGUID() return "Creature-0-1-2-3-" .. npc .. "-00001" end
function CreateFrame() return {RegisterEvent = function() end, SetScript = function() end} end
function hooksecurefunc(tbl, key, cb)
    local original = tbl[key]
    tbl[key] = function(...) original(...); cb(...) end
end
function SpokenUkrainian:ExpandQuestText(text) return text end
GossipOptionButtonMixin = {Setup = function(widget, info) widget:SetText(info.name) end}
''' + captured["Spoken_Quests_UA/GossipFrame.lua"].decode("utf-8") + r'''
local widget = {GetText = function(self) return self.text end,
                SetText = function(self, text) self.text = text end}
local option = {name = "Hello traveler."}
GossipOptionButtonMixin.Setup(widget, option)
assert(widget.text == "Hello traveler.")
npc = 43
GossipOptionButtonMixin.Setup(widget, option)
assert(widget.text == "Стара версія")
''')
            else:
                self.assertIn("Альтернативний переклад", lua)
                self.assertEqual(result["explicit_source_gossip_selections"], 1)
            self.assertIn("Стара версія", lua)


if __name__ == "__main__":
    unittest.main()
