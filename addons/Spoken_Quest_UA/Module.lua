-- Standalone Quest text-only module. The public Spoken text pack is in
-- TextPack.lua; this module adds only the optional local NPC-quest preview.
-- No voice pack registration or synthetic sound duration tables.
local SU = assert(SpokenUkrainian, "Spoken_Ukrainian dependency not loaded")
local translations = assert(SU.QuestTranslations, "Spoken Ukrainian translations not generated")

-- Quest 1:1 provisional preview, separate from native quest frames and
-- Spoken's narrator captions. Never hook upstream internals.
local shown
local function HidePreview()
    if shown then shown:Hide() end
end
SU.HideQuestPreview = HidePreview

local function ShowPreview(questID, event, entry, localizedTitle)
    if not shown then
        local frame = CreateFrame("Frame", nil, UIParent)
        frame:SetWidth(640)
        frame:SetHeight(350)
        frame:SetPoint("CENTER", UIParent, "CENTER", 0, 70)
        frame:SetFrameStrata("DIALOG")
        frame:EnableMouse(true)
        local background = frame:CreateTexture(nil, "BACKGROUND")
        background:SetAllPoints(frame)
        background:SetColorTexture(0.03, 0.05, 0.10, 0.94)
        local heading = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
        heading:SetPoint("TOPLEFT", frame, "TOPLEFT", 16, -12)
        heading:SetText("Spoken Ukrainian — Quest preview (TEST)")
        local close = CreateFrame("Button", nil, frame, "UIPanelCloseButton")
        close:SetPoint("TOPRIGHT", frame, "TOPRIGHT", 0, 0)
        close:SetScript("OnClick", function() frame:Hide() end)
        local info = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        info:SetPoint("TOPLEFT", frame, "TOPLEFT", 16, -43)
        info:SetWidth(600)
        info:SetJustifyH("LEFT")
        local scroll = CreateFrame("ScrollFrame", nil, frame, "UIPanelScrollFrameTemplate")
        scroll:SetPoint("TOPLEFT", frame, "TOPLEFT", 16, -82)
        scroll:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -34, 16)
        local body = CreateFrame("Frame", nil, scroll)
        body:SetWidth(580)
        body:SetHeight(1)
        scroll:SetScrollChild(body)
        local text = body:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
        text:SetWidth(565)
        text:SetPoint("TOPLEFT", body, "TOPLEFT", 0, 0)
        text:SetJustifyH("LEFT")
        text:SetJustifyV("TOP")
        frame.Info = info
        frame.Content = text
        frame.ScrollBody = body
        frame.Scroll = scroll
        SU:UseQuestFont(info, SU:CaptureQuestFont(info), true)
        SU:UseQuestFont(text, SU:CaptureQuestFont(text), true)
        shown = frame
    end
    local title = localizedTitle
    if (type(title) ~= "string" or title == "") and type(GetTitleText) == "function" then
        title = GetTitleText() -- Native-client fallback; no title guessing.
    end
    local label = type(title) == "string" and title ~= "" and (SU:ExpandQuestText(title) .. " · ") or ""
    shown.Info:SetText(label .. "Quest " .. questID .. " · " .. event
        .. (entry.reviewed and " · human-reviewed" or " · machine 1:1 (provisional)"))
    shown.Content:SetText(SU:ExpandQuestText(entry.text))
    shown.ScrollBody:SetHeight(math.max(1, shown.Content:GetStringHeight() + 12))
    shown.Scroll:SetVerticalScroll(0)
    shown:Show()
end

local events = {
    QUEST_DETAIL = "accept",
    QUEST_PROGRESS = "progress",
    QUEST_COMPLETE = "complete",
}
local listener = CreateFrame("Frame")
for name in pairs(events) do listener:RegisterEvent(name) end
listener:RegisterEvent("QUEST_FINISHED")
listener:SetScript("OnEvent", function(self, event)
    if event == "QUEST_FINISHED" then
        HidePreview()
        return
    end
    if not SU.previewEnabled then return end
    local id = GetQuestID and tonumber(GetQuestID())
    if not id or id <= 0 then return end
    local parts = translations[id]
    local entry = parts and parts[events[event]]
    if entry and type(entry.text) == "string" and entry.text ~= "" then
        ShowPreview(id, events[event], entry, parts.title)
    else
        HidePreview()
    end
end)
