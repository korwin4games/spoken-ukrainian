-- NPC Gossip text localization for WoW Forever, independent of ClassicUA at
-- runtime. English is matched only by its deterministic ClassicUA text hash
-- and the exact current NPC ID (or an explicitly common hash). No fuzzy match,
-- no Spoken mapping approval, no audio or global getter modifications.
local SU = assert(SpokenUkrainian, "Spoken_Ukrainian dependency not loaded")
local corpus = assert(SU.GossipTexts, "Spoken Ukrainian Gossip data not generated")
local snapshots = setmetatable({}, { __mode = "k" })
local writing = setmetatable({}, { __mode = "k" })
local hooked = setmetatable({}, { __mode = "k" })
local questGreetingHooked = false

local function ClassicUAActive()
    if type(IsAddOnLoaded) == "function" then
        return IsAddOnLoaded("ClassicUA") and true or false
    end
    return C_AddOns and type(C_AddOns.IsAddOnLoaded) == "function"
        and C_AddOns.IsAddOnLoaded("ClassicUA") or false
end

local function NpcID()
    if type(UnitGUID) ~= "function" then return nil end
    local guid = UnitGUID("npc")
    if type(guid) ~= "string" then return nil end
    local kind = guid:match("^([A-Za-z]+)%-")
    if kind ~= "Creature" and kind ~= "Vehicle" then return nil end
    -- GUID = type-realm-server-instance-zone-npcID-spawnID.
    local id = guid:match("^[^%-]+%-[^%-]+%-[^%-]+%-[^%-]+%-[^%-]+%-(%d+)%-")
    local number = id and tonumber(id)
    return number and number > 0 and number or nil
end

-- Matches the pinned ClassicUA scripts/utils.lua get_text_hash / string_hash:
-- collapse regular and NBSP spaces, trim, lowercase and hash UTF-8 bytes.
-- String arithmetic stays below 2^53, so Lua's double is exact here.
local function EnglishHash(value)
    if type(value) ~= "string" or value == "" then return nil end
    local text = value:gsub("\194\160", " "):gsub(" +", " ")
    text = text:match("^%s*(.-)%s*$"):lower()
    text = text:gsub("Ї", "ї"):gsub("Є", "є"):gsub("І", "і"):gsub("Ґ", "ґ")
    if text == "" then return nil end
    local count = 1
    local len = #text
    for i = 1, len, 3 do
        count = math.fmod(count * 8161, 4294967279)
            + (text:byte(i) * 16776193)
            + ((text:byte(i + 1) or (len - i + 256)) * 8372226)
            + ((text:byte(i + 2) or (len - i + 256)) * 3932164)
    end
    return math.fmod(count, 4294967291)
end

local function TranslatedText(npcID, sourceText)
    if not npcID or type(sourceText) ~= "string" then return nil end
    local hash = EnglishHash(sourceText)
    if not hash then return nil end
    local byNpc = corpus.byNpc and corpus.byNpc[npcID]
    local translation = (byNpc and byNpc[hash])
        or (corpus.common and corpus.common[hash])
    if type(translation) ~= "string" or translation == "" then return nil end
    return SU:ExpandQuestText(translation)
end

local function ShiftHeld()
    return type(IsShiftKeyDown) == "function" and IsShiftKeyDown() or false
end

local function SetText(widget, text)
    writing[widget] = true
    widget:SetText(text)
    writing[widget] = nil
end

local function Resize(widget, owner, kind)
    if kind == "reply" then
        if type(owner.Resize) == "function" then owner:Resize() end
    elseif kind == "npc" then
        if owner and type(owner.SetHeight) == "function"
                and type(widget.GetHeight) == "function" then
            owner:SetHeight(widget:GetHeight())
        end
    end
end

local function Refresh(widget, snapshot)
    if not widget or not snapshot or ClassicUAActive() then return end
    if type(widget.GetText) ~= "function" or type(widget.SetText) ~= "function" then return end
    local desired = ShiftHeld() and snapshot.original or snapshot.translated
    if widget:GetText() ~= desired then
        SetText(widget, desired)
        Resize(widget, snapshot.owner, snapshot.kind)
    end
end

local function Capture(widget, english, owner, kind)
    if not widget or type(widget.SetText) ~= "function"
            or type(english) ~= "string" or english == "" then return end
    snapshots[widget] = nil
    if ClassicUAActive() then return end
    local npcID = NpcID()
    local uk = TranslatedText(npcID, english)
    if type(uk) ~= "string" or uk == "" then return end
    local original = widget:GetText()
    if type(original) ~= "string" or original == "" then return end
    -- Do not modify decorative icons/prepends on options. Exact substring
    -- replacement, never a global gsub interpreted as a Lua pattern.
    local start, finish = original:find(english, 1, true)
    if not start then return end
    local translated = original:sub(1, start - 1) .. uk .. original:sub(finish + 1)
    if translated == original then return end
    local snapshot = { original = original, translated = translated,
        npcID = npcID, owner = owner, kind = kind }
    snapshots[widget] = snapshot
    Refresh(widget, snapshot)
end

local function OnNPCText(widget, english, owner)
    if writing[widget] then return end
    if type(widget.GetText) ~= "function" then return end
    Capture(widget, english, owner, "npc")
end

local function OnGreetingSetup(frame, english)
    if not frame or not frame.GreetingText then return end
    OnNPCText(frame.GreetingText, english, frame)
end

local function OnReplySetup(row, info)
    if type(info) ~= "table" or type(info.name) ~= "string" or not row then return end
    Capture(row, info.name, row, "reply")
end

local function HookGreetingText()
    if questGreetingHooked or type(hooksecurefunc) ~= "function"
            or type(QuestFrameGreetingPanel_OnShow) ~= "function" then return end
    questGreetingHooked = true
    hooksecurefunc("QuestFrameGreetingPanel_OnShow", function()
        -- Quest Greeting shares the NPC text with ClassicUA Gossip source.
        -- It is separate from Quest accept/progress/completion.
        local widget = _G.GreetingText
        if widget and type(widget.GetText) == "function" then
            OnNPCText(widget, widget:GetText())
        end
    end)
end

local function HookGossip()
    if type(hooksecurefunc) ~= "function" then return end
    local greeting = _G.GossipGreetingTextMixin
    if type(greeting) == "table" and type(greeting.Setup) == "function"
            and not hooked[greeting] then
        hooked[greeting] = true
        hooksecurefunc(greeting, "Setup", OnGreetingSetup)
    end
    local option = _G.GossipOptionButtonMixin
    if type(option) == "table" and type(option.Setup) == "function"
            and not hooked[option] then
        hooked[option] = true
        hooksecurefunc(option, "Setup", OnReplySetup)
    end
    HookGreetingText()
end

local function Clear()
    for widget in pairs(snapshots) do snapshots[widget] = nil end
end

local listener = CreateFrame("Frame")
for _, event in ipairs({
    "PLAYER_LOGIN", "ADDON_LOADED", "GOSSIP_SHOW", "GOSSIP_CLOSED",
    "QUEST_GREETING", "QUEST_FINISHED", "MODIFIER_STATE_CHANGED",
}) do listener:RegisterEvent(event) end
listener:SetScript("OnEvent", function(self, event)
    if event == "MODIFIER_STATE_CHANGED" then
        if ClassicUAActive() then return end
        local npcID = NpcID()
        for widget, snapshot in pairs(snapshots) do
            if npcID and snapshot.npcID == npcID then
                Refresh(widget, snapshot)
            else
                snapshots[widget] = nil
            end
        end
    elseif event == "GOSSIP_CLOSED" or event == "QUEST_FINISHED" then
        Clear()
    else
        HookGossip()
    end
end)

HookGossip()
