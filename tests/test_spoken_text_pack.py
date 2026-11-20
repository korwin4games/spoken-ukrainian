"""Text-only Ukrainian Quest/Gossip pack contract tests."""
import unittest

from lua_runtime import run_lua
from tools.build_ukrainian import render_quest_lua, template_entries, GOSSIP_MODULE
from tools.spoken_text_pack import (
    quest_payload, gossip_payload, render_spoken_text_pack, text_pack_words,
)


class SpokenTextPackTests(unittest.TestCase):
    def test_native_placeholders_only(self):
        self.assertEqual(
            text_pack_words("Вітаю, {ім'я}!{стать:радий:рада} $B"),
            "Вітаю, $N!$Gрадий:рада; $B")
        self.assertEqual(text_pack_words("Клас: {клас}, раса: {раса}"),
                         "Клас: $C, раса: $R")
        self.assertIsNone(text_pack_words("Герою, {ім'я:к}!"))
        self.assertIsNone(text_pack_words("{невідомий:плейсхолдер}"))
        self.assertIsNone(text_pack_words("{стать:ні:так;несумісний}"))

    def test_quest_payload_uses_canonical_line_ids_and_excludes_unsupported(self):
        titles, lines = quest_payload({
            42: {"title": "Український квест",
                 "accept": {"text": "Вітаю, {ім'я}!", "reviewed": False},
                 "complete": {"text": "Дякую, {ім'я:к}!", "reviewed": True}},
            9: {"title": "Лише назва"},
        })
        self.assertEqual(titles, {42: "Український квест"})
        self.assertEqual(lines, {"q:42:accept": "Вітаю, $N!"})

    def test_gossip_shared_id_conflict_fails_closed(self):
        rows = [
            {"status": "ready", "selection": {"text": "Вітаю."},
             "contexts": [{"lineId": "g:abcd"}]},
            {"status": "ready", "selection": {"text": "Привіт."},
             "contexts": [{"lineId": "g:abcd"}]},
            {"status": "stale", "selection": {"text": "Застаріле."},
             "contexts": [{"lineId": "g:efgh"}]},
            {"status": "ready", "selection": {"text": "Добрий день."},
             "contexts": [{"lineId": "g:unique"}]},
        ]
        self.assertEqual(gossip_payload(rows), {"g:unique": "Добрий день."})

    def test_text_pack_registers_only_with_supported_spoken_api(self):
        data = render_spoken_text_pack(
            {42: "Український квест"}, {"q:42:accept": "Вітаю, $N!"})
        code = StringIO = data.decode("utf-8")
        self.assertIn('SpokenUkrainian:RegisterTextPack("quests",', code)
        from pathlib import Path
        core = Path("addons/Spoken_Ukrainian/Core.lua").read_text(encoding="utf-8")
        lua = r'''
SlashCmdList = {}
Spoken = {RegisterText = function(self, language, section, data)
    assert(language == "ukUA" and section == "quests")
    assert(data.titles[42] == "Український квест")
    assert(data.lines["q:42:accept"] == "Вітаю, $N!")
    self.registered = true
    return true
end}
''' + core + "\n" + code + "\nassert(Spoken.registered)\n"
        run_lua(lua)

    def test_older_spoken_does_not_crash(self):
        from pathlib import Path
        code = (Path("addons/Spoken_Ukrainian/Core.lua").read_text(encoding="utf-8")
                + "\n" + render_spoken_text_pack(lines={"q:42:accept": "Текст."}).decode())
        run_lua("SlashCmdList = {}\n" + code)

    def test_text_pack_module_tocs_are_independent_and_audio_free(self):
        q = template_entries(render_quest_lua({
            42: {"accept": {"text": "Тест", "reviewed": False}},
        }, "a" * 40))
        g = template_entries(None, b"SpokenUkrainian.GossipTranslations = {}",
                             module=GOSSIP_MODULE)
        for entries, module in ((q, "Spoken_Quest_UA"), (g, GOSSIP_MODULE)):
            toc = entries[f"{module}/{module}.toc"].decode()
            self.assertIn("## X-Spoken-Text: ukUA", toc)
            self.assertIn("## X-Spoken-TextFormat: 1", toc)
            self.assertIn("TextPack.lua", toc)
            self.assertIn(f"{module}/TextPack.lua", entries)
        self.assertNotIn("X-SpokenQuests-Language: ukUA",
                         q["Spoken_Quest_UA/Spoken_Quest_UA.toc"].decode())


if __name__ == "__main__":
    unittest.main()
