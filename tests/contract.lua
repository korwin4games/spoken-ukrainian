local function contains(values, wanted)
    for _, value in ipairs(values) do
        if (type(value) == "table" and value.code or value) == wanted then return true end
    end
    return false
end

function Session(config)
    config = config or {}
    local e = setmetatable({}, { __index = _G })
    e._G, e.SpokenEnv = e, e
    e.GetLocale = function() return "enUS" end
    -- Chunks already have their requested environment through load(..., env).
    e.setfenv = function(level, target) assert(level == 1 and target == e) end
    e.unpack = table.unpack
    e.format = string.format
    e.Spoken = {}
    e.AddonVersion = "3.9.0"
    e.L = setmetatable({}, { __index = function(_, key) return key end })
    e.Addon = { db = { profile = { Language = { Voice = config.voice or "auto", Fallback = "enUS" } } } }
    e.Addon.BindModuleSettings = function() return false end
    e.SpokenPlacesSettings = { language = config.text }
    local forbidden = function() error("Unexpected sound, network, database or queue operation") end
    e.PlaySoundFile, e.PlaySound, e.SendAddonMessage = forbidden, forbidden, forbidden
    e.SlashCmdList = {}
    e.DEFAULT_CHAT_FRAME = { AddMessage = function() end }
    e.CreateFrame = function(kind)
        assert(kind == "Frame")
        return { RegisterEvent = function() end, SetScript = function() end }
    end
    local font = { GetFont = function() return "Fonts\\FRIZQT__.TTF", 12, "" end }
    e.GameFontHighlight, e.QuestFont = font, font
    e.UIParent = { CreateFontString = function()
        return {
            Hide = function() end,
            SetFont = function() return true end,
            SetText = function(self, text) self.text = text end,
            GetStringWidth = function(self)
                local count = utf8.len(self.text)
                if config.fontMissing then return count * 8 end
                return count * (self.text:find("\205\184", 1, true) and 8 or 11)
            end,
        }
    end }
    local function info(addon)
        if addon == 1 or addon == FOLDER then
            return FOLDER, META.Title, "", not config.disabled, config.disabled and "DISABLED" or nil
        end
        if addon == 2 or addon == "EnglishFixture" then
            return "EnglishFixture", "English fixture", "", true
        end
    end
    e.C_AddOns = {
        GetNumAddOns = function() return config.removed and 0 or 2 end,
        GetAddOnInfo = info,
        GetAddOnMetadata = function(addon, key)
            local folder = info(addon)
            if folder == FOLDER then
                if config.noDeclaration and key == "X-SpokenPlaces-Language" then return nil end
                return META[key]
            end
            if folder == "EnglishFixture" and key == "X-SpokenPlaces-Language" then return "enUS" end
            if addon == "Spoken_Places" and key == "Version" then return "3.9.0" end
        end,
    }
    local function upstream(path, ...)
        return assert(load(SOURCES[path], "@" .. path, "t", e))(...)
    end
    upstream("addons/Spoken/Languages.lua")
    upstream("addons/Spoken/UI/Options.lua")
    upstream("addons/Spoken/API.lua")
    local p = {}
    upstream("addons/Spoken_Places/Data/Languages.lua", "Spoken_Places", p)
    upstream("addons/Spoken_Places/Language.lua", "Spoken_Places", p)
    upstream("addons/Spoken_Places/Core.lua", "Spoken_Places", p)
    upstream("addons/Spoken_Places/Audio.lua", "Spoken_Places", p)
    p.source = { PlayNow = forbidden, Enqueue = forbidden }
    local english, subzones = { [1429] = { name = "Fixture", full = "Synthetic English reference." } }, {}
    p:RegisterLoreData("enUS", "zones", english)
    p:RegisterLoreData("enUS", "subzones", subzones)
    local calls = {}
    if not config.disabled and not config.removed then
        local api = setmetatable({}, {
            __index = function(_, key)
                assert(key == "RegisterLoreData", "Pack used a non-registration API: " .. key)
                return function(_, code, kind, data)
                    calls[#calls + 1] = { code = code, kind = kind, data = data }
                    return p:RegisterLoreData(code, kind, data)
                end
            end,
            __newindex = forbidden,
        })
        local packEnv = setmetatable({ SpokenPlaces = api }, {
            __index = function(_, key) error("Unexpected pack global read: " .. key) end,
            __newindex = forbidden,
        })
        assert(load(PACK, "@Lore.lua", "t", packEnv))(FOLDER, {})
    end
    return e, p, calls, english, subzones
end

function check_registration()
    local e, p = Session()
    local uk = assert(e.Spoken:Language("ukUA"))
    assert(uk.client == false and uk.builtin == false and uk.lore == true)
    assert(uk.name == "Ukrainian" and uk.native == "Українська")
    assert(uk.folders[1] == FOLDER and e.GetLocale() == "enUS")
    assert(e.Spoken:Language("enUS").client == true)
    assert(contains(e.Options:VoiceChoices(), "ukUA"))
    assert(contains(p:GetSelectableLanguages(), "ukUA"))
    assert(e.Spoken:MenuLanguageName("ukUA") == "Українська")
end

function check_registration_order()
    local _, p, calls = Session({ text = "ukUA" })
    assert(#calls == 2)
    assert(calls[1].code == "ukUA" and calls[1].kind == "zones")
    assert(calls[2].code == "ukUA" and calls[2].kind == "subzones")
    assert(next(calls[2].data) == nil and p.Subzones == calls[2].data)
    local zone = p:GetLore(1429)
    assert(zone == calls[1].data[1429] and zone.name == "Elwynn Forest")
    local count = 0
    for id in pairs(p.Zones) do assert(id == 1429); count = count + 1 end
    assert(count == 1)
    assert(zone.short ~= "" and zone.full:find("не історія світу Warcraft", 1, true))
    for _, glyph in ipairs({"і", "ї", "є", "ґ", "І", "Ї", "Є", "Ґ", "'", "’", "ʼ", "«", "»", "“", "”", '"', "…", "—"}) do
        assert(zone.full:find(glyph, 1, true), "Missing glyph: " .. glyph)
    end
    assert(zone.file == nil and zone.len == nil and zone.times == nil)
end

function check_separate_settings_and_reload()
    local e, p, _, english = Session()
    assert(p:GetLanguage() == "enUS" and p.Zones == english)
    assert(p:SetLanguage("ukUA"))
    assert(p:GetLanguage() == "enUS" and p:ResolveLanguage() == "ukUA")
    assert(e.Spoken:VoiceLanguage() == "enUS")
    e, p = Session({ text = "ukUA" })
    assert(p:GetLanguage() == "ukUA" and p:GetLore(1429))
    e.Addon.db.profile.Language.Voice = "ukUA"
    assert(p:SetLanguage("enUS"))
    assert(e.Spoken:VoiceLanguage() == "ukUA")
    e, p, _, english = Session({ text = "enUS", voice = "ukUA" })
    assert(p.Zones == english and e.Spoken:VoiceLanguage() == "ukUA")
    assert(e.GetLocale() == "enUS")
end

function check_english_preserved()
    for _, code in ipairs({"enUS", "ukUA"}) do
        local e, p, _, english, subzones = Session({ text = code })
        assert(p.CaptionLore.enUS.zones == english and p.CaptionLore.enUS.subzones == subzones)
        assert(english[1429].full == "Synthetic English reference.")
        assert(contains(e.Options:FallbackChoices(), "enUS"))
        assert(p:GetFallbackLanguage() == "enUS")
        p:RegisterStrings("enUS", { DIAGNOSTIC_TEST = "English UI fixture" })
        assert(p.L.DIAGNOSTIC_TEST == "English UI fixture")
    end
end

function check_disabled_and_removed()
    for _, flag in ipairs({"disabled", "removed"}) do
        local e, p, calls, english = Session({ [flag] = true, text = "ukUA" })
        assert(e.Spoken:Language("ukUA") == nil and #calls == 0)
        assert(not contains(e.Options:VoiceChoices(), "ukUA"))
        assert(not contains(p:GetSelectableLanguages(), "ukUA"))
        assert(p:GetLanguage() == "enUS" and p.Zones == english)
        assert(e.GetLocale() == "enUS")
    end
end

function check_font_guard()
    local e, p = Session({ fontMissing = true, text = "ukUA" })
    assert(e.Spoken:Language("ukUA") ~= nil)
    assert(not p:IsLanguageSelectable("ukUA") and not p:SetLanguage("ukUA"))
    assert(p:GetLanguage() == "enUS" and p.CaptionLore.ukUA == nil)
    assert(e.Spoken:MenuLanguageName("ukUA") == "Ukrainian")
end

function check_requires_places_declaration()
    local e, p = Session({ noDeclaration = true })
    assert(e.Spoken:Language("ukUA") == nil)
    assert(p.CaptionLore.ukUA == nil)
end

function check_no_audio()
    local e, p = Session({ text = "ukUA", voice = "ukUA" })
    assert(e.SpokenPlacesAudioPacks == nil and e.SpokenBossesAudioPacks == nil)
    assert(e.SpokenReadablesAudioPacks == nil and e.SpokenZonesAudioPacks == nil)
    assert(#p:GetAudioPacks() == 0 and not p:HasAudio(1429))
    assert(p:NewLoreSound(1429) == nil and p:PlayLore(1429) == false)
end
