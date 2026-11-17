"""Local test ZIP: synthetic text only; builder always auto-imports first."""
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zipfile import ZipFile
import tempfile
import unittest

from lua_runtime import run_lua
from tools import build_ukrainian as builder


EN = "Invented text"
UK = 'Вигаданий "рядок" ї ґ.\\ Ім’я\nДругий рядок.'


class BuildUkrainianTests(unittest.TestCase):
    def test_unicode_and_lua_quoting_roundtrip(self):
        quoted = builder.lua_quote(UK)
        run_lua("assert(" + quoted + " == " + builder.lua_quote(UK) + ")")
        self.assertIn("ґ", quoted)
        self.assertIn("\\n", quoted)
        self.assertNotIn('""рядок""', quoted)
        for bad in ("", "   ", 12, "x" * 60001):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(ValueError):
                builder.lua_quote(bad)

    def test_generated_manifest_is_a_real_separate_module_without_fake_audio(self):
        preview = {42: {"accept": {"text": UK, "reviewed": False},
                        "complete": {"text": "Дякую.", "reviewed": True}}}
        generated = builder.render_quest_lua(preview, "a" * 40)
        entries = builder.template_entries(generated)
        self.assertEqual(set(entries), {
            "Spoken_Ukrainian/Spoken_Ukrainian.toc",
            "Spoken_Ukrainian/Core.lua",
            "Spoken_Quests_UA/Spoken_Quests_UA.toc",
            "Spoken_Quests_UA/Module.lua",
            "Spoken_Quests_UA/NativeQuestFrame.lua",
            "Spoken_Quests_UA/GossipQuestTitles.lua",
            "Spoken_Quests_UA/Translations.lua",
            "Spoken_Gossip_UA/Spoken_Gossip_UA.toc",
            "Spoken_Gossip_UA/GossipFrame.lua",
            "Spoken_Gossip_UA/Translations.lua",
        })
        self.assertIn(b"Spoken_Ukrainian, ", entries["Spoken_Quests_UA/Spoken_Quests_UA.toc"]
                      .replace(b"Spoken_Ukrainian\n", b"Spoken_Ukrainian, "))
        self.assertIn(b"X-SpokenQuests-DataModule-Version: 1",
                      entries["Spoken_Quests_UA/Spoken_Quests_UA.toc"])
        self.assertNotIn(b".mp3", b"".join(entries.values()))
        self.assertNotIn(b"Silence", b"".join(entries.values()))
        self.assertIn("machine 1:1", generated.decode())
        self.assertNotIn("Invented text", generated.decode())

    def test_archive_contents_deterministic_and_atomic(self):
        entries = builder.template_entries(builder.render_quest_lua(
            {42: {"accept": {"text": UK, "reviewed": False}}}, "a" * 40))
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(builder, "DIST", Path(tmp)):
                a, d1 = builder.write_zip(entries, Path(tmp) / "one.zip")
                b, d2 = builder.write_zip(entries, Path(tmp) / "two.zip")
                self.assertEqual(d1, d2)
                self.assertEqual(a.read_bytes(), b.read_bytes())
                self.assertEqual(sha256(a.read_bytes()).hexdigest(), d1)
                with ZipFile(a) as z:
                    self.assertEqual(z.namelist(), sorted(entries))
                    self.assertIsNone(z.testzip())
                    self.assertEqual(
                        z.read("Spoken_Quests_UA/Translations.lua"),
                        entries["Spoken_Quests_UA/Translations.lua"])
                    self.assertTrue(all(file.date_time == (1980, 1, 1, 0, 0, 0)
                                        for file in z.infolist()))

    def test_ambiguous_quest_event_suppressed_from_preview(self):
        state = Mock()
        state.inventory.targets = {
            "q:42:accept": SimpleNamespace(family="quest"),
            "q:42:accept:w2": SimpleNamespace(family="quest"),
        }
        text1 = {"id": "a", "target_id": "q:42:accept", "decision": "machine_1to1_provisional",
                 "text": "Перший."}
        text2 = {"id": "b", "target_id": "q:42:accept:w2",
                 "decision": "machine_1to1_provisional", "text": "Другий."}
        machine = {"schema_version": 1, "versions": [text1, text2],
                   "imports": [{"target_id": text1["target_id"], "version_id": "a"},
                               {"target_id": text2["target_id"], "version_id": "b"}]}
        human = {"schema_version": 1, "versions": [], "imports": []}
        state.machine_imports.file.data = machine
        state.translations.file.data = human
        with patch.object(builder, "validate_machine_ledger", side_effect=lambda x: x), patch.object(
                builder, "_validate_ledger", side_effect=lambda x: x):
            preview, count, skipped = builder.current_quest_texts(state)
        self.assertEqual(preview, {})
        self.assertEqual(count, 2)
        self.assertEqual(skipped, 2)

    def test_quest_title_comes_from_the_exact_audited_source_not_an_id_guess(self):
        target = "q:42:accept"
        source_id = "quest:horde:42:accept"
        row = {"id": "machine-version", "target_id": target, "source_id": source_id,
               "decision": "machine_1to1_provisional", "text": "Вигаданий текст."}
        state = Mock()
        state.machine_imports.file.data = {
            "versions": [row], "imports": [{"target_id": target, "version_id": row["id"]}]}
        state.translations.file.data = {"versions": [], "imports": []}
        state.inventory.targets = {target: SimpleNamespace(family="quest")}
        state.source.units = {source_id: object()}
        record = SimpleNamespace(fields={(1,): SimpleNamespace(
            node=SimpleNamespace(value="Вигадана назва"))})
        state.dataset.faction_views.return_value = ({"horde": {42: record}, "alliance": {}}, [])
        with patch.object(builder, "validate_machine_ledger", side_effect=lambda x: x), patch.object(
                builder, "_validate_ledger", side_effect=lambda x: x):
            preview, count, skipped = builder.current_quest_texts(state)
        self.assertEqual((count, skipped), (1, 0))
        self.assertEqual(preview[42]["title"], "Вигадана назва")
        generated = builder.render_quest_lua(preview, "a" * 40).decode()
        self.assertIn('title = "Вигадана назва"', generated)
        self.assertIn('accept = { text = "Вигаданий текст."', generated)

    def test_quest_title_is_omitted_when_audited_faction_titles_conflict(self):
        # Two distinct events can share one QuestID; do not choose one
        # faction's title blindly on an unknown client context.
        targets = ("q:42:accept", "q:42:complete")
        rows = [
            {"id": "a", "target_id": targets[0], "source_id": "quest:horde:42:accept",
             "decision": "machine_1to1_provisional", "text": "Перший текст."},
            {"id": "b", "target_id": targets[1], "source_id": "quest:alliance:42:complete",
             "decision": "machine_1to1_provisional", "text": "Другий текст."},
        ]
        state = Mock()
        state.machine_imports.file.data = {
            "versions": rows, "imports": [
                {"target_id": item["target_id"], "version_id": item["id"]}
                for item in rows]}
        state.translations.file.data = {"versions": [], "imports": []}
        state.inventory.targets = {target: SimpleNamespace(family="quest") for target in targets}
        state.source.units = {row["source_id"]: object() for row in rows}
        def record(title):
            return SimpleNamespace(fields={(1,): SimpleNamespace(
                node=SimpleNamespace(value=title))})
        state.dataset.faction_views.return_value = (
            {"horde": {42: record("Назва орди")},
             "alliance": {42: record("Назва альянсу")}}, [])
        with patch.object(builder, "validate_machine_ledger", side_effect=lambda x: x), patch.object(
                builder, "_validate_ledger", side_effect=lambda x: x):
            preview, _, _ = builder.current_quest_texts(state)
        self.assertNotIn("title", preview[42])

    def test_gossip_title_only_from_audited_quest_records_even_without_spoken_voice(self):
        state = Mock()
        state.policy.allows_ai_transations.return_value = True
        state.source.files = {"entries/forever/quest_horde.lua": "a" * 64}
        source = "entries/forever/quest_horde.lua"
        entry = SimpleNamespace(
            ai=True, fields={(1,): SimpleNamespace(
                node=SimpleNamespace(value="Загублена зброя"),
                origin=SimpleNamespace(file=source))})
        state.dataset.faction_views.return_value = (
            {"alliance": {}, "horde": {97279: entry}}, [])
        names = builder.local_gossip_titles(state)
        self.assertEqual(names, {"alliance": {}, "horde": {97279: "Загублена зброя"}})
        generated = builder.render_quest_lua({}, "a" * 40, gossip_titles=names).decode()
        self.assertIn("[97279] = \"Загублена зброя\"", generated)
        self.assertIn("SpokenUkrainian.GossipQuestTitles", generated)
        self.assertIn("SpokenUkrainian.QuestTranslations = {", generated)
        # This title is *not* a narration import and remains unreviewed.
        state.policy.allows_ai_transations.return_value = False
        state.dataset.faction_views.return_value = (
            {"alliance": {}, "horde": {}}, [])
        self.assertEqual(builder.local_gossip_titles(state)["horde"], {})

    def test_quest_97279_diagnostic_does_not_invent_reason_without_real_corpus(self):
        state = Mock()
        state.policy.allows_ai_transations.return_value = True
        state.inventory.targets = {"q:42:accept": SimpleNamespace(family="quest")}
        state.inventory.contexts = {}
        state.original_index.original_english = {}
        state.source.units = {}
        state._hints = [{"source_id": "quest:horde:97279:accept",
                         "reason": "target_unavailable", "candidates": []}]
        state.machine_imports.file.data = {"imports": []}
        state.translations.file.data = {"imports": []}
        report = builder.import_reason_for_quest(state, 97279)
        self.assertEqual(report["spoken_narrated_targets"], 0)
        self.assertEqual(report["auto_imported_targets"], 0)
        self.assertEqual(report["candidate_reasons"], ["target_unavailable"])

    def test_unknown_faction_count_reports_metadata_not_review_approval(self):
        state = Mock()
        state.inventory.contexts = {
            "q:42:accept": [{"faction": "unknown"}],
            "q:42:complete": [{"faction": "horde"}],
            "q:43:accept": [{"faction": "unknown"}],
        }
        state.machine_imports.file.data = {"imports": [
            {"target_id": "q:42:accept", "version_id": "a"},
            {"target_id": "q:42:complete", "version_id": "b"},
        ]}
        state.translations.file.data = {"imports": [
            {"target_id": "q:43:accept", "version_id": "c"},
        ]}
        self.assertEqual(
            builder.unknown_faction_import_counts(state),
            {"machine_provisional": 1, "human_reviewed": 1})
        state.machine_imports.file.data["imports"].append(
            {"target_id": "q:42:accept", "version_id": "a"})
        with self.assertRaisesRegex(ValueError, "duplicate_quest_faction_import_target"):
            builder.unknown_faction_import_counts(state)

    def test_import_always_runs_before_zip_write(self):
        state = Mock()
        state.inventory.revision = "a" * 40
        state.inventory.contexts = {}
        state.translation_action.return_value = {"report": {
            "total_spoken_records": 19639, "machine_one_to_one_imported": 1,
            "human_reviewed_imported_total": 0}}
        order = []
        def do_import(action, payload):
            order.append("import")
            self.assertEqual(action, "auto_import_one_to_one")
            self.assertEqual(payload, {"source": "classicua"})
            return {"report": state.translation_action.return_value["report"]}
        state.translation_action.side_effect = do_import
        preview = {42: {"accept": {"text": UK, "reviewed": False}}}
        def fake_zip(entries):
            order.append("zip")
            self.assertIn("Spoken_Quests_UA/Translations.lua", entries)
            self.assertIn("Spoken_Gossip_UA/Translations.lua", entries)
            return Path("dist/test.zip"), "b" * 64
        with patch.object(builder, "validate_source_paths"), patch.object(
                builder, "build_state", return_value=state), patch.object(
                builder, "current_quest_texts", return_value=(preview, 1, 0)), patch.object(
                builder, "unknown_faction_import_counts",
                return_value={"machine_provisional": 0, "human_reviewed": 0}), patch.object(
                builder, "read_classicua_inflections", return_value={}), patch.object(
                builder, "local_gossip_titles", return_value={"horde": {}, "alliance": {}}), patch.object(
                builder, "local_gossip_texts", return_value={"byNpc": {}, "common": {}}), patch.object(
                builder, "import_reason_for_quest", return_value={"quest_id": 97279}), patch.object(
                builder, "write_zip", side_effect=fake_zip):
            built = builder.build(Path("/unused/classicua"), Path("/unused/spoken"))
        self.assertEqual(order, ["import", "zip"])
        self.assertEqual(built["previewable_quest_moments"], 1)
        self.assertEqual(built["reported_total_spoken"], 19639)

    def test_failed_auto_import_never_writes_archive(self):
        state = Mock()
        state.translation_action.side_effect = ValueError("public_revision_mismatch")
        with patch.object(builder, "validate_source_paths"), patch.object(
                builder, "build_state", return_value=state), patch.object(
                builder, "write_zip") as zip_write:
            with self.assertRaisesRegex(ValueError, "public_revision_mismatch"):
                builder.build("/missing/ua", "/missing/spoken")
            zip_write.assert_not_called()

    def test_no_quest_entries_does_not_build_empty_pack(self):
        state = Mock()
        state.translation_action.return_value = {
            "report": {"total_spoken_records": 19639, "imported_total": 0,
                       "human_reviewed_imported_total": 0, "machine_one_to_one_imported": 0}}
        with patch.object(builder, "validate_source_paths"), patch.object(
                builder, "build_state", return_value=state), patch.object(
                builder, "current_quest_texts", return_value=({}, 0, 0)), patch.object(
                builder, "write_zip") as zip_write:
            with self.assertRaisesRegex(ValueError, "no_unambiguous_quest_imports"):
                builder.build("/missing/ua", "/missing/spoken")
            state.translation_action.assert_called_once()
            zip_write.assert_not_called()

    def test_lua_module_registers_without_audio_and_preview_is_opt_in(self):
        files = builder.template_entries(
            builder.render_quest_lua(
                {42: {"title": "Вигадана назва", "accept": {
                    "text": "{Ім'я:к}, {стать:готовий:готова}, {Клас:к} із раси {раса}! {необроблений:код}",
                    "reviewed": False}}}, "a" * 40, {
                    "class": {"paladin": {"к": ("паладине", "паладинко")}},
                    "race": {"orc": {"н": ("орк", "орчиня")}}}))
        script = """
SlashCmdList = {}
DEFAULT_CHAT_FRAME = {AddMessage = function(self, text) assert(type(text) == "string") end}
local widgets = {}
local widgetMT
widgetMT = {__index = function(self, key)
    if key == "CreateTexture" or key == "CreateFontString" then
        return function() return setmetatable({}, widgetMT) end
    elseif key == "GetStringHeight" then return function() return 28 end
    elseif key == "SetText" then
        return function(self, value) self.text = value end
    elseif key == "SetScript" then
        return function(self, name, callback) self[name] = callback end
    elseif key == "RegisterEvent" then
        return function(self, event) self.events[event] = true end
    elseif key == "Show" then
        return function(self) self.shown = true end
    elseif key == "Hide" then
        return function(self) self.shown = false end
    else return function() end end
end}
UIParent = setmetatable({}, widgetMT)
function CreateFrame(type, name, parent, template)
    local frame = setmetatable({events = {}}, widgetMT)
    table.insert(widgets, frame)
    return frame
end
GetQuestID = function() return 42 end
GetTitleText = function() return "Fallback English title" end
UnitName = function() return "Тест" end
local sex = 2
UnitSex = function() return sex end
UnitClass = function() return "Paladin", "PALADIN" end
UnitRace = function() return "Orc", "Orc" end
VoiceOver = {DataModules = {
    Register = function(self, name, module)
        assert(name == "Spoken_Quests_UA")
        assert(type(module.SoundLengthLookupByFileName) == "table")
        assert(next(module.SoundLengthLookupByFileName) == nil)
        self.registered = name
    end
}}
"""
        for name in (
                "Spoken_Ukrainian/Core.lua",
                "Spoken_Quests_UA/Translations.lua",
                "Spoken_Quests_UA/Module.lua"):
            script += "\n" + files[name].decode("utf-8") + "\n"
        script += """
assert(VoiceOver.DataModules.registered == "Spoken_Quests_UA")
assert(SpokenUkrainian.previewEnabled == false)
local found
for _, widget in ipairs(widgets) do
    if widget.events and widget.events.QUEST_DETAIL then found = widget end
end
assert(found and found.events.QUEST_FINISHED)
found.OnEvent(found, "QUEST_DETAIL") -- default: no UI
assert(#widgets == 1)
SlashCmdList.SPOKENUKRAINIAN("preview on")
found.OnEvent(found, "QUEST_DETAIL") -- opted in: preview exists
assert(#widgets > 1)
assert(SpokenUkrainian.previewEnabled)
local previewWindow
for _, widget in ipairs(widgets) do
    if rawget(widget, "Info") and rawget(widget, "Content") then previewWindow = widget end
end
assert(previewWindow ~= nil)
assert(previewWindow.Info.text:find("Вигадана назва", 1, true))
assert(previewWindow.Info.text:find("Quest 42", 1, true))
assert(previewWindow.Content.text:find("Тест", 1, true))
assert(previewWindow.Content.text:find("готовий", 1, true))
assert(previewWindow.Content.text:find("Паладине", 1, true))
assert(previewWindow.Content.text:find("орк", 1, true))
assert(previewWindow.Content.text:find("{необроблений:код}", 1, true))
assert(not previewWindow.Content.text:find("{Ім'я:к}", 1, true))
sex = 3
assert(SpokenUkrainian:ExpandQuestText("{стать:готовий:готова}") == "готова")
assert(SpokenUkrainian:ExpandQuestText("{клас:к}") == "паладинко")
assert(SpokenUkrainian:ExpandQuestText("{раса}") == "орчиня")
assert(SpokenUkrainian:ExpandQuestText("{ім'я:р}") == "Тест")
assert(SpokenUkrainian:ExpandQuestText("{вигаданий:код}") == "{вигаданий:код}")
SlashCmdList.SPOKENUKRAINIAN("preview off")
assert(SpokenUkrainian.previewEnabled == false)
"""
        run_lua(script)


if __name__ == "__main__":
    unittest.main()
