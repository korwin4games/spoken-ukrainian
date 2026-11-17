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
