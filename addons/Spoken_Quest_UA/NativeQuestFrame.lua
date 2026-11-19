-- Native WoW Forever QuestFrame translation. Does NOT patch GetQuestText,
-- GetTitleText, Blizzard UI files or Spoken internals. No ClassicUA runtime.
-- Imported (possibly machine-provisional) Quest rows only. Not a release.
local SU = assert(SpokenUkrainian, "Spoken_Ukrainian dependency not loaded")
local translations = assert(SU.QuestTranslations, "Spoken Ukrainian Quest data missing")

-- Frame SetText hooks see the *original* rendered UI text, then replace only
-- that widget. A protected write guard prevents caching our own translation.
-- Shift temporarily restores the exact captured original; release restores UK.
local registered = {}
local originals = {}
local writing = {}
local activeID, activeMoment, pendingMoment
local frame
local nativeFields = {
    {name = "QuestInfoTitleHeader", events = {accept = true, complete = true},
     source = "title", info = true},
    {name = "QuestInfoDescriptionText", events = {accept = true},
     source = "accept", field = "text", info = true},
    {name = "QuestInfoObjectivesText", events = {accept = true},
     source = "objective", info = true},
    {name = "QuestInfoRewardText", events = {complete = true},
     source = "complete", field = "text", info = true},
    {name = "QuestProgressTitleText", events = {progress = true},
     source = "title"},
    {name = "QuestProgressText", events = {progress = true},
     source = "progress", field = "text"},
}
local eventMoments = {
    QUEST_DETAIL = "accept", QUEST_PROGRESS = "progress",
    QUEST_COMPLETE = "complete",
}

local function ClassicUAIsActive()
    -- ClassicUA hooks the same widgets. If installed, let it own QuestFrame
    -- rather than competing for SetText calls or tainting either add-on.
    if type(IsAddOnLoaded) == "function" then
        return IsAddOnLoaded("ClassicUA")
    end
    if C_AddOns and type(C_AddOns.IsAddOnLoaded) == "function" then
        return C_AddOns.IsAddOnLoaded("ClassicUA")
    end
    return false
end

local function WindowVisible()
    return QuestFrame and type(QuestFrame.IsShown) == "function"
        and QuestFrame:IsShown()
end

local function LiveID()
    if type(GetQuestID) ~= "function" then return nil end
    local id = tonumber(GetQuestID())
    if id and id > 0 then return id end
end

local function SelectedTranslation(id, moment, field)
    local quest = translations[id]
    if not quest or not moment or not field.events[moment] then return nil end
    if field.source == "title" or field.source == "objective" then
        -- The title/objective is sourced from the *same* audited Quest record
        -- as an already-imported moment, not from an unreviewed ID-only join.
        local row = quest[field.source]
        return type(row) == "string" and row ~= "" and row or nil
    end
    local row = quest[field.source]
    return row and type(row.text) == "string" and row.text ~= ""
        and row.text or nil
end

local function SetWithoutRecursion(widget, text)
    writing[widget] = true
    widget:SetText(text)
    writing[widget] = nil
end

local function ShiftHeld()
    return type(IsShiftKeyDown) == "function" and IsShiftKeyDown() or false
end

local function JournalOwnsField(info)
    return info and QuestInfoFrame and QuestInfoFrame.questLog
end

local function Apply(widget, snapshot)
    if not snapshot or not WindowVisible() or activeID ~= snapshot.id
            or activeMoment ~= snapshot.moment or LiveID() ~= snapshot.id
            or JournalOwnsField(snapshot.info) then
        return
    end
    local original = ShiftHeld()
    if not SU:UseQuestFont(widget, snapshot.font, not original) then original = true end
    local text = original and snapshot.original or snapshot.translated
    if widget:GetText() ~= text then
        SetWithoutRecursion(widget, text)
    end
end

local function HandleText(widget, value, field)
    if writing[widget] then return end
    local previous = originals[widget]
    if previous then SU:UseQuestFont(widget, previous.font, false) end
    originals[widget] = nil
    if JournalOwnsField(field.info) or type(value) ~= "string" or value == "" or ClassicUAIsActive()
            or not WindowVisible() or not activeID or not activeMoment
            or activeID ~= LiveID() then return end
    local translation = SelectedTranslation(activeID, activeMoment, field)
    if not translation then return end
    translation = SU:ExpandQuestText(translation)
    if type(translation) ~= "string" or translation == "" then return end

    -- Native rendered text, even if it already substitutes player tokens,
    -- is always the Shift version, never the offline English corpus.
    local snapshot = {id = activeID, moment = activeMoment, info = field.info,
                      original = value, translated = translation}
    snapshot.font = SU:CaptureQuestFont(widget)
    originals[widget] = snapshot
    Apply(widget, snapshot)
end

local function HookFields()
    if type(hooksecurefunc) ~= "function" then return end
    for _, field in ipairs(nativeFields) do
        local widget = _G[field.name]
        if widget and type(widget.SetText) == "function" and not registered[widget] then
            registered[widget] = true
            hooksecurefunc(widget, "SetText", function(self, value)
                HandleText(self, value, field)
            end)
        end
    end
end

local function Clear()
    -- No native widget ownership outside the current NPC quest moment.
    -- Leave original text intact during transition to the next quest.
    for widget, snapshot in pairs(originals) do
        if widget and snapshot and
                widget:GetText() == snapshot.translated then
            SetWithoutRecursion(widget, snapshot.original)
        end
        SU:UseQuestFont(widget, snapshot.font, false)
        originals[widget] = nil
    end
end

local function ScanCurrent()
    if not activeID or not activeMoment or activeID ~= LiveID()
            or not WindowVisible() then return end
    HookFields()
    -- Catch a widget whose native SetText preceded the event or OnShow.
    for _, field in ipairs(nativeFields) do
        local widget = _G[field.name]
        if widget and registered[widget] and field.events[activeMoment]
                and not JournalOwnsField(field.info) then
            local existing = originals[widget]
            if existing and existing.id == activeID
                    and existing.moment == activeMoment then
                Apply(widget, existing)
            elseif not existing and type(widget.GetText) == "function" then
                HandleText(widget, widget:GetText(), field)
            end
        end
    end
end

local function OnMoment(moment)
    -- Obtain the actual ID from the live NPC frame, not from a nearby
    -- tooltip, zone map or previous Spoken preview. Fail closed otherwise.
    pendingMoment = moment
    local id = LiveID()
    if not id or ClassicUAIsActive() then
        Clear()
        activeID, activeMoment = nil, nil
        return
    end
    if activeID ~= id or activeMoment ~= moment then Clear() end
    activeID, activeMoment = id, moment
    ScanCurrent()
end

local function RefreshShift()
    if ClassicUAIsActive() or not WindowVisible() or not activeID then return end
    for widget, snapshot in pairs(originals) do Apply(widget, snapshot) end
end

local listener = CreateFrame("Frame")
listener:RegisterEvent("PLAYER_LOGIN")
listener:RegisterEvent("ADDON_LOADED")
listener:RegisterEvent("QUEST_DETAIL")
listener:RegisterEvent("QUEST_PROGRESS")
listener:RegisterEvent("QUEST_COMPLETE")
listener:RegisterEvent("QUEST_FINISHED")
listener:RegisterEvent("MODIFIER_STATE_CHANGED")
listener:SetScript("OnEvent", function(self, event, ...)
    if eventMoments[event] then
        OnMoment(eventMoments[event])
    elseif event == "MODIFIER_STATE_CHANGED" then
        RefreshShift()
    elseif event == "QUEST_FINISHED" then
        Clear()
        activeID, activeMoment, pendingMoment = nil, nil, nil
    else
        HookFields()
    end
end)

local function HookQuestFrameHide()
    if frame or not QuestFrame or type(QuestFrame.HookScript) ~= "function" then
        return
    end
    frame = QuestFrame
    frame:HookScript("OnShow", function()
        -- Some Blizzard QuestFrame revisions set text while the frame is
        -- hidden. Resolve a pending moment only once its real QuestID exists.
        if pendingMoment and not ClassicUAIsActive() then
            local id = LiveID()
            if id and (id ~= activeID or pendingMoment ~= activeMoment) then
                Clear()
                activeID, activeMoment = id, pendingMoment
            end
            ScanCurrent()
        end
    end)
    frame:HookScript("OnHide", function()
        Clear()
        activeID, activeMoment, pendingMoment = nil, nil, nil
    end)
end

-- Available when the WoW UI is already loaded; lazy retry on player login,
-- addon load and each quest event in case Blizzard frames initialize late.
HookFields()
HookQuestFrameHide()
listener:HookScript("OnEvent", function(self, event)
    if event == "PLAYER_LOGIN" or event == "ADDON_LOADED" or eventMoments[event] then
        HookQuestFrameHide()
    end
end)
