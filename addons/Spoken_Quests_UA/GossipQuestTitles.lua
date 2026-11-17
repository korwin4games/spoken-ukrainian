-- WoW Forever Quest title translations in Gossip / Quest Greeting.
-- Title-only data are from the audited ClassicUA source at BUILD time.
-- This module does not require the ClassicUA AddOn at runtime and does not
-- treat title-only content as Spoken narration or approved Stage 3 mapping.
local SU = assert(SpokenUkrainian, "Spoken Ukrainian dependency not loaded")
local titleLookup = assert(SU.GossipQuestTitles, "Gossip title data not generated")
local rows = setmetatable({}, {__mode = "k"})
local hooked = {}
local greetingPanel

local function ClassicUAActive()
    if type(IsAddOnLoaded) == "function" then
        return IsAddOnLoaded("ClassicUA")
    end
    return C_AddOns and type(C_AddOns.IsAddOnLoaded) == "function"
        and C_AddOns.IsAddOnLoaded("ClassicUA") or false
end

local function PlayerFaction()
    if type(UnitFactionGroup) ~= "function" then return nil end
    local faction = UnitFactionGroup("player")
    if type(faction) ~= "string" then return nil end
    return titleLookup[faction:lower()]
end

local function EnglishOriginal(row)
    if not row or type(row.GetText) ~= "function" then return nil end
    local text = row:GetText()
    return type(text) == "string" and text ~= "" and text or nil
end

local function ReplaceTitle(original, english, ukrainian)
    if type(original) ~= "string" or type(english) ~= "string"
            or english == "" or type(ukrainian) ~= "string" then
        return nil
    end
    local start, finish = original:find(english, 1, true)
    if not start then return nil end
    return original:sub(1, start - 1) .. ukrainian .. original:sub(finish + 1)
end

-- Gossip mixin buttons implement Resize(), but QuestTitleButtonTemplate
-- in the NPC Quest Greeting does not. Blizzard calculates its initial height
-- from the English title before our post-OnShow translation. Update that
-- height after every visible text change so following anchored rows reflow.
local function ResizeTitle(row, greeting)
    if not greeting then
        if type(row.Resize) == "function" then row:Resize() end
        return
    end
    if type(row.SetHeight) ~= "function" or type(row.GetTextHeight) ~= "function" then
        return
    end
    local textHeight = row:GetTextHeight()
    if type(textHeight) ~= "number" then return end
    local iconHeight = row.Icon and type(row.Icon.GetHeight) == "function"
        and row.Icon:GetHeight() or 0
    if type(iconHeight) ~= "number" then iconHeight = 0 end
    -- Match Blizzard QuestFrameGreetingPanel_OnShow's SetHeight formula.
    row:SetHeight(math.max(textHeight + 2, iconHeight))
end

local function Refresh(row, snapshot)
    if not row or not snapshot or ClassicUAActive() then return end
    if type(row.SetText) ~= "function" or type(row.GetText) ~= "function" then return end
    if type(row.IsShown) == "function" and not row:IsShown() then return end
    local english = type(IsShiftKeyDown) == "function" and IsShiftKeyDown()
    local desired = english and snapshot.original or snapshot.translated
    if row:GetText() ~= desired then
        row:SetText(desired)
        ResizeTitle(row, snapshot.greeting)
    end
end

local function TranslateRow(row, questID, englishTitle, greeting)
    if not row or type(row.SetText) ~= "function" then return end
    local old = rows[row]
    local value = EnglishOriginal(row)
    if not value then
        rows[row] = nil
        return
    end
    -- A pooled button might be scanned repeatedly after our own SetText.
    -- Reuse its captured original; never make Ukrainian the Shift original.
    if old and old.id == questID and value == old.translated then
        Refresh(row, old)
        return
    end
    rows[row] = nil
    if ClassicUAActive() then return end
    local id = tonumber(questID)
    local titles = PlayerFaction()
    local localized = id and titles and titles[id]
    if type(localized) ~= "string" or localized == "" then return end
    local translated = ReplaceTitle(value, englishTitle, SU:ExpandQuestText(localized))
    if not translated or translated == value then return end
    local snapshot = {id = id, original = value, translated = translated,
                      greeting = greeting == true}
    rows[row] = snapshot
    Refresh(row, snapshot)
end

local function OnGossipQuestSetup(row, info)
    if type(info) ~= "table" then return end
    TranslateRow(row, info.questID, info.title)
end

local function HookGossipMixins()
    if type(hooksecurefunc) ~= "function" then return end
    for _, name in ipairs({"GossipAvailableQuestButtonMixin", "GossipActiveQuestButtonMixin"}) do
        local mixin = _G[name]
        if type(mixin) == "table" and type(mixin.Setup) == "function"
                and not hooked[mixin] then
            hooked[mixin] = true
            hooksecurefunc(mixin, "Setup", OnGossipQuestSetup)
        end
    end
end

local function RefreshGreetingTitles()
    if ClassicUAActive() then return end
    local panel = QuestFrameGreetingPanel
    local pool = panel and panel.titleButtonPool
    if not pool or type(pool.EnumerateActive) ~= "function" then return end
    for button in pool:EnumerateActive() do
        if button and type(button.GetID) == "function" then
            local id
            if button.isActive == 1 and type(GetActiveQuestID) == "function" then
                id = GetActiveQuestID(button:GetID())
            elseif type(GetAvailableQuestInfo) == "function" then
                id = select(5, GetAvailableQuestInfo(button:GetID()))
            end
            local original = EnglishOriginal(button)
            local existing = rows[button]
            if existing and existing.id == id
                    and original == existing.translated then
                original = existing.original
            end
            if original then
                -- The NPC greeting title is the whole visible button text;
                -- unlike Gossip options it has no extra formatting to keep.
                TranslateRow(button, id, original, true)
            end
        end
    end
end

local function HookGreeting()
    local panel = QuestFrameGreetingPanel
    if panel and panel ~= greetingPanel and type(panel.HookScript) == "function" then
        greetingPanel = panel
        panel:HookScript("OnShow", RefreshGreetingTitles)
    end
    if not hooked.greetingFunction and type(QuestFrameGreetingPanel_OnShow) == "function"
            and type(hooksecurefunc) == "function" then
        hooked.greetingFunction = true
        hooksecurefunc("QuestFrameGreetingPanel_OnShow", RefreshGreetingTitles)
    end
end

local function RefreshShift()
    if ClassicUAActive() then return end
    for row, snapshot in pairs(rows) do
        Refresh(row, snapshot)
    end
end

local events = CreateFrame("Frame")
for _, event in ipairs({
    "PLAYER_LOGIN", "ADDON_LOADED", "GOSSIP_SHOW", "QUEST_GREETING",
    "MODIFIER_STATE_CHANGED", "GOSSIP_CLOSED", "QUEST_FINISHED",
}) do events:RegisterEvent(event) end

events:SetScript("OnEvent", function(self, event)
    if event == "MODIFIER_STATE_CHANGED" then
        RefreshShift()
    elseif event == "GOSSIP_CLOSED" or event == "QUEST_FINISHED" then
        -- Avoid retaining stale QuestID and translated title for a later NPC.
        for row in pairs(rows) do rows[row] = nil end
    else
        HookGossipMixins()
        HookGreeting()
        if event == "QUEST_GREETING" then RefreshGreetingTitles() end
    end
end)

HookGossipMixins()
HookGreeting()
