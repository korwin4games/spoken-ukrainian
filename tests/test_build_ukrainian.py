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
            "Spoken_Quests_UA/Translations.lua",
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

    def test_import_always_runs_before_zip_write(self):
        state = Mock()
        state.inventory.revision = "a" * 40
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
            return Path("dist/test.zip"), "b" * 64
        with patch.object(builder, "validate_source_paths"), patch.object(
                builder, "build_state", return_value=state), patch.object(
                builder, "current_quest_texts", return_value=(preview, 1, 0)), patch.object(
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
                {42: {"accept": {"text": UK, "reviewed": False}}}, "a" * 40))
        script = """
SlashCmdList = {}
DEFAULT_CHAT_FRAME = {AddMessage = function(self, text) assert(type(text) == "string") end}
local widgets = {}
local widgetMT
widgetMT = {__index = function(self, key)
    if key == "CreateTexture" or key == "CreateFontString" then
        return function() return setmetatable({}, widgetMT) end
    elseif key == "GetStringHeight" then return function() return 28 end
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
SlashCmdList.SPOKENUKRAINIAN("preview off")
assert(SpokenUkrainian.previewEnabled == false)
"""
        run_lua(script)


if __name__ == "__main__":
    unittest.main()
