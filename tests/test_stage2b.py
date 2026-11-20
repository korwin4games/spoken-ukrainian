"""Offline characterization of immutable Spoken blobs, using the Stage 1 Lua runner."""
import hashlib
import json
import unittest

from lua_runtime import run_lua
from test_stage1 import LEGACY_LOCK, ROOT, git, quote_lua, snapshot


class RuntimeCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = snapshot()
        manifest = json.loads((ROOT / "tests/stage2b_sources.json").read_text())
        if manifest["revision"] != LEGACY_LOCK["revision"]:
            raise AssertionError("Stage 2B source revision differs from project pin")
        cls.sources = {}
        for path, digest in {**LEGACY_LOCK["files"], **manifest["files"]}.items():
            data = git("show", manifest["revision"] + ":" + path)
            if hashlib.sha256(data).hexdigest() != digest:
                raise AssertionError("Pinned source hash mismatch: " + path)
            cls.sources[path] = data.decode()
        # Same synthetic metadata, pack and Session used by Stage 1, unchanged.
        from test_stage1 import builder
        metadata, _ = builder.read_toc(ROOT / "addons" / builder.FOLDER)
        cls.script = "SOURCES = {}\n"
        for path, source in cls.sources.items():
            cls.script += "SOURCES[ " + quote_lua(path) + " ] = " + quote_lua(source) + "\n"
        cls.script += "META = {}\n"
        for key, value in metadata.items():
            cls.script += "META[ " + quote_lua(key) + " ] = " + quote_lua(value) + "\n"
        cls.script += "FOLDER = " + quote_lua(builder.FOLDER) + "\n"
        cls.script += "PACK = " + quote_lua((ROOT / "addons" / builder.FOLDER / "Lore.lua").read_text()) + "\n"
        cls.script += (ROOT / "tests/contract.lua").read_text()
        cls.script += (ROOT / "tests/runtime_contract.lua").read_text()

    @classmethod
    def tearDownClass(cls):
        if snapshot() != cls.before:
            raise AssertionError("Upstream checkout changed during Stage 2B tests")

    def check(self, name):
        run_lua(self.script + "\nlocal before = {}\n"
                "for k, v in pairs(_G) do before[k] = v end\n" + name + "()\n"
                "for k, v in pairs(_G) do assert(before[k] == v, 'Host global changed: ' .. k) end\n"
                "for k, v in pairs(before) do assert(_G[k] == v, 'Host global removed: ' .. k) end\n")

    def test_readables_text_without_file_is_available_but_unsafe(self):
        self.check("readables_text_without_file")

    def test_readables_compendium_language_is_client_not_voice(self):
        self.check("readables_compendium")

    def test_readables_audio_metadata_and_nonclient_captions(self):
        self.check("readables_audio")

    def test_readables_missing_disabled_fallback_and_legacy(self):
        self.check("readables_fallback")

    def test_readables_matching_and_player_templates(self):
        self.check("readables_matching")

    def test_quests_registration_load_order_and_disabled(self):
        self.check("quests_registration")

    def test_quests_audio_required_queue_and_caption_locale_gate(self):
        self.check("quests_audio")

    def test_quests_missing_fallback_and_gender(self):
        self.check("quests_fallback")

    def test_quests_compendium_text_remains_in_client_language(self):
        self.check("quests_compendium")

    def test_gossip_matched_unmatched_and_player_templates(self):
        self.check("gossip_matching")

    def test_gossip_audio_required_and_caption_locale_gate(self):
        self.check("gossip_audio")

    def test_places_text_and_voice_with_audio_metadata(self):
        self.check("places_audio")

    def test_bosses_text_only_pack_is_safe_but_client_gated(self):
        self.check("bosses_text")

    def test_bosses_audio_caption_mismatch_fallback_and_missing_core(self):
        self.check("bosses_audio")

    def test_core_text_only_admission_is_not_module_support(self):
        self.check("core_text_only")


if __name__ == "__main__":
    unittest.main()
