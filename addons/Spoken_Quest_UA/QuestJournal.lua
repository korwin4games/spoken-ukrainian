-- Forever journal widgets and refresh points verified in pinned ClassicUA.
local SU = assert(SpokenUkrainian)
local translations = assert(SU.QuestTranslations)
local details, titles = {}, {}
local detailID
local displayHooked, scrollHooked, titlesHideHooked, detailsHideHooked

local function ClassicUAIsActive()
    if IsAddOnLoaded then return IsAddOnLoaded("ClassicUA") end
    return C_AddOns and C_AddOns.IsAddOnLoaded and C_AddOns.IsAddOnLoaded("ClassicUA")
end

local function SelectedID()
    if QuestInfoFrame and QuestInfoFrame.questLog and C_QuestLog and C_QuestLog.GetSelectedQuest then
        local id = C_QuestLog.GetSelectedQuest()
        if type(id) == "number" and id > 0 then return id end
    end
end

local function Apply(widget, entry, useOriginal)
    local before = widget:GetText()
    if before ~= entry.original and before ~= entry.translated then return end
    local text = useOriginal and entry.original or entry.translated
    local button = entry.button
    local oldHeight = button and widget.GetHeight and widget:GetHeight()
    if not SU:UseQuestFont(widget, entry.font, not useOriginal) then text = entry.original end
    if before ~= text then widget:SetText(text) end
    if oldHeight and button.GetHeight and button.SetHeight then
        button:SetHeight(button:GetHeight() + widget:GetHeight() - oldHeight)
    end
end

local function Restore(entries, widget)
    local entry = entries[widget]
    if not entry then return end
    Apply(widget, entry, true)
    SU:UseQuestFont(widget, entry.font, false)
    entries[widget] = nil
end

local function Clear(entries)
    for widget in pairs(entries) do Restore(entries, widget) end
end

local function Capture(entries, widget, original, translated, id, button)
    if type(original) ~= "string" or original == "" or type(translated) ~= "string" then return end
    translated = SU:ExpandLocalQuestText(translated)
    if type(translated) ~= "string" or translated == "" then return end
    local entry = {original = original, translated = translated, id = id, button = button,
                   font = SU:CaptureQuestFont(widget)}
    entries[widget] = entry
    Apply(widget, entry, IsShiftKeyDown and IsShiftKeyDown())
end

local function UpdateDetails()
    Clear(details)
    detailID = not ClassicUAIsActive() and SelectedID() or nil
    local row = detailID and translations[detailID]
    if not row then return end
    local fields = {
        QuestInfoTitleHeader = row.title,
        QuestInfoDescriptionText = row.accept and row.accept.text,
        QuestInfoObjectivesText = row.objective,
    }
    for name, text in pairs(fields) do
        local widget = _G[name]
        if widget and widget.GetText and widget.SetText then
            Capture(details, widget, widget:GetText(), text, detailID)
        end
    end
end

local function UpdateTitles(scroll)
    Clear(titles)
    local pool = scroll.titleFramePool
    if ClassicUAIsActive() or not pool or not pool.EnumerateActive then return end
    for button in pool:EnumerateActive() do
        local widget = button.Text
        local id = button.questID
        local row = id and translations[id]
        local nativeTitle = button.info and button.info.title
        if widget and widget.GetText and widget.SetText and row and row.title
                and type(nativeTitle) == "string" and nativeTitle ~= "" then
            local original = widget:GetText()
            local first, last
            if type(original) == "string" then first, last = original:find(nativeTitle, 1, true) end
            if first then
                local translation = original:sub(1, first - 1) .. row.title .. original:sub(last + 1)
                Capture(titles, widget, original, translation, id, button)
            end
        end
    end
end

local function Install()
    if type(hooksecurefunc) ~= "function" then return end
    if not displayHooked and type(QuestInfo_Display) == "function" then
        hooksecurefunc("QuestInfo_Display", UpdateDetails)
        displayHooked = true
    end
    if not scrollHooked and QuestScrollFrame and type(QuestScrollFrame.UpdateBackground) == "function" then
        hooksecurefunc(QuestScrollFrame, "UpdateBackground", UpdateTitles)
        scrollHooked = true
    end
    if not titlesHideHooked and QuestScrollFrame and QuestScrollFrame.HookScript then
        QuestScrollFrame:HookScript("OnHide", function() Clear(titles) end)
        titlesHideHooked = true
    end
    if not detailsHideHooked and QuestInfoFrame and QuestInfoFrame.HookScript then
        QuestInfoFrame:HookScript("OnHide", function() Clear(details) end)
        detailsHideHooked = true
    end
end

local listener = CreateFrame("Frame")
for _, event in ipairs({"PLAYER_LOGIN", "ADDON_LOADED", "QUEST_LOG_UPDATE", "MODIFIER_STATE_CHANGED"}) do
    listener:RegisterEvent(event)
end
listener:SetScript("OnEvent", function(_, event)
    if event == "PLAYER_LOGIN" or event == "ADDON_LOADED" then Install() end
    if ClassicUAIsActive() then
        Clear(details)
        Clear(titles)
        return
    end
    if not detailID or detailID ~= SelectedID() then Clear(details) end
    if event == "MODIFIER_STATE_CHANGED" then
        local shift = IsShiftKeyDown and IsShiftKeyDown()
        for widget, entry in pairs(details) do Apply(widget, entry, shift) end
        for widget, entry in pairs(titles) do
            if entry.button.questID == entry.id then Apply(widget, entry, shift)
            else Restore(titles, widget) end
        end
    end
end)
Install()
