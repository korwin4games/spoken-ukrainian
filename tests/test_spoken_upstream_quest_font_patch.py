"""Validate the proposed official Spoken Quest Compendium font fix.

The patch is NOT installed into the player by Spoken Ukrainian. Tests use a
temporary copy of the pinned upstream source and the actual Lua method.
"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from lua_runtime import run_lua
from test_stage1 import LOCK, ROOT, git


UPSTREAM_QUEST_TAB = "addons/Spoken_Quests/UI/QuestsTab.lua"
PATCH = ROOT / "docs/upstream/spoken-quests-compendium-font.patch"


def patched_quest_tab():
    pin = LOCK["spoken"]["revision"]
    original = git("show", f"{pin}:{UPSTREAM_QUEST_TAB}").decode("utf-8")
    with tempfile.TemporaryDirectory() as temp:
        checkout = Path(temp)
        file = checkout / UPSTREAM_QUEST_TAB
        file.parent.mkdir(parents=True)
        file.write_text(original, encoding="utf-8")
        for arguments in (("--check", str(PATCH)), (str(PATCH),)):
            subprocess.run(
                ["git", "-C", str(checkout), "apply", *arguments],
                check=True, capture_output=True, text=True,
            )
        patched = file.read_text(encoding="utf-8")
    return original, patched


class QuestCompendiumUpstreamPatchTests(unittest.TestCase):
    def test_patch_applies_to_pinned_spoken_without_touching_checkout(self):
        original, patched = patched_quest_tab()
        self.assertIn("page = C.NewPage(holder, ns)", original)
        self.assertNotIn("page = C.NewPage(holder, ns)", patched)
        self.assertIn("page = C.NewPage(holder, QuestsTab)", patched)
        self.assertEqual(patched.count("function QuestsTab:FontFor("), 1)
        self.assertNotIn("local _, ns = ...", patched)
        self.assertIn("Spoken:FontForLanguage(fontObject, language, self)", patched)
        # Only the intended page ownership and font adapter may differ.
        method = re.search(
            r"^-- The Compendium page asks.*?^end\n\n",
            patched, re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(method)
        self.assertEqual(
            patched.replace(method.group(), "")
            .replace("page = C.NewPage(holder, QuestsTab)", "page = C.NewPage(holder, ns)")
            .replace("local VO = VoiceOver", "local _, ns = ...\nlocal VO = VoiceOver", 1),
            original,
        )

    def test_adapter_resolves_ukrainian_and_english_fonts(self):
        _, patched = patched_quest_tab()
        method = re.search(
            r"^function QuestsTab:FontFor\(fontObject\)\n.*?^end$",
            patched, re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(method)
        script = r"""
local selected = "ukUA"
local packFace = [[Interface\AddOns\Spoken_Quest_UA\NotoSans-Regular.ttf]]
local titleFont = [[Fonts\MORPHEUS.ttf]]
local bodyFont = [[Fonts\FRIZQT__.ttf]]
local function Font(path)
    return { GetFont = function() return path end }
end
local VO = { Language = { GetTextLanguage = function() return selected, true end } }
local QuestsTab = {}
local called = {}
Spoken = {
    FontForLanguage = function(self, object, code, cache)
        assert(cache == QuestsTab)
        called[#called + 1] = { code = code, path = object:GetFont() }
        if code == "ukUA" then return packFace end
        return object:GetFont()
    end,
}
""" + method.group() + r"""
assert(QuestsTab:FontFor(Font(titleFont)) == packFace)
assert(QuestsTab:FontFor(Font(bodyFont)) == packFace)
assert(#called == 2 and called[1].code == "ukUA")
selected = "enUS"
assert(QuestsTab:FontFor(Font(titleFont)) == titleFont)
assert(QuestsTab:FontFor(Font(bodyFont)) == bodyFont)
Spoken = nil
selected = "ukUA"
assert(QuestsTab:FontFor(Font(bodyFont)) == bodyFont)
assert(QuestsTab:FontFor(nil) == nil)
"""
        run_lua(script)

    def test_shared_upstream_page_supports_owner_fonts(self):
        pin = LOCK["spoken"]["revision"]
        compendium = git(
            "show", f"{pin}:addons/Spoken/UI/Compendium.lua",
        ).decode("utf-8")
        textview = git(
            "show", f"{pin}:addons/Spoken/UI/TextView.lua",
        ).decode("utf-8")
        self.assertIn("addon:FontFor(_G.QuestTitleFont)", compendium)
        self.assertIn("SpokenTextView.Create(frame, addon)", compendium)
        self.assertIn("owner:FontFor(fontObject)", textview)
        self.assertIn("slot.heading:SetFont(font,", textview)


if __name__ == "__main__":
    unittest.main()
