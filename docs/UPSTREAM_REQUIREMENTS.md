# Proposed upstream runtime requirements

Design only, based on Spoken `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`.
No interfaces described here have been implemented in this project or accepted by
the maintainer. See [compatibility evidence](STAGE_2B_COMPATIBILITY.md) for pinned
functions, reproduced limitations and the unanswered Readables question in #1123.

## 1. Readables audio safety, independently shippable

`Audio.lua:239–300` (`ClipFor`) and `329–342` (`HasAudio`) need the same predicate
for an actual recording entry. `PageLength:305–316` must skip text-only entries too,
so it describes the recording the resolver would choose. `Playlist:PlayFrom` and
the Compendium's Play/Voiced Only controls must continue to mean recorded audio.

Illustrative pseudocode, **not a player patch**:

```lua
local function IsAudioEntry(entry)
    return type(entry) == "table"
        and type(entry.file) == "string" and entry.file ~= ""
end

-- Same language/priority order and canonical page id as today.
-- FindAudioEntry(pageId) -> entry, pack, language | nil
-- Missing file: continue to the next pack/language, never concatenate nil.
-- HasAudio(pageId) -> FindAudioEntry(pageId) ~= nil
-- ClipFor(pageId) -> existing audio clip, or nil
-- PageLength(pageId) -> chosen audio entry's positive len, or nil
```

A missing duration remains permissible where the existing imported-clip contract
allows it; no guessed duration or silent file is introduced. Existing format-1
audio packs retain discovery, sorting, paths, timings and legacy registry behavior.
`HasAudio` cannot prove disk presence: a pack must actually ship the referenced
MP3, and ordinary playback rejection must remain recoverable. Authoring validation
should check files separately, without changing the runtime meaning of text.

This fix is useful even before independent Ukrainian text display. It prevents the
reproduced exception and lets a text-only entry coexist with real fallback audio.
It does **not** alone satisfy Ukrainian Compendium display.

## 2. Readables text registration and selection

The smallest safe extension should reuse canonical `b:<pageID>` and existing
book/page/owner structure, with separate text availability and audio availability.
An optional text registry keeps unsafe entries out of old players' audio registry.
Illustrative public interface:

```lua
-- Proposed, capability-detected public API; names subject to upstream agreement.
SpokenReadables:RegisterTextData(folder, {
    version = 1, language = "ukUA",
    pages = { [canonicalPageID] = { text = "Original synthetic example." } },
    -- Optional titles keyed by canonical book id; no title-as-identity matching.
    titles = { [canonicalBookID] = "Synthetic title" },
})

SpokenReadables:HasText(pageID, language)       -- nonempty text, no audio requirement
SpokenReadables:TextFor(pageID, language)       -- text, actualLanguage | nil
SpokenReadables:TitleFor(bookID, language)      -- title, actualLanguage | nil
SpokenReadables:GetTextLanguage()              -- independent content preference
SpokenReadables:SetTextLanguage(codeOrDefault) -- validate installed text capability
```

Keep `PackPageText` as a compatible lookup into existing audio packs' text. The new
resolver can also read the text registry and existing corpus/remembered words.
Define deterministic precedence, e.g. existing audio-pack words before separate
text-pack words within the same language, then corpus/session text as appropriate.
Sort same-class packs by folder as today. Return the actual selected language so
titles, report links, fonts and timing decisions describe the words displayed.
Maintainers should confirm precedence before implementation.

A future text pack can declare the existing `X-SpokenReadables-Language`, language
name/native/font metadata and a dependency on the first supporting release. Its
loader must feature-detect the text API and safely decline registration on older
players; it must **not** put a no-file page in `SpokenReadablesAudioPacks` as fallback.
The Manager already has a readables section, but minimum-player capability/version
checks and text-only pack labeling need maintainer agreement. No release number
or undocumented TOC key is promised here.

An additive format-1 audio-reader guard is backward compatible for existing valid
packs. It does not make new no-file audio entries safe on old readers. Therefore
an optional separate registration API is preferable to advertising those entries
as a universally compatible format-1 text pack. If upstream chooses a new format
instead, old readers must reject it safely, and the change must be negotiated.

## 3. Independent text and voice policy

Keep these axes distinct:

| Axis | Role / required behavior |
| --- | --- |
| Actual client locale | `GetLocale()` remains enUS; recognition indexes and game API labels still use it |
| Content text preference | Optional per-module setting, separate from voice and interface labels |
| Voice language + fallback | Existing shared choice, English fallback or Stay Silent, resolved per recording |
| Interface language | Outside this proposal; changing it must not change matching identity |

Unset/default text preference must preserve existing behavior: Readables' current
non-client voice caption preference, client-language Compendium, Quests' current
captured/client text, Places' existing Text Language and Bosses' client-selected
core story. Do not silently turn “Auto voice” into Ukrainian or change default
English behavior. An explicit text selection is the opt-in extension.

For an explicit `ukUA` content selection, resolve text independently per unit:
selected language → actual client language → English → no text. Deduplicate codes;
return the actual language. A missing/disabled text pack must invalidate cached
availability and fall back without erasing the user's stored preference. Changes
to selectors must refresh title/page caches; if reload is required, say so in the
settings UI. For Places, preserve its existing reload/readiness behavior and absence
of per-entry English text fallback unless upstream separately opts to generalize it.

`Stay Silent` controls missing voice, not availability of readable text. With UK
text and English voice, show UK words without English word timings. With UK voice
and English text, omit UK word timings. Language equality is necessary but may not
be sufficient: apply timing marks only when text is the selected recording's exact
words, retaining existing `recorded` checks. Use fonts appropriate to actual text;
language-menu glyph success alone does not prove every caption style can draw it.

Readables' `UI/Readables:Title`, `EachText`/`Words`/`HasWords` should consume this
resolver. `Reader:CaptionText` should honor explicit selection while retaining its
present default behavior. `HasAudio`/Play remain recording-only. A text-only
Compendium page is a complete useful feature without any narrator queue item.
If upstream later wants “Read silently,” make that a separate explicit action using
the existing `textOnly` clip contract, rather than making the audio Play button lie.

## 4. Quests and Gossip follow-up

`DataModules:ResolveSoundFile` (1110–1192) currently obtains `TextByFileName` only
while resolving a duration entry, and only in the client's language. Add a text
resolver addressed by **existing canonical moment**, separate from audio resolution:

```lua
-- Illustrative only:
DataModules:TextForMoment(canonicalID, textLanguage, playerContext)
    -- -> displayTemplate, actualLanguage, provenance | nil
```

Resolve the source identity before applying translated display words. Matching
still uses `LookupLocale`/`ClientLocaleLookups`, quest ID/event/wording and speaker;
never match a native English dialog against the translated caption as a shortcut.
Keep speaker/wording/gender/voice variants and aliases stable. Gossip numeric
ClassicUA hashes never enter this API as Spoken IDs.

`Player:Prepare` should use independently selected text and correct timing provenance;
`QuestsTab:PartText` should call the same text resolver without needing a recording.
Any text-only narrator mode must explicitly construct a `textOnly` clip after a
confirmed match, and must preserve module enablement and avoid muting game dialogue.
Do not broaden fuzzy matching to force a caption for an unmatched page. Ukrainian
case templates need a separately reviewed rendering contract, beyond this API.

## 5. Places and Bosses follow-up

Places already separates lore and recordings. Preserve `RegisterLoreData`, its
TOC/font guards, selection/reload and `NewLoreSound` behavior. Do not infer that its
readiness declaration proves complete Ukrainian story coverage. No required Places
patch is proposed for the Stage 1 supported surface.

Bosses can reuse its existing safe text-only clip primitive. Introduce a public
story resolver/optional text registration rather than replacing generated core tables:

```lua
-- Illustrative only, not an implemented contract:
Bosses:StoryText(mapID, canonicalKey, textLanguage) -- text, actualLanguage | nil
Bosses:RegisterStoryText(folder, language, storiesByMapAndCanonicalKey)
```

`UI/Bosses:Story` (174–181) should use it for explicit content selection; `StoryClip`
(397–429), Compendium and encounter/map story surfaces should share that answer.
Allow a registered story for an already known canonical boss lacking a core story,
without minting a new boss from a name. Preserve the existing English/client default
and audio fallback. Ukrainian audio must not be reported as Ukrainian text where
the transcript is English. Bosses Manager distribution remains a separate question.

## Acceptance for a future upstream implementation

Before changing the source pin, review the new revision and add parity tests showing:

1. No-file and empty-file Readables entries cannot claim audio or crash; fallback
   proceeds. Existing valid audio/legacy packs behave identically.
2. An explicit UK text choice shows mapped text/title with no recording and English
   client recognition, without altering `GetLocale` or audio choice.
3. Missing text/voice, disabled module/pack, stale settings, partial books, reload,
   cache refresh, fonts and both fallback choices work independently.
4. Caption timings follow the actual take text, not a translation. Default users
   retain their previous captions, titles and queue behavior.
5. Native game frames and ClassicUA hook ordering are tested separately in Forever;
   enUS recognition and canonical identities remain intact.

## Proposed issue/PR description — not submitted

**Title:** Separate Readables text availability from audio and allow explicit content language

At Spoken `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`, a format-1 readable page
containing text but no file makes `HasAudio` return true and makes `ClipFor`/`PlayFrom`
raise a nil-concatenation error. An installed English fallback does not avoid it.
On an enUS client, selecting a non-client voice language also leaves Compendium
text selected in English, although a real recording can carry non-client captions.

Propose two small changes: share a safe recording-entry predicate across audio
availability/resolution, then add optional public text registration and independent
content selection for titles/pages/captions. Keep current defaults, canonical page
IDs, matching indexes, valid format-1 audio packs and legacy registries unchanged.
Use a separate text API so older players never load unsafe no-file audio entries.

Reproduction: this project's offline `RuntimeCompatibilityTests` executes the
original pinned Lua, models enUS plus ukUA, expects the current error and checks
client-based Compendium selection. It creates or plays no audio. Forever
reproduction is still pending; attach the completed isolated manual record before
claiming game validation. No change has been submitted to upstream.

Maintainer questions: Is a separate optional text registry preferred over a new
format? What default/explicit text fallback and pack precedence should be public?
Should one shared content setting cover captions and Compendium, with Places
retaining its current setting? Which release/capability should a text pack require?
Can the readables listing represent text-only capabilities? Are there unpublished
changes addressing #1123? Could Bosses story registration follow later without a
Manager section? Interface localization, paid TTS, production data, automatic
mapping, player forks, native-frame hooks and releases are outside this proposal.
