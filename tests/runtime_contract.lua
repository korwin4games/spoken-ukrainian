-- Only invented prose and symbolic valid-clip metadata. No file is created or played.
-- Whole pinned chunks are loaded without replacement. Lexical UI exports are appended
-- after the original chunk solely to call its existing private functions in tests.
local function upstream(e, path, module, exports)
    local source = assert(SOURCES[path], path)
    return assert(load(source .. (exports or ""), "@" .. path, "t", e))(path, module)
end

local function forbidden() error("Unexpected audio/network operation") end

local function base(noUkrainianPack)
    local e = setmetatable({}, { __index = _G })
    e._G, e.SpokenEnv, e.VoiceOver = e, e, e
    e.GetLocale = function() return "enUS" end
    e.setfenv = function(level, env) assert(level == 1 and env == e) end
    e.format, e.unpack, e.getn = string.format, table.unpack, function(t) return #t end
    -- Lua 5.1 compatibility on a private copy, never mutate the host table library.
    e.table = setmetatable({ getn = e.getn }, { __index = table })
    e.UnitName = function() return "Fixture" end
    e.UnitClass = function() return "Warrior" end
    e.UnitRace = function() return "Human" end
    e.UnitSex = function() return 2 end
    e.PlaySoundFile, e.PlaySound, e.SendAddonMessage = forbidden, forbidden, forbidden
    e.NotSecret = function(value) return value end -- No secret game values in fixtures.
    e.Bullets = {} -- Core's public bullet registry.
    e.Spoken = {}
    e.Addon = { db = { profile = { Language = { Voice = "ukUA", Fallback = "enUS" }, Audio = {} } } }
    e.L = setmetatable({}, { __index = function(_, key) return key end })
    e.SpokenCompendium = { CONTINENTS = {}, CITY_IN = {}, IS_BATTLEGROUND = {},
        Dungeon = function() return { zone = 1 } end,
        DungeonName = function() return "Synthetic dungeon" end,
        MapName = function() return "Synthetic zone" end }
    e.SpokenCompendium.UnknownIcon = function() return {} end -- Decorative UI placeholder.
    e.GetNumAddOns = function() return 0 end
    e.CreateFrame = function(kind)
        assert(kind == "Frame")
        return { RegisterEvent = function() end, SetScript = function() end }
    end
    e.C_AddOns = { GetNumAddOns = e.GetNumAddOns, GetAddOnInfo = function() end,
        GetAddOnMetadata = function() end }
    upstream(e, "addons/Spoken/Languages.lua")
    upstream(e, "addons/Spoken/API.lua")
    upstream(e, "addons/Spoken/UI/Options.lua")
    upstream(e, "addons/Spoken/UI/Transcript.lua")
    if not noUkrainianPack then
        e.Spoken:DeclareLanguage("ukUA", "SyntheticUK")
        assert(e.Spoken:Language("ukUA").client == false)
    end
    return e
end

local function readable()
    local e = base()
    local r = { L = e.L }
    e.SpokenReadablesData = { books = { [91] = { title = "Synthetic book", pages = { 900001, 900002 } } },
        pages = { [900001] = { book = 91, number = 1, text = "Synthetic English page." },
            [900002] = { book = 91, number = 2, text = "Second synthetic page." } } }
    e.SpokenReadablesSettings = {}
    for _, path in ipairs({ "Checksum.lua", "Core.lua", "Language.lua", "Reader.lua", "Audio.lua", "Playlist.lua" }) do
        upstream(e, "addons/Spoken_Readables/" .. path, r)
    end
    local ui = upstream(e, "addons/Spoken_Readables/UI/Readables.lua", r,
        "\nreturn { Words = Words, HasWords = HasWords, Title = Title }\n")
    e.SpokenReadablesAudioPacks = { SyntheticUK = { version = 1, language = "ukUA",
        pages = { [900001] = { text = "Синтетична сторінка." } } } }
    local calls = {}
    r.source = { PlayNow = function(_, clip) calls[#calls + 1] = clip; return clip end,
        Enqueue = function(_, clip) calls[#calls + 1] = clip; return clip end }
    return e, r, ui, calls
end

function readables_text_without_file()
    local e, r, _, calls = readable()
    assert(#r:GetAudioPacks() == 1 and r:PackPageText(900001, "ukUA") == "Синтетична сторінка.")
    assert(r:HasAudio(900001) == true) -- Baseline false positive, not desired capability.
    assert(r:PageLength(900001) == nil)
    local ok, message = pcall(r.ClipFor, r, 900001)
    assert(not ok and message:find("concatenate", 1, true) and message:find("file", 1, true), message)
    e.SpokenReadablesAudioPacks.SyntheticEN = { version = 1, pages = {
        [900001] = { file = "900001", len = 3, text = "Synthetic English fallback." } } }
    ok, message = pcall(r.ClipFor, r, 900001)
    assert(not ok and message:find("file", 1, true)) -- Bad entry prevents even valid fallback.
    ok, message = pcall(r.PlayFrom, r, 900001, true, true)
    assert(not ok and message:find("file", 1, true) and #calls == 0)
    assert(not r:HasAudio(900002) and r:ClipFor(900002) == nil)
    assert(e.GetLocale() == "enUS")
end

function readables_compendium()
    local e, r, ui = readable()
    assert(r:GetVoiceLanguage() == "ukUA" and r:GetClientLanguage() == "enUS")
    assert(ui.Words(91) == "Synthetic English page.\n\nSecond synthetic page.")
    assert(ui.HasWords(91) and ui.Title(91) == "Synthetic book")
    local entry = e.SpokenReadablesAudioPacks.SyntheticUK.pages[900001]
    entry.file, entry.len = "900001", 4.5
    assert(ui.Words(91) == "Synthetic English page.\n\nSecond synthetic page.")
    assert(r.ClientPageText and r:ClientPageText(900001) == nil)
    -- No public independent text-language setter in this module.
    assert(r.SetTextLanguage == nil and r.GetTextLanguage == nil)
    e.SpokenReadablesAudioPacks.SyntheticEN = { version = 1, pages = {
        [900001] = { text = "Synthetic English pack words." } } }
    assert(ui.Words(91) == "Synthetic English pack words.\n\nSecond synthetic page.")
end

function readables_audio()
    local e, r, _, calls = readable()
    local entry = e.SpokenReadablesAudioPacks.SyntheticUK.pages[900001]
    -- Symbolic metadata for the genuine-clip contract; no claim of disk availability.
    entry.file, entry.len, entry.times = "900001", 4.5, { 0, 1 }
    local clip = assert(r:ClipFor(900001))
    assert(clip.path == "Interface\\AddOns\\SyntheticUK\\Sounds\\900001.mp3")
    assert(clip.language == "ukUA" and clip.key == "b:900001" and not clip.textOnly)
    assert(clip.present.transcript == entry.text and clip.present.timings == entry.times)
    assert(r:PlayFrom(900001, true, true) == 1 and calls[1].key == clip.key)
    entry.text = nil
    clip = assert(r:ClipFor(900001))
    assert(clip.present.transcript == "Synthetic English page." and clip.present.timings == nil)
    assert(e.GetLocale() == "enUS")
end

function readables_fallback()
    local e, r = readable()
    e.SpokenReadablesAudioPacks.SyntheticUK = nil -- Disabled at load / removed on reload.
    assert(not r:HasAudio(900001) and r:ClipFor(900001) == nil)
    e.SpokenBooksAudioPacks = { SpokenBooksAudio = { version = 1,
        pages = { [900001] = { file = "900001", text = "English legacy words.", len = 3 } } } }
    assert(r:ClipFor(900001).language == "enUS")
    assert(r:ClipFor(900001).present.transcript == "English legacy words.")
    e.Addon.db.profile.Language.Fallback = "none"
    assert(not r:HasAudio(900001) and r:PlayFrom(900001, true, true) == 0)
    e.Addon.db.profile.Language.Voice = "auto"
    assert(r:GetVoiceLanguage() == "enUS" and r:HasAudio(900001))
    e.SpokenReadablesAudioPacks.Bad = { version = 99, pages = {} }
    assert(#r:GetAudioPacks() == 1)
end

function readables_matching()
    local e, r = readable()
    local text = "Synthetic English page."
    local checksum = r:ChecksumOf(text)
    e.SpokenReadablesData.index = { ["Synthetic book"] = { [1] = { [checksum] = 900001 } } }
    e.ItemTextGetText = function() return text end
    e.ItemTextGetItem = function() return "Synthetic book" end
    e.ItemTextGetPage = function() return 1 end
    local id, exact = r:PageOnScreen()
    assert(id == 900001 and exact == true and r:PackPageText(id, "ukUA"))
    assert(r:FillPlayerTokens("$N $C $R $gson:daughter;") == "Fixture Warrior Human son")
    e.UnitSex = function() return 3 end
    assert(r:FillPlayerTokens("$gson:daughter;") == "daughter")
    e.ItemTextGetCreator = function() return "Synthetic sender" end
    assert(r:PageOnScreen() == nil) -- Mail must remain excluded.
end

local function quests(disabled)
    local e = base(disabled)
    e.AddonFolder = "Spoken_Quests"
    e.Debug = { Record = function() end }
    e.EasterEggs = { Apply = function() return false end }
    e.Version = { Interface = 16001 }
    e.Options = { AddDataModule = function() end, AddAvailableDataModule = function() end }
    for _, path in ipairs({ "Enums.lua", "Utils.lua", "Language.lua", "FuzzySearch.lua", "DataModules.lua", "Player.lua" }) do
        upstream(e, "addons/Spoken_Quests/" .. path)
    end
    local metadata = { SyntheticUK = "ukUA", SyntheticEN = "enUS" }
    e.GetNumAddOns = function() return 2 end
    e.GetAddOnInfo = function(name)
        if type(name) == "number" then name = name == 1 and "SyntheticUK" or "SyntheticEN" end
        return name, name, "", not (disabled and name == "SyntheticUK"),
            disabled and name == "SyntheticUK" and "DISABLED" or nil
    end
    e.GetAddOnMetadata = function(name, key)
        name = e.GetAddOnInfo(name)
        if key == "X-SpokenQuests-DataModule-Version" then return "1" end
        if key == "X-SpokenQuests-Language" then return metadata[name] end
        if key == "Version" then return "1.0.0" end
    end
    e.IsAddOnLoadOnDemand = function() return true end
    e.DataModules:EnumerateAddons(false) -- Normal enumeration before pack registration.
    local function pack()
        return { LookupLocale = "enUS", SoundLengthLookupByFileName = {}, TextByFileName = {},
            WordTimesByFileName = {}, GetSoundPath = function(_, file) return "Sounds/" .. file .. ".mp3" end,
            GossipLookupByNPCName = { Speaker = { ["Hello $N, take the northern road."] = "synthetic-moment" } },
            QuestWordingLookup = { ["900001-accept"] = { ["Welcome $N, take this letter."] = "900001-accept" } } }
    end
    local uk, en = pack(), pack()
    if not disabled then e.DataModules:Register("SyntheticUK", uk) end
    e.DataModules:Register("SyntheticEN", en)
    return e, uk, en
end

local function sound(e, gossip)
    return { event = gossip and e.Enums.SoundEvent.Gossip or e.Enums.SoundEvent.QuestAccept,
        questID = not gossip and 900001 or nil, name = "Speaker",
        text = gossip and "Hello Fixture, take the northern road." or "Welcome Fixture, take this letter." }
end

local function audioEntry(pack, stem, text)
    pack.SoundLengthLookupByFileName[stem] = 4.5
    pack.TextByFileName[stem] = text
    pack.WordTimesByFileName[stem] = { 0, 1 }
end

function quests_registration()
    local e, uk = quests()
    assert(uk.METADATA.Language == "ukUA" and e.Language:GetClientLanguage() == "enUS")
    assert(e.Language:GetVoiceLanguage() == "ukUA" and e.Spoken:Language("ukUA").client == false)
    local ok, message = pcall(e.DataModules.Register, e.DataModules, "Undetected", {})
    assert(not ok and message:find("enumeration", 1, true))
    e = quests(true)
    assert(e.DataModules:GetPresentModule("SyntheticUK") == nil)
    assert(e.DataModules:GetModule("SyntheticUK") == nil)
    assert(e.Spoken:Language("ukUA") == nil and e.Language:GetVoiceLanguage() == "ukUA")
end

function quests_audio()
    local e, uk = quests()
    local s = sound(e)
    uk.TextByFileName["900001-accept"] = "Синтетичне завдання."
    local calls = 0
    e.SoundQueue = { IsPaused = function() return false end,
        EndMuteGameDialogueAhead = function() end }
    e.Player.source = { Enqueue = function() calls = calls + 1; return true end }
    assert(not e.Player:Enqueue(s) and calls == 0) -- Text alone never queues.
    audioEntry(uk, "900001-accept", "Синтетичне завдання.")
    s = sound(e)
    assert(e.Player:Enqueue(s) and calls == 1)
    assert(s.language == "ukUA" and s.packText == nil and s.present.transcript == nil)
    assert(s.text == "Welcome Fixture, take this letter." and not s.textOnly)
    assert(s.present.timings == nil and s.path:find("SyntheticUK", 1, true))
    assert(e.Transcript:TextFor(s) == s.text) -- Real narrator text fallback.
    for _, event in ipairs({ e.Enums.SoundEvent.QuestProgress, e.Enums.SoundEvent.QuestComplete }) do
        local moment = event == e.Enums.SoundEvent.QuestProgress and "progress" or "complete"
        audioEntry(uk, "900001-" .. moment, "Синтетичний інший етап.")
        s = { event = event, questID = 900001, text = "Synthetic client moment." }
        assert(e.DataModules:PrepareSound(s) and s.language == "ukUA" and s.packText == nil)
    end
end

function quests_fallback()
    local e, uk, en = quests()
    audioEntry(en, "900001-accept", "Synthetic English recorded words.")
    local s = sound(e)
    assert(e.DataModules:PrepareSound(s) and s.language == "enUS")
    assert(s.packText == "Synthetic English recorded words." and s.timings)
    e.Addon.db.profile.Language.Fallback = "none"
    assert(not e.DataModules:PrepareSound(sound(e)))
    audioEntry(uk, "f-900001-accept", "Синтетична жіноча форма.")
    e.UnitSex = function() return 3 end
    s = sound(e)
    assert(e.DataModules:PrepareSound(s) and s.fileName == "f-900001-accept")
    s.text = "Unrelated unmatched wording"
    assert(not e.DataModules:PrepareSound(s))
    e, uk, en = quests(true)
    assert(not e.DataModules:PrepareSound(sound(e)))
    audioEntry(en, "900001-accept", "Synthetic English recording with UK disabled.")
    s = sound(e)
    assert(e.DataModules:PrepareSound(s) and s.language == "enUS")
end

function quests_compendium()
    local e, uk, en = quests()
    e.SpokenQuestsText = { [900001] = { accept = "Welcome $N, take this letter." } }
    local ui = upstream(e, "addons/Spoken_Quests/UI/QuestsTab.lua", nil,
        "\nreturn { PartText = PartText, Kept = Kept }\n")
    assert(ui.Kept() == nil and ui.PartText(900001, "accept") == "Welcome Fixture, take this letter.")
    audioEntry(uk, "900001-accept", "Синтетичне завдання.")
    assert(ui.PartText(900001, "accept") == "Welcome Fixture, take this letter.")
    uk.SoundLengthLookupByFileName = {}
    audioEntry(en, "900001-accept", "Synthetic English take.")
    assert(ui.PartText(900001, "accept") == "Synthetic English take.")
end

function gossip_matching()
    local e, uk, en = quests()
    local s = sound(e, true)
    assert(e.DataModules:GetNPCGossipTextHash(s) == "synthetic-moment")
    s.text = "unrelated words with zero overlap"
    assert(e.DataModules:GetNPCGossipTextHash(s) == nil)
    s = sound(e, true)
    e.UnitName = function() return "Other" end
    s.text = "Hello Other, take the northern road."
    assert(e.DataModules:GetNPCGossipTextHash(s) == "synthetic-moment")
    -- A non-client lookup with a single distinct moment is an explicit upstream heuristic.
    uk.LookupLocale = "ukUA"
    en.GossipLookupByNPCName = nil
    uk.GossipLookupByNPCName.Speaker = { ["Синтетичне привітання."] = "synthetic-moment" }
    s.text = "Unknown client words"
    assert(e.DataModules:GetNPCGossipTextHash(s) == "synthetic-moment")
    uk.GossipLookupByNPCName.Speaker["Інше синтетичне привітання."] = "other-synthetic-moment"
    assert(e.DataModules:GetNPCGossipTextHash(s) == nil) -- Two foreign moments cannot be guessed.
end

function gossip_audio()
    local e, uk, en = quests()
    uk.TextByFileName["synthetic-moment"] = "Синтетичне привітання."
    assert(not e.DataModules:PrepareSound(sound(e, true)))
    audioEntry(uk, "synthetic-moment", "Синтетичне привітання.")
    local s = sound(e, true)
    assert(e.DataModules:PrepareSound(s) and s.language == "ukUA" and s.packText == nil)
    e.Player:Prepare(s)
    assert(s.present.transcript == nil and s.priority == "low" and not s.textOnly)
    assert(e.Transcript:TextFor(s) == s.text)
    uk.SoundLengthLookupByFileName = {}
    audioEntry(en, "synthetic-moment", "Synthetic English greeting.")
    s = sound(e, true)
    assert(e.DataModules:PrepareSound(s) and s.language == "enUS" and s.packText)
    e.Addon.db.profile.Language.Fallback = "none"
    assert(not e.DataModules:PrepareSound(sound(e, true)))
    e, uk, en = quests(true)
    assert(not e.DataModules:PrepareSound(sound(e, true)))
    audioEntry(en, "synthetic-moment", "Synthetic English greeting with UK disabled.")
    s = sound(e, true)
    assert(e.DataModules:PrepareSound(s) and s.language == "enUS")
end

function places_audio()
    local e, p = Session({ text = "ukUA", voice = "ukUA" })
    e.GameFontNormal = e.GameFontHighlight
    e.C_Map = { GetMapInfo = function() return { name = "Synthetic map" } end }
    assert(p:GetLore(1429) and not p:HasAudio(1429))
    e.SpokenPlacesAudioPacks = { SyntheticUK = { version = 1, addon = "SyntheticUK", language = "ukUA",
        zones = { [1429] = { file = "1429/zone", len = 4.5, text = "Синтетичний запис." } }, subzones = {} } }
    assert(p:HasAudio(1429))
    local path, _, pack = p:GetAudioClip(1429)
    assert(path:find("1429/zone.mp3", 1, true) and pack.language == "ukUA")
    local clip = assert(p:NewLoreSound(1429))
    assert(clip.present.transcript == "Синтетичний запис." and clip.key == "z:1429")
    e.SpokenPlacesAudioPacks.SyntheticEN = { version = 1, addon = "SyntheticEN", language = "enUS",
        zones = { [1429] = { file = "1429/zone", len = 3, text = "English spoken words." } } }
    e.SpokenPlacesAudioPacks.SyntheticUK.zones[1429] = nil
    clip = assert(p:NewLoreSound(1429))
    assert(clip.present.transcript == p:GetLore(1429).full and clip.present.timings == nil)
    e.Addon.db.profile.Language.Fallback = "none"
    assert(p:NewLoreSound(1429) == nil and p:GetLore(1429))
    assert(p:GetLanguage() == "ukUA" and e.GetLocale() == "enUS")
    e.SpokenPlacesAudioPacks = nil
    assert(not p:HasAudio(1429) and p:GetLore(1429))
end

local function bosses()
    local e = base()
    local b = { L = e.L }
    upstream(e, "addons/Spoken_Bosses/Core.lua", b)
    e.SpokenBosses = { maps = { [99] = { { "Synthetic boss", key = "fixture" } } } }
    e.SpokenBossStories = { [99] = { fixture = "Synthetic English core story." } }
    e.SpokenBossesAudioPacks = { SyntheticUK = { version = 1, language = "ukUA",
        bosses = { [99] = { fixture = { text = "Синтетична історія." } } } } }
    upstream(e, "addons/Spoken_Bosses/Audio.lua", b)
    local ui = upstream(e, "addons/Spoken_Bosses/UI/Bosses.lua", b,
        "\nreturn { Story = Story, CoreStory = CoreStory }\n")
    return e, b, ui
end

function bosses_text()
    local e, b, ui = bosses()
    assert(b:PackStoryText(99, "fixture", "ukUA") == "Синтетична історія.")
    assert(b:GetAudioClip(99, "fixture") == nil)
    assert(ui.Story(99, "fixture") == "Synthetic English core story.")
    local clip = assert(b:StoryClip(99, "fixture"))
    assert(clip.textOnly and clip.path == nil and clip.language == "enUS")
    assert(clip.present.transcript == "Synthetic English core story.")
    e.SpokenBossesAudioPacks = nil
    assert(b:StoryClip(99, "fixture").textOnly and ui.Story(99, "fixture"))
end

function bosses_audio()
    local e, b, ui = bosses()
    local entry = e.SpokenBossesAudioPacks.SyntheticUK.bosses[99].fixture
    entry.file, entry.len, entry.times = "99/fixture", 4.5, { 0, 1 }
    local clip = assert(b:StoryClip(99, "fixture"))
    assert(clip.language == "ukUA" and clip.path and not clip.textOnly)
    assert(clip.present.transcript == "Synthetic English core story." and clip.present.timings == nil)
    e.SpokenBossesAudioPacks.SyntheticEN = { version = 1,
        bosses = { [99] = { fixture = { file = "99/fixture", len = 4, text = "English pack story." } } } }
    entry.file = nil
    assert(b:GetAudioClip(99, "fixture").language == "enUS")
    assert(ui.Story(99, "fixture") == "English pack story.")
    e.Addon.db.profile.Language.Fallback = "none"
    assert(b:GetAudioClip(99, "fixture") == nil and b:StoryClip(99, "fixture").textOnly)
    e.SpokenBossStories[99].fixture = nil
    entry.file = "99/fixture"
    assert(b:GetAudioClip(99, "fixture") and b:StoryClip(99, "fixture") == nil)
    assert(e.GetLocale() == "enUS")
end

function core_text_only()
    local e = base()
    local whyRefused = upstream(e, "addons/Spoken/SoundQueue.lua", nil,
        "\nreturn WhyRefused\n")
    e.Sources = { IsTurnedOff = function(_, source) return source.off end }
    e.SoundUtils = { WhyInaudible = function() error("Text-only must not ask an audio channel") end }
    assert(whyRefused({}, { textOnly = true }) == nil)
    assert(whyRefused({ textOnly = true }, {}) == nil)
    assert(whyRefused({ off = true }, { textOnly = true }) == "PART_TURNED_OFF")
end
