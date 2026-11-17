"""Synthetic ClassicUA Gossip source/hash and WoW Forever UI contracts."""
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

from lua_runtime import run_lua
from test_crosswalk import Fixture
from tools import build_ukrainian as builder


class GossipTextsTests(unittest.TestCase):
    def fixture_state(self, allow_ai=True):
        fixture = Fixture().add(
            "gossip", "classic",
            '{["!common"]={[991562674]="Спільна відповідь."},'
            '[42]={[3995595454]="Вітаю, {ім\'я}!",'
            '[3246404856]="Ось де заїзд.",'
            '["!code"]={["unknown-pattern"]=3995595454}},'
            '[99]={[3974570973]="ШІ-відповідь",ai=true}}')
        policy = Mock()
        policy.allows_ai_transations.return_value = allow_ai
        return SimpleNamespace(dataset=fixture.dataset,
                               source=fixture.inventory(), policy=policy)

    def test_only_audited_exact_hashes_and_ai_opt_in(self):
        state = self.fixture_state(allow_ai=False)
        data = builder.local_gossip_texts(state)
        self.assertEqual(data["common"], {991562674: "Спільна відповідь."})
        self.assertEqual(data["byNpc"][42][3995595454], "Вітаю, {ім'я}!")
        self.assertEqual(data["byNpc"][42][3246404856], "Ось де заїзд.")
        self.assertNotIn(99, data["byNpc"])
        self.assertEqual(len(data["byNpc"][42]), 2)
        self.assertEqual(set(data["byNpc"][42]), {3995595454, 3246404856})
        self.assertIn(99, builder.local_gossip_texts(self.fixture_state(True))["byNpc"])
        # Source file/revision must be pinned, never emitted from edited data.
        state.source.files["classic/gossip.lua"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "unverified_classicua_gossip_source"):
            builder.local_gossip_texts(state)

    def test_synthetic_gossip_module_hashes_npc_reply_shift_and_fallback(self):
        data = builder.local_gossip_texts(self.fixture_state())
        generated = builder.render_gossip_lua(data)
        self.assertIn("Вітаю", generated.decode())
        self.assertNotIn("unknown-pattern", generated.decode())
        entries = builder.template_entries(
            builder.render_quest_lua({}, "a" * 40), generated)
        self.assertIn("Spoken_Quests_UA/GossipTranslations.lua", entries)
        self.assertIn("Spoken_Quests_UA/GossipFrame.lua", entries)
        script = r'''
_G = _G or _ENV
local shifted, classicua = false, false
local npcID = 42
function UnitGUID(unit)
    assert(unit == "npc")
    return "Creature-0-1-2-3-" .. npcID .. "-00001"
end
function IsShiftKeyDown() return shifted end
function IsAddOnLoaded(name) return name == "ClassicUA" and classicua end
local frames = {}
function CreateFrame()
    local f = { events = {}, scripts = {} }
    function f:RegisterEvent(event) self.events[event] = true end
    function f:SetScript(name, script) self.scripts[name] = script end
    function f:Fire(event)
        assert(self.events[event])
        self.scripts.OnEvent(self, event)
    end
    table.insert(frames, f)
    return f
end
local function stringWidget()
    local w = {text = ""}
    function w:SetText(value) self.text = value end
    function w:GetText() return self.text end
    function w:GetHeight() return math.ceil(#self.text / 12) * 15 end
    return w
end
local function greetingFrame()
    local f = {GreetingText = stringWidget()}
    function f:SetSize(_, height) self.height = height end
    function f:SetHeight(height) self.height = height end
    return f
end
GossipGreetingTextMixin = {
    Setup = function(frame, text)
        frame.GreetingText:SetText(text)
        frame:SetSize(270, frame.GreetingText:GetHeight())
    end
}
GossipOptionButtonMixin = {
    Setup = function(row, info)
        row:SetText("> " .. info.name)
        row:Resize()
    end
}
local hooks = {}
function hooksecurefunc(target, functionName, callback)
    if type(target) == "string" then
        assert(type(_G[target]) == "function")
        local original = _G[target]
        _G[target] = function(...)
            original(...)
            callback(...)
        end
    else
        local original = target[functionName]
        assert(type(original) == "function")
        target[functionName] = function(self, ...)
            original(self, ...)
            callback(self, ...)
        end
    end
end
QuestFrameGreetingPanel_OnShow = function()
    GreetingText:SetText("Hello traveler.")
end
GreetingText = stringWidget()
SpokenUkrainian = {ExpandQuestText = function(self, text)
    return (text:gsub("{ім'я}", "Тест"))
end}
'''
        for path in ("Spoken_Quests_UA/GossipTranslations.lua",
                     "Spoken_Quests_UA/GossipFrame.lua"):
            script += "\n" + entries[path].decode("utf-8") + "\n"
        script += r'''
assert(#frames == 1)
local eventFrame = frames[1]
local greet = greetingFrame()
GossipGreetingTextMixin.Setup(greet, "Hello traveler.")
assert(greet.GreetingText:GetText() == "Вітаю, Тест!")
assert(greet.height == greet.GreetingText:GetHeight())
shifted = true
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(greet.GreetingText:GetText() == "Hello traveler.")
shifted = false
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(greet.GreetingText:GetText() == "Вітаю, Тест!")
-- English whitespace normalization matches ClassicUA: hash of doubled spaces.
GossipGreetingTextMixin.Setup(greet, "Hello  traveler.  ")
assert(greet.GreetingText:GetText() == "Вітаю, Тест!")
shifted = true
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(greet.GreetingText:GetText() == "Hello  traveler.  ")
shifted = false
eventFrame:Fire("MODIFIER_STATE_CHANGED")
local reply = stringWidget()
reply.count = 0
function reply:Resize() self.count = self.count + 1 end
GossipOptionButtonMixin.Setup(reply, {name = "Where is the inn?"})
assert(reply:GetText() == "> Ось де заїзд.")
assert(reply.count >= 2)
shifted = true
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(reply:GetText() == "> Where is the inn?")
shifted = false
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(reply:GetText() == "> Ось де заїзд.")
-- Global !common entries translate only when an NPC is present.
GossipOptionButtonMixin.Setup(reply, {name = "Tell me more."})
assert(reply:GetText() == "> Спільна відповідь.")
-- Two different NPCs must not share per-NPC mappings.
npcID = 777
GossipOptionButtonMixin.Setup(reply, {name = "Where is the inn?"})
assert(reply:GetText() == "> Where is the inn?")
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(reply:GetText() == "> Where is the inn?")
-- The original Quest Greeting header is also eligible, outside Quest accept.
npcID = 42
QuestFrameGreetingPanel_OnShow()
assert(GreetingText:GetText() == "Вітаю, Тест!")
shifted = true
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(GreetingText:GetText() == "Hello traveler.")
shifted = false
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(GreetingText:GetText() == "Вітаю, Тест!")
-- Missing NPC GUID => remain English (no unverified NPC fallback).
UnitGUID = function() return nil end
GossipGreetingTextMixin.Setup(greet, "Hello traveler.")
assert(greet.GreetingText:GetText() == "Hello traveler.")
UnitGUID = function() return "Creature-0-1-2-3-42-00001" end
-- ClassicUA installed: no competing writes to Gossip fields.
classicua = true
GossipOptionButtonMixin.Setup(reply, {name = "Where is the inn?"})
assert(reply:GetText() == "> Where is the inn?")
classicua = false
-- Closing NPC clears saved originals before the next NPC.
eventFrame:Fire("GOSSIP_CLOSED")
GossipOptionButtonMixin.Setup(reply, {name = "Unknown option"})
assert(reply:GetText() == "> Unknown option")
shifted = true
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(reply:GetText() == "> Unknown option")
'''
        run_lua(script)

    def test_invalid_gossip_data_refused(self):
        for invalid in ({}, {"byNpc": {}}, {"byNpc": {-2: {1: "text"}}, "common": {}},
                        {"byNpc": {}, "common": {4294967291: "text"}}):
            with self.subTest(data=invalid), self.assertRaises(ValueError):
                builder.render_gossip_lua(invalid)


if __name__ == "__main__":
    unittest.main()
