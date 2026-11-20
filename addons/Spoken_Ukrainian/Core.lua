-- Spoken Ukrainian standalone language helper (local test build).
-- Never overwrites Spoken/Spoken_Quests, GetLocale, native Quest frames or audio.
SpokenUkrainian = SpokenUkrainian or {}
local SU = SpokenUkrainian

SU.previewEnabled = false

function SU:Print(message)
    if DEFAULT_CHAT_FRAME and DEFAULT_CHAT_FRAME.AddMessage then
        DEFAULT_CHAT_FRAME:AddMessage("|cff6cb8ffSpoken Ukrainian|r: " .. message)
    end
end

-- ClassicUA's Quest text uses Ukrainian grammatical placeholders.
-- Expand only documented local-test forms; preserve unknown codes verbatim.
-- The character's declined name is not available from the public WoW API:
-- all name cases intentionally fall back to UnitName("player").
local firstUpper = {
    ["а"] = "А", ["б"] = "Б", ["в"] = "В", ["г"] = "Г",
    ["ґ"] = "Ґ", ["д"] = "Д", ["е"] = "Е", ["є"] = "Є",
    ["ж"] = "Ж", ["з"] = "З", ["и"] = "И", ["і"] = "І",
    ["ї"] = "Ї", ["й"] = "Й", ["к"] = "К", ["л"] = "Л",
    ["м"] = "М", ["н"] = "Н", ["о"] = "О", ["п"] = "П",
    ["р"] = "Р", ["с"] = "С", ["т"] = "Т", ["у"] = "У",
    ["ф"] = "Ф", ["х"] = "Х", ["ц"] = "Ц", ["ч"] = "Ч",
    ["ш"] = "Ш", ["щ"] = "Щ", ["ь"] = "Ь", ["ю"] = "Ю",
    ["я"] = "Я",
}
local function Capitalize(word)
    local head = word:sub(1, 2)
    if firstUpper[head] then
        return firstUpper[head] .. word:sub(3)
    end
    return word:sub(1, 1):upper() .. word:sub(2)
end

local canonicalForms = {
    ["ім'я"] = "name", ["Ім'я"] = "name", ["ІМ'Я"] = "name",
    ["клас"] = "class", ["Клас"] = "class", ["КЛАС"] = "class",
    ["раса"] = "race", ["Раса"] = "race", ["РАСА"] = "race",
}
local declinedCases = {
    ["н"] = true, ["р"] = true, ["д"] = true, ["з"] = true,
    ["о"] = true, ["м"] = true, ["к"] = true,
}
local function ReplaceCode(code)
    local male, female = code:match("^стать:([^:{}]+):([^:{}]+)$")
    if male and female and type(UnitSex) == "function" then
        local sex = UnitSex("player")
        if sex == 2 then return male end
        if sex == 3 then return female end
        return nil
    end

    local original, case = code:match("^([^:{}]+):?([^:{}]*)$")
    local kind = original and canonicalForms[original]
    if not kind or (case ~= "" and not declinedCases[case]) then return nil end

    if kind == "name" then
        if type(UnitName) ~= "function" then return nil end
        local name = UnitName("player")
        return type(name) == "string" and name ~= "" and name or nil
    end

    local sex = type(UnitSex) == "function" and UnitSex("player") or nil
    if sex ~= 2 and sex ~= 3 then return nil end
    local getIdentity = kind == "class" and UnitClass or UnitRace
    if type(getIdentity) ~= "function" then return nil end
    local _, key = getIdentity("player")
    if type(key) ~= "string" then return nil end
    local root = SU.Inflections and SU.Inflections[kind]
    local forms = root and root[key:lower()]
    local selected = forms and forms[case == "" and "н" or case]
    local text = selected and selected[sex == 2 and 1 or 2]
    if type(text) ~= "string" or text == "" then return nil end
    if original == "Клас" or original == "Раса"
            or original == "КЛАС" or original == "РАСА" then
        return Capitalize(text)
    end
    return text
end

function SU:ExpandQuestText(sourceText)
    if type(sourceText) ~= "string" then return sourceText end
    return (sourceText:gsub("{([^{}]+)}", function(code)
        return ReplaceCode(code) or "{" .. code .. "}"
    end))
end

-- Official Spoken 3.10.1 text-pack contract. An older Player simply lacks this
-- API; native QuestFrame/Journal/Gossip localization remains available.
-- A text pack is never registered as a voice pack or used as a sound source.
function SU:RegisterTextPack(section, data)
    if section ~= "quests" or type(data) ~= "table" then return false end
    if not Spoken or type(Spoken.RegisterText) ~= "function" then return false end
    return Spoken:RegisterText("ukUA", section, data) == true
end

SLASH_SPOKENUKRAINIAN1 = "/spokenuk"
SlashCmdList["SPOKENUKRAINIAN"] = function(message)
    message = (message or ""):lower():match("^%s*(.-)%s*$")
    if message == "preview on" then
        SU.previewEnabled = true
        SU:Print("Quest preview ON. Only imported translations appear; no audio.")
    elseif message == "preview off" then
        SU.previewEnabled = false
        if SU.HideQuestPreview then SU:HideQuestPreview() end
        SU:Print("Quest preview OFF.")
    elseif message == "status" then
        SU:Print("Quest preview: " .. (SU.previewEnabled and "ON" or "OFF")
            .. "; module: " .. (SU.QuestTranslations and "loaded" or "not loaded"))
    else
        SU:Print("Commands: /spokenuk preview on | preview off | status")
    end
end
