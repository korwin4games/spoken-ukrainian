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
        shared = "g:" + "a" * 32
        unique = "g:" + "b" * 32

        def row(npc, key, english, selection):
            return {
                "status": "ready", "npc_id": npc, "english_hash": npc,
                "review_binding": "verified", "originals": [english],
                "selection": {"text": selection} if selection else None,
                "contexts": [{"lineId": key, "originalText": english, "npcType": "creature",
                              "voice": None, "playerGender": None}],
            }

        rows = [row(42, shared, "Hello.", "Вітаю."),
                row(43, shared, "Hello.", "Привіт."),
                row(44, unique, "Welcome.", "Добрий день.")]
        self.assertEqual(gossip_payload(rows), {unique: "Добрий день."})

        # A shared canonical ID is not safe if even one NPC has no selection.
        rows[1]["selection"] = None
        self.assertEqual(gossip_payload(rows), {unique: "Добрий день."})
        rows[1]["selection"] = {"text": "Вітаю."}
        self.assertEqual(gossip_payload(rows), {shared: "Вітаю.", unique: "Добрий день."})

        # A different verified original cannot inherit the same translation.
        rows[1]["originals"] = ["Greetings."]
        rows[1]["contexts"][0]["originalText"] = "Greetings."
        self.assertEqual(gossip_payload(rows), {unique: "Добрий день."})

        rows[1]["status"] = "stale"
        self.assertEqual(gossip_payload(rows), {unique: "Добрий день."})

    def test_gossip_complete_corpus_scoping_blocks_unlisted_contexts(self):
        from tools.gossip_coverage import classicua_hash
        key = "g:" + "c" * 32
        english = "Original line."
        row = {
            "npc_id": 42, "english_hash": classicua_hash(english),
            "review_binding": "evidence", "status": "ready", "originals": [english],
            "selection": {"text": "Переклад."},
            "contexts": [{"lineId": key, "originalText": english,
                          "npcType": "creature", "voice": None, "playerGender": None}],
        }
        full = [{"source": "gossip", "lineId": key, "npcId": 42, "npcType": "creature",
                 "originalText": english}]
        self.assertEqual(gossip_payload([row], corpus_lines=full), {key: "Переклад."})
        # This row is outside the editor scope but shares the global ID.
        full.append({**full[0], "npcId": 43})
        self.assertEqual(gossip_payload([row], corpus_lines=full), {})
        full.pop()
        full.append({**full[0], "npcType": "gameobject", "npcId": 0})
        self.assertEqual(gossip_payload([row], corpus_lines=full), {})

    def test_quest_base_id_requires_one_verified_original(self):
        preview = {
            42: {"title": "Завдання", "accept": {"text": "Вітаю."}},
            43: {"accept": {"text": "Привіт."}},
        }
        moments = {(42, "accept"): {"Hello."},
                   (43, "accept"): {"Hello.", "Greetings."}}
        titles, lines = quest_payload(preview, source_moments=moments,
                                      faction_titles={"horde": {43: "Назва"}})
        self.assertEqual(titles, {42: "Завдання", 43: "Назва"})
        self.assertEqual(lines, {"q:42:accept": "Вітаю."})
        # Faction-specific title disagreement must not be globally exported.
        titles, _ = quest_payload(preview, source_moments=moments,
                                  faction_titles={"horde": {42: "Інша назва"}})
        self.assertNotIn(42, titles)

    def test_unsupported_tokens_fail_closed(self):
        for value in ("Привіт, $Q.", "$Gmale:female", "$Gmale:;", "{ім'я:к}",
                      "{стать:хто:що;$N}", "Невідоме {плейсхолдер}."):
            with self.subTest(value=value):
                self.assertIsNone(text_pack_words(value))

    def test_text_pack_registers_only_with_supported_spoken_api(self):
        data = render_spoken_text_pack(
            {42: "Український квест"}, {"q:42:accept": "Вітаю, $N!"})
        code = data.decode("utf-8")
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
            self.assertIn(f"{module}/NotoSans-Regular.ttf", entries)
            self.assertIn(f"{module}/OFL-NotoSans.txt", entries)
        self.assertNotIn("X-SpokenQuests-Language: ukUA",
                         q["Spoken_Quest_UA/Spoken_Quest_UA.toc"].decode())


if __name__ == "__main__":
    unittest.main()
