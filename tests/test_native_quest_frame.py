"""Synthetic WoW Forever FontString/QuestFrame contract for Issue #19."""
from pathlib import Path
import unittest

from lua_runtime import run_lua
from tools import build_ukrainian as builder


class NativeQuestFrameTests(unittest.TestCase):
    def test_native_window_shift_and_quest_lifecycle(self):
        preview = {
            42: {"title": "Вигадана українська назва",
                 "objective": "Збери {стать:перший:першу} річ.",
                 "accept": {"text": "Вітаю, {ім'я}!", "reviewed": False},
                 "progress": {"text": "Як просувається робота?", "reviewed": False},
                 "complete": {"text": "Дякую, {ім'я}!", "reviewed": False}},
            99: {"title": "Інша назва", "accept": {"text": "Інший опис", "reviewed": False}},
        }
        sources = builder.template_entries(
            builder.render_quest_lua(preview, "a" * 40))
        lua = r'''
_G = _G or _ENV
SlashCmdList = {}
DEFAULT_CHAT_FRAME = {AddMessage = function() end}
local questID, shift, sex, classicUA = 42, false, 2, false
function GetQuestID() return questID end
function IsShiftKeyDown() return shift end
function UnitName() return "Гравець" end
function UnitSex() return sex end
function UnitClass() return "Paladin", "PALADIN" end
function UnitRace() return "Orc", "Orc" end
function IsAddOnLoaded(addon) return addon == "ClassicUA" and classicUA end
function GetTitleText() return "Native title" end
local frames = {}
function CreateFrame()
    local frame = { registered = {}, scripts = {}, hooks = {} }
    function frame:RegisterEvent(event) self.registered[event] = true end
    function frame:SetScript(event, callback) self.scripts[event] = callback end
    function frame:HookScript(event, callback)
        self.hooks[event] = self.hooks[event] or {}
        table.insert(self.hooks[event], callback)
    end
    function frame:Fire(event, ...)
        if self.scripts.OnEvent then self.scripts.OnEvent(self, event, ...) end
        for _, callback in ipairs(self.hooks.OnEvent or {}) do
            callback(self, event, ...)
        end
    end
    function frame:IsShown() return self.visible ~= false end
    function frame:Show()
        self.visible = true
        for _, callback in ipairs(self.hooks.OnShow or {}) do callback(self) end
    end
    function frame:Hide()
        self.visible = false
        for _, callback in ipairs(self.hooks.OnHide or {}) do callback(self) end
    end
    function frame:CreateTexture() return setmetatable({}, {__index = function()
        return function() end end}) end
    function frame:CreateFontString() return setmetatable({}, {__index = function()
        return function() end end}) end
    setmetatable(frame, {__index = function(_, name)
        if name == "GetStringHeight" then return function() return 24 end end
        return function() end
    end})
    table.insert(frames, frame)
    return frame
end
QuestFrame = CreateFrame()
local function font(name)
    local object = {content = "", callbacks = {}}
    function object:GetText() return self.content end
    function object:SetText(text)
        self.content = text
        for _, cb in ipairs(self.callbacks) do cb(self, text) end
    end
    _G[name] = object
    return object
end
local title = font("QuestInfoTitleHeader")
local description = font("QuestInfoDescriptionText")
local objectives = font("QuestInfoObjectivesText")
local reward = font("QuestInfoRewardText")
local progressTitle = font("QuestProgressTitleText")
local progress = font("QuestProgressText")
function hooksecurefunc(widget, name, callback)
    assert(name == "SetText")
    table.insert(widget.callbacks, callback)
end
VoiceOver = {DataModules = {Register = function() end}}
UIParent = QuestFrame
'''
        for name in (
                "Spoken_Ukrainian/Core.lua",
                "Spoken_Quests_UA/Translations.lua",
                "Spoken_Quests_UA/Module.lua",
                "Spoken_Quests_UA/NativeQuestFrame.lua"):
            lua += "\n" + sources[name].decode("utf-8") + "\n"
        lua += r'''
local nativeListener
for _, item in ipairs(frames) do
    if item.registered.MODIFIER_STATE_CHANGED then nativeListener = item end
end
assert(nativeListener, "native QuestFrame event handler not installed")
local function moment(event)
    nativeListener:Fire(event)
end
local function mod(held)
    shift = held
    nativeListener:Fire("MODIFIER_STATE_CHANGED", "LSHIFT", held and 1 or 0)
end
-- NPC accept: original text first, Ukrainization only on exact imported ID.
moment("QUEST_DETAIL")
title:SetText("English name")
description:SetText("Hello $N!")
objectives:SetText("Retrieve an item.")
assert(title:GetText() == "Вигадана українська назва")
assert(description:GetText() == "Вітаю, Гравець!")
assert(objectives:GetText() == "Збери перший річ.")
-- Existing title/progress/reward fields outside the current stage untouched.
progress:SetText("Unrelated progress")
reward:SetText("Unrelated reward")
assert(progress:GetText() == "Unrelated progress")
assert(reward:GetText() == "Unrelated reward")
mod(true)
assert(title:GetText() == "English name")
assert(description:GetText() == "Hello $N!")
assert(objectives:GetText() == "Retrieve an item.")
-- Native updates while Shift held must be tracked as new originals.
description:SetText("Hello again from client!")
assert(description:GetText() == "Hello again from client!")
mod(false)
assert(description:GetText() == "Вітаю, Гравець!")
assert(title:GetText() == "Вигадана українська назва")
-- Many toggles: no hooks stack up; no original contamination.
for i = 1, 3 do
    mod(true)
    assert(description:GetText() == "Hello again from client!")
    mod(false)
    assert(description:GetText() == "Вітаю, Гравець!")
end
-- Progress stage: no bleed from accept.
moment("QUEST_PROGRESS")
progressTitle:SetText("English title progress")
progress:SetText("Still working?")
assert(progressTitle:GetText() == "Вигадана українська назва")
assert(progress:GetText() == "Як просувається робота?")
mod(true)
assert(progressTitle:GetText() == "English title progress")
assert(progress:GetText() == "Still working?")
mod(false)
-- Complete: correct distinct spoken row in native reward.
moment("QUEST_COMPLETE")
reward:SetText("Thank you, $N.")
assert(reward:GetText() == "Дякую, Гравець!")
mod(true)
assert(reward:GetText() == "Thank you, $N.")
mod(false)
-- No data / unmatched QuestID: never substitute text.
moment("QUEST_FINISHED")
questID = 77777
moment("QUEST_DETAIL")
description:SetText("Unknown quest stays English")
title:SetText("Unknown native title")
assert(description:GetText() == "Unknown quest stays English")
assert(title:GetText() == "Unknown native title")
mod(true); mod(false)
assert(description:GetText() == "Unknown quest stays English")
-- Other imported quest gets ONLY its own row.
questID = 99
moment("QUEST_DETAIL")
description:SetText("Other English text")
assert(description:GetText() == "Інший опис")
title:SetText("Other English title")
assert(title:GetText() == "Інша назва")
-- Quest closed: clear state and never translate unrelated panels.
QuestFrame:Hide()
questID = 42
description:SetText("Closed text remains English")
assert(description:GetText() == "Closed text remains English")
QuestFrame:Show()
moment("QUEST_DETAIL")
description:SetText("Fresh English line")
assert(description:GetText() == "Вітаю, Гравець!")
-- Avoid a SetText ping-pong if ClassicUA AddOn is present.
moment("QUEST_FINISHED")
classicUA = true
moment("QUEST_DETAIL")
description:SetText("ClassicUA owns text")
assert(description:GetText() == "ClassicUA owns text")
mod(true); mod(false)
assert(description:GetText() == "ClassicUA owns text")
classicUA = false
QuestFrame:Hide()
questID = 42
-- Some retail-derived clients set native FontStrings before their frame shows.
moment("QUEST_DETAIL")
title:SetText("Title written while hidden")
description:SetText("Description written while hidden")
assert(description:GetText() == "Description written while hidden")
QuestFrame:Show()
assert(title:GetText() == "Вигадана українська назва")
assert(description:GetText() == "Вітаю, Гравець!")
mod(true)
assert(description:GetText() == "Description written while hidden")
mod(false)
assert(description:GetText() == "Вітаю, Гравець!")
'''
        run_lua(lua)


if __name__ == "__main__":
    unittest.main()
