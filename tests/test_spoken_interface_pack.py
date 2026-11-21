"""Validate the Interface Pack against the pinned Spoken loader and formatter."""
from pathlib import Path
import tempfile
import unittest

from lua_runtime import run_lua
from test_stage1 import LOCK, ROOT, git, quote_lua

PACK = ROOT / "addons" / "Spoken_Interface_UA"
PIN = LOCK["spoken"]["revision"]
CORE = "addons/Spoken/"
ENGLISH = (
    CORE + "Strings.lua",
    "addons/Spoken_Quests/Strings.lua",
    *(f"addons/Spoken_{module}/Locale/enUS.lua"
      for module in ("Places", "Readables", "Bosses", "Developer")),
)
CHECKER = "scripts/interface/strings.lua"

# The upstream chunks use WoW's Lua 5.1 environment API. Our runner uses Lua 5.4.
SETFENV = """
function setfenv(chunk, env)
    if type(chunk) == "number" then chunk = debug.getinfo(chunk + 1, "f").func end
    local index = 1
    while debug.getupvalue(chunk, index) do
        if debug.getupvalue(chunk, index) == "_ENV" then
            debug.upvaluejoin(chunk, index, function() return env end, 1)
            break
        end
        index = index + 1
    end
    return chunk
end
"""


class SpokenInterfacePackTests(unittest.TestCase):
    def test_upstream_checker_for_keys_and_numbered_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for path in (*ENGLISH, CHECKER):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(git("show", f"{PIN}:{path}"))
            checker = quote_lua((root / CHECKER).as_posix())
            run_lua(SETFENV + f"""
arg = {{[0] = {checker}, "check", "ukUA", {quote_lua(PACK.as_posix())}}}
print = function() end
local checked = false
os.exit = function(status)
    assert(status == 0, "Upstream interface checker rejected the pack")
    checked = true
end
dofile(arg[0])
assert(checked)
""")

    def test_load_on_demand_english_fallback_and_independent_language_choices(self):
        toc = (PACK / f"{PACK.name}.toc").read_text(encoding="utf-8")
        sources = "local sources = {}\n"
        for filename in ("Languages.lua", "Interface.lua", "Texts.lua", "API.lua", "Strings.lua"):
            blob = git("show", f"{PIN}:{CORE}{filename}").decode("utf-8")
            sources += f"sources[ {quote_lua(filename)} ] = {quote_lua(blob)}\n"
        run_lua(SETFENV + sources + f"local toc = {quote_lua(toc)}\n"
                + f"local pack = {quote_lua((PACK / 'Interface.lua').as_posix())}\n" + r"""
local metadata = {}
local files = {}
for line in toc:gmatch("[^\r\n]+") do
    local key, value = line:match("^## ([^:]+): (.+)$")
    if key then metadata[key] = value else files[#files + 1] = line end
end
assert(metadata.Dependencies == "Spoken" and metadata.LoadOnDemand == "1")
assert(metadata["X-Spoken-Interface"] == "ukUA" and metadata["X-Spoken-InterfaceFormat"] == "1")
assert(#files == 1 and files[1] == "Interface.lua")

local function offered(choices, code)
    for _, choice in ipairs(choices) do if choice == code then return true end end
    return false
end

local function boot(choice, drawsUkrainian, installed)
    local loads = 0
    Spoken = {}
    SpokenSettings = { global = { InterfaceLanguage = choice } }
    SpokenEnv = setmetatable({
        Spoken = Spoken,
        Addon = {},
        Developer = { Log = function(_, _, message) error(message) end },
        Options = {
            NameBindings = function() end,
            LanguageDraws = function(_, code) return drawsUkrainian and code == "ukUA" end,
        },
    }, { __index = _G })
    GetLocale = function() return "enUS" end
    GetNumAddOns = function() return installed and 1 or 0 end
    GetAddOnInfo = function() return "Spoken_Interface_UA", nil, nil, true end
    GetAddOnMetadata = function(_, key) return metadata[key] end
    LoadAddOn = function(folder)
        assert(folder == "Spoken_Interface_UA")
        loads = loads + 1
        dofile(pack)
        return true
    end
    for _, filename in ipairs({"Languages.lua", "Interface.lua", "Texts.lua", "API.lua", "Strings.lua"}) do
        assert(load(sources[filename], filename))()
    end
    SpokenEnv.Interface:Load()
    return SpokenEnv, loads
end

local env, loads = boot(nil, true, true)
assert(loads == 0 and Spoken:InterfaceLanguage() == "enUS" and env.L.PLAY == "Play")
assert(offered(env.Interface:Choices(), "ukUA"))
assert(not offered(env.Texts:Choices(), "ukUA"))
assert(#Spoken:Language("ukUA").folders == 0)

env, loads = boot("ukUA", true, true)
assert(loads == 1 and Spoken:InterfaceLanguage() == "ukUA" and Spoken:InterfaceBase() == "enUS")
assert(env.L.PLAY == "Відтворити")
assert(env.L.OPT_INTERFACE_LANGUAGE == "Мова інтерфейсу")
assert(env.L.SEARCH_WHERE == "%1$s > %2$s")
local quests = { QUEST_PART_ACCEPT = "Description", QUESTS_GROUP_LIBRARY = "Library Books" }
Spoken:ApplyInterfaceStrings("Quests", quests)
assert(quests.QUEST_PART_ACCEPT == "Опис" and quests.QUESTS_GROUP_LIBRARY == "Library Books")
assert(GetLocale() == "enUS")

env, loads = boot(nil, false, true)
assert(loads == 0 and not offered(env.Interface:Choices(), "ukUA"))
env, loads = boot("ukUA", true, false)
assert(loads == 0 and Spoken:InterfaceLanguage() == "enUS" and env.L.PLAY == "Play")
""")
