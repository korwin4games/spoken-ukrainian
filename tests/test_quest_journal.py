from unittest import TestCase

from lua_runtime import run_lua
from tools.build_ukrainian import render_quest_lua, template_entries


class QuestJournalTests(TestCase):
    def test_forever_details_recycled_title_shift_and_font(self):
        entries = template_entries(render_quest_lua({
            42: {"title": "Їжак", "objective": "Знайди ґудзик.",
                 "accept": {"text": "і ї є ґ І Ї Є Ґ", "reviewed": True}},
        }, "a" * 40))
        code = r'''
SpokenUkrainian = {ExpandQuestText = function(_, text) return text end}
local shift, id = false, 42
function IsShiftKeyDown() return shift end
C_QuestLog = {GetSelectedQuest = function() return id end}
local function Widget()
    local w = {path = "Native", size = 14, flags = "OUTLINE"}
    function w:GetFont() return self.path, self.size, self.flags end
    function w:SetFont(path, size, flags) self.path, self.size, self.flags = path, size, flags end
    function w:SetText(text) self.text = text end
    function w:GetText() return self.text end
    return w
end
local function frame()
    return {HookScript = function(self, event, fn) self[event] = fn end}
end
QuestInfoFrame = frame()
QuestInfoFrame.questLog = true
QuestInfoTitleHeader, QuestInfoDescriptionText, QuestInfoObjectivesText = Widget(), Widget(), Widget()
function QuestInfo_Display(title, description)
    QuestInfoTitleHeader:SetText(title)
    QuestInfoDescriptionText:SetText(description)
    QuestInfoObjectivesText:SetText("Actual objective.")
end
local row = {questID = 42, info = {title = "Hedgehog"}, Text = Widget()}
QuestScrollFrame = frame()
QuestScrollFrame.titleFramePool = {EnumerateActive = function()
    local unread = true
    return function() if unread then unread = false; return row end end
end}
function QuestScrollFrame:UpdateBackground()
    row.Text:SetText("[42] " .. row.info.title)
end
function hooksecurefunc(target, name, fn)
    if type(target) == "string" then target, name, fn = _G, target, name end
    local original = target[name]
    target[name] = function(...) original(...); fn(...) end
end
local listener
function CreateFrame()
    listener = {RegisterEvent = function() end, SetScript = function(self, _, fn) self.fire = fn end}
    return listener
end
'''
        for file in ("Translations.lua", "QuestFont.lua", "QuestJournal.lua"):
            code += "\n" + entries[f"Spoken_Quest_UA/{file}"].decode()
        code += r'''
QuestInfo_Display("Hedgehog", "Native original B!")
QuestScrollFrame:UpdateBackground()
assert(QuestInfoDescriptionText:GetText() == "і ї є ґ І Ї Є Ґ")
assert(QuestInfoTitleHeader:GetText() == "Їжак")
assert(QuestInfoObjectivesText:GetText() == "Знайди ґудзик.")
assert(row.Text:GetText() == "[42] Їжак")
assert(row.Text.path:find("NotoSans-Regular.ttf", 1, true))
assert(row.Text.size == 14 and row.Text.flags == "OUTLINE")
shift = true
listener:fire("MODIFIER_STATE_CHANGED")
assert(QuestInfoDescriptionText:GetText() == "Native original B!")
assert(row.Text:GetText() == "[42] Hedgehog" and row.Text.path == "Native")
shift = false
listener:fire("MODIFIER_STATE_CHANGED")
assert(QuestInfoDescriptionText:GetText() == "і ї є ґ І Ї Є Ґ")
id, row.questID, row.info.title = 99, 99, "Another"
listener:fire("QUEST_LOG_UPDATE")
QuestInfo_Display("Another", "Untranslated quest.")
QuestScrollFrame:UpdateBackground()
listener:fire("MODIFIER_STATE_CHANGED")
assert(QuestInfoDescriptionText:GetText() == "Untranslated quest.")
assert(row.Text:GetText() == "[42] Another" and row.Text.path == "Native")
id = 42
QuestInfo_Display("Hedgehog", "Native original A!")
QuestInfoFrame:OnHide()
assert(QuestInfoDescriptionText:GetText() == "Native original A!")
'''
        run_lua(code)
