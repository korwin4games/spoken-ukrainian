"""WoW Forever Quest Greeting and Gossip title-only ID mapping: synthetic Lua."""
import unittest
from lua_runtime import run_lua
from tools import build_ukrainian as builder


class GossipQuestTitleTests(unittest.TestCase):
    def test_gossip_exact_questid_faction_shift_fallback_and_quest_greeting(self):
        files = builder.template_entries(builder.render_quest_lua(
            {}, "a" * 40,
            gossip_titles={
                "horde": {42: "Перші випробування", 97279: "Загублена зброя"},
                "alliance": {42: "Випробування альянсу"},
            }))
        script = r'''
_G = _G or _ENV
local shifted = false
local classicua = false
local faction = "Horde"
UnitFactionGroup = function() return faction end
IsShiftKeyDown = function() return shifted end
IsAddOnLoaded = function(name) return name == "ClassicUA" and classicua end
SpokenUkrainian = {
    ExpandQuestText = function(_, str) return str end,
}
local createdFrames = {}
function CreateFrame()
    local frame = {callbacks = {}, registered = {}}
    function frame:RegisterEvent(event) self.registered[event] = true end
    function frame:SetScript(name, cb) self.callbacks[name] = cb end
    function frame:Fire(event)
        assert(self.registered[event])
        self.callbacks.OnEvent(self, event)
    end
    table.insert(createdFrames, frame)
    return frame
end
local hooks = {}
function hooksecurefunc(obj, method, callback)
    if type(obj) == "string" then
        hooks[obj] = callback
        return
    end
    local original = obj[method]
    assert(type(original) == "function")
    obj[method] = function(self, ...)
        original(self, ...)
        callback(self, ...)
    end
end
local function button(index)
    local row = {text = "", index = index, visible = true, sizeCount = 0}
    function row:GetText() return self.text end
    function row:SetText(value) self.text = value end
    function row:Resize() self.sizeCount = self.sizeCount + 1 end
    function row:GetTextHeight() return math.ceil(#self.text / 22) * 14 end
    function row:SetHeight(value) self.height = value end
    function row:GetHeight() return self.height end
    row.Icon = { GetHeight = function() return 16 end }
    -- Simulates Blizzard's anchor chain: each row's top is relative
    -- to the preceding button's bottom, not a static pixel position.
    function row:TopY()
        return self.previous and (self.previous:TopY() - self.previous:GetHeight() - 2) or 0
    end
    function row:IsShown() return self.visible end
    function row:GetID() return self.index end
    return row
end
GossipAvailableQuestButtonMixin = {
    Setup = function(row, info) row:SetText("! " .. info.title) end,
}
GossipActiveQuestButtonMixin = {
    Setup = function(row, info) row:SetText("? " .. info.title) end,
}
local first, second = button(1), button(2)
local panelHooks = {}
local pool = {}
function pool:EnumerateActive()
    local i = 0
    local buttons = {first, second}
    return function()
        i = i + 1
        return buttons[i]
    end
end
QuestFrameGreetingPanel = {titleButtonPool = pool}
function QuestFrameGreetingPanel:HookScript(name, callback)
    panelHooks[name] = callback
end
QuestFrameGreetingPanel_OnShow = function() end
GetAvailableQuestInfo = function(id)
    return "English", 0, 0, 0, id == 1 and 97279 or 42
end
GetActiveQuestID = function(id) return id == 1 and 97279 or 42 end
'''
        for name in ("Spoken_Quests_UA/Translations.lua",
                     "Spoken_Quests_UA/GossipQuestTitles.lua"):
            script += "\n" + files[name].decode("utf-8") + "\n"
        script += r'''
assert(#createdFrames == 1)
local eventFrame = createdFrames[1]
local info = {questID = 97279, title = "Wayward Weapons"}
GossipAvailableQuestButtonMixin.Setup(first, info)
assert(first:GetText() == "! Загублена зброя")
shifted = true
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(first:GetText() == "! Wayward Weapons")
shifted = false
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(first:GetText() == "! Загублена зброя")
-- Reused pooled button must not carry text for old QuestID.
GossipAvailableQuestButtonMixin.Setup(first, {questID = 42, title = "Cutting Teeth"})
assert(first:GetText() == "! Перші випробування")
GossipAvailableQuestButtonMixin.Setup(second, {questID = 777, title = "Unknown Quest"})
assert(second:GetText() == "! Unknown Quest")
-- Captured original includes decorative glyphs; Shift preserves it.
GossipActiveQuestButtonMixin.Setup(first, {questID = 97279, title = "Wayward Weapons"})
assert(first:GetText() == "? Загублена зброя")
shifted = true
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(first:GetText() == "? Wayward Weapons")
shifted = false
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(first:GetText() == "? Загублена зброя")
-- The character's faction is consulted live.
faction = "Alliance"
GossipAvailableQuestButtonMixin.Setup(first, {questID = 42, title = "Cutting Teeth"})
assert(first:GetText() == "! Випробування альянсу")
GossipAvailableQuestButtonMixin.Setup(first, {questID = 97279, title = "Wayward Weapons"})
assert(first:GetText() == "! Wayward Weapons") -- no Alliance title
faction = "Horde"
-- ClassicUA owns Gossip UI when installed, to avoid competing hooks.
classicua = true
GossipAvailableQuestButtonMixin.Setup(first, {questID = 97279, title = "Wayward Weapons"})
assert(first:GetText() == "! Wayward Weapons")
classicua = false
-- QuestFrameGreetingPanel buttons do NOT have Gossip mixin Resize().
-- A long translated title must grow the row; the next anchored button
-- must move automatically, then return when Shift shows shorter English.
local longTitle = "Довга українська назва квесту з багатьма словами для перевірки перенесення рядків"
SpokenUkrainian.GossipQuestTitles.horde[97279] = longTitle
first.Resize = nil
second.Resize = nil
first:SetText("Wayward Weapons")
second:SetText("Cutting Teeth")
first.isActive = 0
second.isActive = 1
second.previous = first
first:SetHeight(math.max(first:GetTextHeight() + 2, first.Icon:GetHeight()))
second:SetHeight(math.max(second:GetTextHeight() + 2, second.Icon:GetHeight()))
local originalHeight = first:GetHeight()
local originalSecondTop = second:TopY()
panelHooks.OnShow()
assert(first:GetText() == longTitle)
assert(second:GetText() == "Перші випробування")
assert(first:GetHeight() > originalHeight, "localized first row height not recomputed")
assert(second:GetHeight() > 16, "localized second row height not recomputed")
assert(second:TopY() == -first:GetHeight() - 2)
assert(second:TopY() < originalSecondTop, "next row did not reflow")
local localizedHeight = first:GetHeight()
shifted = true
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(first:GetText() == "Wayward Weapons")
assert(second:GetText() == "Cutting Teeth")
assert(first:GetHeight() == originalHeight, "Shift must restore original height")
assert(second:GetHeight() == 16)
assert(second:TopY() == originalSecondTop)
shifted = false
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(first:GetText() == longTitle)
assert(second:GetText() == "Перші випробування")
assert(first:GetHeight() == localizedHeight)
assert(second:TopY() == -localizedHeight - 2)
-- Rescanning while already translated must not replace the cached
-- English Shift original with the Ukrainian text or duplicate line breaks.
panelHooks.OnShow()
shifted = true
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(first:GetText() == "Wayward Weapons")
shifted = false
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(first:GetText() == longTitle)
-- Reuse the pooled button for an untranslated quest and clear state:
-- it must keep its native text without resizing our cached old row.
first:SetText("Untranslated quest")
first.isActive = 0
GetAvailableQuestInfo = function(id)
    return "English", 0, 0, 0, id == 1 and 77777 or 42
end
panelHooks.OnShow()
assert(first:GetText() == "Untranslated quest")
eventFrame:Fire("GOSSIP_CLOSED")
first:SetText("Unrelated NPC")
eventFrame:Fire("MODIFIER_STATE_CHANGED")
assert(first:GetText() == "Unrelated NPC")
'''
        run_lua(script)


if __name__ == "__main__":
    unittest.main()
