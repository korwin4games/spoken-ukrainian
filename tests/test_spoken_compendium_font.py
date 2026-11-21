"""Exercise Spoken's pinned public font resolver with Quest pack metadata."""
import unittest

from lua_runtime import run_lua
from test_stage1 import LOCK, ROOT, git, quote_lua


class SpokenCompendiumFontTests(unittest.TestCase):
    def test_quest_text_pack_face_resolves_independently_of_interface_glyphs(self):
        pin = LOCK["spoken"]["revision"]
        folder = "Spoken_Quest_UA"
        toc = (ROOT / "addons" / folder / f"{folder}.toc").read_text(encoding="utf-8")
        metadata = dict(line.removeprefix("## ").split(": ", 1)
                        for line in toc.splitlines() if line.startswith("## ") and ": " in line)
        font = metadata["X-Spoken-LanguageFont"]
        self.assertTrue((ROOT / "addons" / folder / font).is_file())

        source = "local blobs = {}\n"
        for name in ("Languages", "Texts", "API"):
            blob = git("show", f"{pin}:addons/Spoken/{name}.lua").decode("utf-8")
            source += f"blobs.{name} = {quote_lua(blob)}\n"
        fields = ", ".join(f"[ {quote_lua(key)} ] = {quote_lua(value)}"
                           for key, value in metadata.items())
        path = quote_lua(f"Interface\\AddOns\\{folder}\\{font}")
        run_lua(source + f"local metadata = {{{fields}}}\nlocal packFace = {path}\n" + r"""
local stockTitle, stockBody = [[Fonts\Title.ttf]], [[Fonts\Body.ttf]]
local packDraws, bodyDraws = true, false
local function face(path) return { GetFont = function() return path end } end
local env = setmetatable({
    Spoken = {},
    Addon = {},
    GetLocale = function() return "enUS" end,
    GetNumAddOns = function() return 1 end,
    GetAddOnInfo = function() return "Spoken_Quest_UA", nil, nil, true end,
    GetAddOnMetadata = function(_, key) return metadata[key] end,
    Options = {
        LanguageDraws = function(_, code, path)
            assert(code == "ukUA")
            return (path == packFace and packDraws) or (path == stockBody and bodyDraws)
        end,
    },
    -- Lua 5.4 sets the same environment explicitly via load().
    setfenv = function() end,
}, { __index = _G })
for _, name in ipairs({"Languages", "Texts", "API"}) do
    assert(load(blobs[name], name, "t", env))()
end
local spoken = env.Spoken
local entry = spoken:Language("ukUA")
assert(#entry.texts == 1 and #entry.interfaces == 0 and #entry.folders == 0)
assert(entry.font == packFace)
assert(not spoken:LanguageDraws("ukUA"))
local cache = {}
assert(spoken:FontForLanguage(face(stockTitle), "ukUA", cache) == packFace)
assert(spoken:FontForLanguage(face(stockBody), "ukUA", cache) == packFace)
assert(spoken:FontForLanguage(face(stockTitle), "enUS", cache) == stockTitle)

bodyDraws = true
assert(spoken:FontForLanguage(face(stockBody), "ukUA", {}) == stockBody)
packDraws = false
assert(spoken:FontForLanguage(face(stockTitle), "ukUA", {}) == nil)
""")
