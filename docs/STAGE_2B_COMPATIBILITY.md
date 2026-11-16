# Stage 2B runtime compatibility

Offline characterization completed on `feat/spoken-runtime-compatibility`, 2026-11-16.
Stage 2B Forever acceptance remains **pending**. Existing Stage 1 user-reported
diagnostic acceptance is preserved; it does not cover the additional modules here.

Every baseline result below uses Spoken **P = `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`**
(3.9.0), `GetLocale() == "enUS"`, and independently declared non-client `ukUA`.
No upstream code, installed addon, source lock or project version was changed.

## Evidence and source references

`E` means executed original pinned Lua function bodies, with synthetic inputs and
essential host fixtures; `S` means inspected source, without executing that surface.
“With audio” below means the valid clip metadata/path contract was exercised. No
MP3 was created, tested for existence or played. Audible behavior requires a real,
authorized recording and the manual checks in [testing](STAGE_2B_TESTING.md).

All paths in this table belong to P; links are immutable source permalinks. The
Stage 2B SHA-256 manifest is [tests/stage2b_sources.json](../tests/stage2b_sources.json);
existing locked files retain their hashes in `sources.lock.json`.

| Ref | Pinned functions and source range |
| --- | --- |
| L | [Spoken/Languages.lua:65–184](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken/Languages.lua#L65): `Declare`, `Scan`, `Get`; [API.lua:502–579](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken/API.lua#L502): shared language choice and `VoiceLanguage` |
| R-A | [Readables/Audio.lua:125–342](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Readables/Audio.lua#L125): `Listable`, `BuildAudioPacks`, `ClipFor` (239–300, path at 266), `PageLength`, `HasAudio` (329–342) |
| R-T | [Readables/Reader.lua:320–595](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Readables/Reader.lua#L320): `PageOnScreen`, `PackPageText` (391–399), `CaptionText` (459–471), `TitleIn`, `PlaceOf`, `BookById`; player templates at 154–193 |
| R-U | [Readables/UI/Readables.lua:86–101](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Readables/UI/Readables.lua#L86): `Title`; [407–433](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Readables/UI/Readables.lua#L407): `EachText`, `Words`, `HasWords` |
| R-P | [Readables/Playlist.lua:184–245](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Readables/Playlist.lua#L184): `PlayFrom`; [Language.lua:70–131](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Readables/Language.lua#L70): client, voice, fallback order |
| Q-D | [Quests/DataModules.lua:179–237, 293–352](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Quests/DataModules.lua#L179): `Register`, `GetModules`, `EnumerateAddons`; [465–506, 641–705](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Quests/DataModules.lua#L465): `TextLookup`, `GossipLookupKey`, `CollectTexts`, `GetNPCGossipTextHash` |
| Q-A | [Quests/DataModules.lua:898–927, 1070–1192](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Quests/DataModules.lua#L898): `QuestFile`, `PrepareSound`, `ResolveSoundFile`, gender filename selection; caption gate at 1158–1164 |
| Q-P | [Quests/Player.lua:237–270, 304–385](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Quests/Player.lua#L237): `Prepare`, `Enqueue`; [Spoken/UI/Transcript.lua:125–137](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken/UI/Transcript.lua#L125): `CleanText`, `TextFor` |
| Q-U | [Quests/UI/QuestsTab.lua:109–149, 965–995](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Quests/UI/QuestsTab.lua#L965): `Locale`, `Kept`, `Stored`, `SeenText`, `PartText` |
| P-L | [Places/Language.lua:136–354, 430–460](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Places/Language.lua#L136): readiness, glyph guard, independent selection, `RegisterLoreData`; [Core.lua:206–273](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Places/Core.lua#L206): `GetMapName`, `GetLore`, ancestor fallback |
| P-A | [Places/Audio.lua:185–438, 497–565](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Places/Audio.lua#L185): `GetAudioPacks`, `GetActiveAudioPack`, `GetAudioClip`, `NewLoreSound` |
| B-A | [Bosses/Audio.lua:10–106](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Bosses/Audio.lua#L10): voice/fallback, `GetAudioPacks`, `PackStoryText`, `GetAudioClip` |
| B-U | [Bosses/UI/Bosses.lua:37–39, 160–181](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Bosses/UI/Bosses.lua#L160): `Name`, `CoreStory`, `Story`; [397–429, 483](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Bosses/UI/Bosses.lua#L397): `StoryClip`, Compendium `ShowEntry` |
| C | [Spoken/SoundQueue.lua:503–539, 652–669](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken/SoundQueue.lua#L652): `PlaySound`, `WhyRefused`; [API.lua:107](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken/API.lua#L107): generic `textOnly` clip contract |

## Module × surface × audio matrix

All rows are revision **P** as defined above. Test names below are exact Lua
characterization entry points in `tests/runtime_contract.lua` (their Python unittest
names are listed in [testing](STAGE_2B_TESTING.md)); **all passed**. `Stage1` refers
to the unchanged `tests/contract.lua` checks. Passing a limitation test confirms the
limitation; it does not mean Ukrainian display now works.

“Missing” means disabled/removed at load followed by reload, or no matching entry.
Fallback applies independently to voice and text. Manual IDs refer to the pending
Forever checklist in the testing document.

| Module / surface | Audio | Source at P | Status on enUS + ukUA; fallback / missing | Evidence | Minimum extension; manual |
| --- | --- | --- | --- | --- | --- |
| Readables / text lookup | None, text-only entry | R-A, R-T | Supported programmatic access; `PackPageText(id,"ukUA")` returns words. Missing returns nil. This is not a displayed page. | E `readables_text_without_file` | Separate public text capability; M-R |
| Readables / audio availability + Play | None, text-only entry | R-A, R-P | **Unsafe**: `HasAudio=true`, `PageLength=nil`; `ClipFor` and `PlayFrom` fail on nil `file` before queue submission, even with valid English fallback. Absent page safely returns false/nil. | E `readables_text_without_file` | Guard audio entries and continue fallback; M-R isolated reproduction |
| Readables / audio availability + Play | Valid clip metadata | R-A, R-P | Conditional audio contract works; `b:<pageID>`, correct pack-relative MP3 path and duration; `PlayFrom` submits a clip to a recording-only queue stub. | E `readables_audio` | No audio format change needed; M-A |
| Readables / narrator captions | None | R-T, R-P | Unsupported normal text-only narration: no clip or the error above. Caption helper alone can return text but is not a queue path. | E `readables_text_without_file` | Optional explicit text-only presentation, separate from Play; M-R |
| Readables / narrator captions | Ukrainian clip metadata | R-T, R-A | Conditional Ukrainian: non-client clip language wins. Without Ukrainian words, English corpus captions remain, with no Ukrainian word timings. Missing pack uses English voice fallback, or silence. | E `readables_audio`, `readables_fallback` | Preserve default; optional independent text setting; M-A |
| Readables / Compendium title + page | None | R-U, R-T | Ukrainian unsupported; client-language words/title, then English corpus. No independent text-language setter. Missing/disabled UK leaves English. | E `readables_compendium` | Independent text selection and `TextFor`/`HasText`; M-R |
| Readables / Compendium title + page | Ukrainian clip metadata | R-U | Still English: choosing Ukrainian voice does not change the text selector. English pack words may override English corpus text. | E `readables_compendium`, `readables_audio` | Same text change; M-R, M-A |
| Readables / native ItemTextFrame | None | R-T `PageOnScreen` | Spoken identifies original client pages; no Ukrainian frame replacement established. ClassicUA may separately change the frame and recognition input. | E `readables_matching` for English recognition/mail/templates; S native surface | Native translation out of scope; M-C |
| Readables / native ItemTextFrame | Valid clip metadata | R-T, R-A | Same native-frame boundary; narration does not prove frame translation. | S | None proposed; M-C, M-A |
| Quests / narrator caption + queue | None | Q-A, Q-P | Independent Ukrainian text unsupported. `TextByFileName` without duration lookup never queues; no module text-only fallback. Missing UK → English audio if present, otherwise no clip. | E `quests_audio`, `quests_fallback` | Text lookup separate from `PrepareSound`, explicit caption selection; M-Q |
| Quests / narrator caption + queue | Ukrainian clip metadata | Q-A, Q-P | Clip resolves, but Ukrainian `packText`/timings are nil; narrator `TextFor` uses the captured client dialog. Accept/progress/complete tested. English fallback supplies English pack words/timings. | E `quests_audio`, `quests_fallback` | Remove coupling to client locale through opt-in text choice; M-Q, M-A |
| Quests / Compendium parts | None | Q-U | Client/corpus English can display without audio. Ukrainian pack words are not selected; no English-client remembered-text table. Missing UK preserves corpus. | E `quests_compendium` | Public canonical moment text resolver; M-Q |
| Quests / Compendium parts | Ukrainian clip metadata | Q-U, Q-A | Still client/corpus text. English fallback audio can supply English take words. | E `quests_compendium` | Same text resolver; M-Q, M-A |
| Quests / native quest frames | None | Q-D, Q-A | No independent pack-driven Ukrainian frame translation established; matching consumes captured text. ClassicUA may alter it. Unmatched wording refuses playback. | E `quests_fallback` for rejected wording; S native frame | Native UI out of scope; M-C |
| Quests / native quest frames | Valid clip metadata | Q-P | Same boundary; voice selection is not native localization. | S | None proposed; M-C, M-A |
| Gossip / narrator caption + queue | None | Q-D, Q-A, Q-P | Matched moment without duration lookup does not narrate Ukrainian text; missing/disabled UK allows English fallback only when it has audio. | E `gossip_audio` | Separate moment text resolver + explicit text-only opt-in; M-G |
| Gossip / narrator caption + queue | Ukrainian clip metadata | Q-A, Q-P | Ukrainian audio contract resolves; Ukrainian pack captions/timings discarded on enUS. Captured client text supplies caption. Stay Silent suppresses fallback. | E `gossip_audio` | Same caption contract as Quests; M-G, M-A |
| Gossip / identity matching | None | Q-D | Lookup locale differs from voice language. Exact/fuzzy player-token matching works; unmatched client text returns nil. With only foreign lookups, one distinct moment can be selected heuristically; two unrelated moments are refused. | E `gossip_matching` | Keep matching language independent; no numeric ClassicUA hash conversion; M-G, M-C |
| Gossip / identity matching | Valid clip metadata | Q-D, Q-A | Match first, then resolve same moment in voice/fallback language. Audio does not repair an unmatched page. | E `gossip_audio`, `gossip_matching` | Preserve identity rules; M-G, M-A |
| Gossip / native dialog | None | Q-D | Game/ClassicUA owns native words. No independent Spoken pack frame translation established. | S; synthetic matching E as above | No native UI proposal; M-C |
| Gossip / native dialog | Valid clip metadata | Q-P | Same native boundary, regardless of recording language. | S | None; M-C, M-A |
| Places / lore panel + Compendium data | None | P-L | Supported diagnostic Ukrainian lore via TOC + `RegisterLoreData`, text selection + reload + drawable font. Removed/disabled pack or font rejection → English selection. A missing selected-language record has **no per-record English text fallback**; ancestor fallback is geographical. | E Stage1 `check_registration_order`, `check_separate_settings_and_reload`, `check_font_guard`, `check_disabled_and_removed`; S missing-record semantics | No required extension; M-P |
| Places / lore panel + Compendium data | Valid clip metadata | P-L, P-A | Same independent text selection; changing voice preserves selected lore. Removing audio preserves text. | E `places_audio` + Stage1 settings checks | Preserve existing contract; M-P, M-A |
| Places / narrator + audio availability | None | P-A | Lore remains readable, `HasAudio=false`, `NewLoreSound=nil`, `PlayLore=false`; no audio-free narrator clip. | E Stage1 `check_no_audio`, `places_audio` | Optional text-only narrator outside minimum scope; M-P |
| Places / narrator + audio availability | Valid clip metadata | P-A | Conditional recording path; Ukrainian text with UK voice, selected Ukrainian lore under English fallback voice without mismatched timings. Stay Silent removes clip, keeps lore. | E `places_audio` | No required change; M-P, M-A |
| Places / native map labels | None | P-L `GetMapName` | Client map labels can remain English. Lore registration does not translate the native map. | S | None; M-P, M-C |
| Places / native map labels | Valid clip metadata | P-L | Same client-label rule. | S | None; M-P, M-A |
| Bosses / Compendium + encounter story selection | None | B-U, B-A | UK pack text is accessible but display stays English. `Story` requires a core story, then asks the pack in `GetLocale()`. Missing pack preserves core. | E `bosses_text`, `bosses_audio` for missing core; S final UI rendering | Independent public story resolver by stable map/key; M-B |
| Bosses / Compendium + encounter story selection | Ukrainian clip metadata | B-U | Still English; even a valid UK recording does not change selected story. Missing core prevents `StoryClip` despite an available recording. | E `bosses_audio`; S final encounter UI/event dispatch | Same story resolver; M-B, M-A |
| Bosses / narrator + audio availability | None | B-U, B-A | Safe English `textOnly=true` clip with no path. UK text-only pack does not set an audio flag. | E `bosses_text` | Generalize text choice, retain text-only primitive; M-B |
| Bosses / narrator + audio availability | Ukrainian clip metadata | B-U, B-A | UK clip language/path with **English transcript**, timings omitted across language mismatch. Missing UK file → English fallback audio or English text-only core story under Stay Silent. | E `bosses_audio` | Explicit selected text and separate voice language; M-B, M-A |
| Bosses / native names + encounter UI | None | B-U `Name`; Bosses/Core.lua encounter mapping | Client names/English fallback; no UK native translation proven. | S | Native translation out of scope; M-B, M-C |
| Bosses / native names + encounter UI | Valid clip metadata | B-U | Same label rule, independent of audio. | S | None; M-B, M-A |

Gossip has no separate Compendium text reader established here. Places and Bosses
are their own Compendium surfaces, not evidence about the Readables page selector.

## Exact Readables blockers and registration

Format 1 currently registers in `SpokenReadablesAudioPacks[folder] = { version=1,
language="ukUA", pages=... }`; `books`, `places`, `index` and `extraIndex` can add
structure and recognition. The TOC language metadata or Lua language declaration
registers a language; it does not authorize a text selector or prove audio exists.
`Core:Data` reads the corpus; `Reader:PlaceOf`/`BookById` can supplement it from packs.
These IDs and structures remain canonical across languages.

The synthetic text-only page passes pack discovery and `PackPageText`. It then
falsely passes `HasAudio` and raises a nil-concatenation error in `ClipFor`, propagated
by `PlayFrom` before submission. The tests explicitly expect this error, and also
show that a valid English fallback entry cannot bypass the broken selected-language
entry. This is an **audio-safety** defect. Guarding `file` and continuing the resolver
would prevent the error, but would still leave the Ukrainian Compendium unavailable.

The separate **display** gate is `EachText`'s `GetClientLanguage()` argument and
`Title`'s client-based choice. `CaptionText` deliberately has a different rule:
a non-client recording language is tried first. Consequently genuine UK audio can
have UK narrator captions while its Compendium page remains English. Calling that
helper programmatically without audio is not a supported text-only UI path.

The minimum upstream proposal is described in [requirements](UPSTREAM_REQUIREMENTS.md):
audio safety first; then an optional text registry and independent text selection,
with default behavior preserved. A safe reader need not enqueue text-only narration
to offer a Compendium page.

## Load order, matching and ClassicUA coexistence

Readables loads checksum/data/locales, Core, Language, Reader, Audio, Playlist and UI.
Bosses loads Core/data, Audio, then UI; story and event wiring comes later. Quests'
TOC delegates to `addon.xml` (Enums/Utils/Language before DataModules/Player), then
its Compendium XML. Its load-on-demand pack must be enumerated before `Register`;
an unenumerated pack raises an assertion. Tests preserve relative order of executed
files while supplying synthetic data and omitting unused event/UI infrastructure.
They do not claim to execute the full TOCs or addon lifecycle.

Quest IDs/events, original wording, speaker and player templates identify a line.
Gossip's client lookup can remain `enUS` while its recording language is `ukUA`;
`LookupLocale` and `ClientLocaleLookups` are matching inputs, not caption settings.
Tests use invented moment identifiers, not a crosswalk. ClassicUA numeric hashes
are not Spoken moment IDs, and item IDs are not readable page IDs.

ClassicUA's hooks may translate native quest/gossip/book frames without changing
`GetLocale`. Spoken captions instead consume pack transcripts or captured window
text, and Compendium surfaces have their own selectors. If a hook changes the text
before Spoken captures it, a client-worded match may fail; if Spoken captures it
first, English matching may survive. A Ukrainian captured caption, if observed,
would demonstrate ClassicUA coexistence for that event order, not a pack-driven
independent text API. Actual hook timing is unverified; see M-C. Stage 2A synthetic
template tests remain intact; Ukrainian grammatical cases are not implemented by
Spoken's English name/class/race token filling.

## Current upstream evidence, separate from P

Read-only GitHub checks on 2026-11-16 found [issue #1123](https://github.com/rusty-key/spoken-wow/issues/1123)
open with two comments. The collaborator's [guide referral](https://github.com/rusty-key/spoken-wow/issues/1123#issuecomment-6906425492)
does not answer the later [Readables text-only question](https://github.com/rusty-key/spoken-wow/issues/1123#issuecomment-6911281526).
There was **no maintainer answer to that question** in the retrieved discussion.
Searches for `readables language` and `"text-only" readables` in that repository
found no separate fix establishing this capability. This is a bounded search,
not proof that no relevant unmerged work exists.

The [current Community Packs guide](https://github.com/rusty-key/spoken-wow/blob/master/community/README.md)
describes metadata registration and Places lore; it does not establish an independent
Readables text-only contract. Its Manager sections are quests, places and readables;
Gossip belongs to quests and Bosses cannot currently be listed separately.

Among the ten most recent releases returned, the newest player release was
[Spoken 3.9.0](https://github.com/rusty-key/spoken-wow/releases/tag/spoken/v3.9.0),
published 2026-11-14; its notes discuss pack transcripts and dynamic languages,
not a promised fix to these reproduced gates. Manager releases are separate.
No pin was advanced and no current branch implementation was substituted for P.

## Stage 3 recommendation and remaining gates

Stage 2B research and executable characterization are delivered; new manual game
acceptance is pending. The first safe current text surface remains Places lore,
under its existing authorship/font gates. Prioritize an upstream Readables safety
fix and text API discussion before choosing it as the first translated text-only pack.

When separately authorized, Stage 3 can prepare reviewed canonical ID evidence
offline even for blocked surfaces. Follow `STAGE_3_SPECIFICATION.md`: preserve
crosswalk identity across revisions, pin hashes, compare effective resolved source,
invalidate changed translation/grammar/audio reviews, and reject ambiguity. No
mapping or updater was implemented here. Runtime support, grammar review, rights
and audio availability must remain separate readiness fields.

ClassicUA's scoped translation/adaptation/TTS/distribution grant and attribution
are recorded in [CLASSICUA_PERMISSION.md](CLASSICUA_PERMISSION.md). Its historic
“unresolved” lock note does not override that subsequent permission. Authored
Places/Bosses stories, fonts and provider terms still need their own review.
The grant does not authorize this task to generate audio or publish content.
