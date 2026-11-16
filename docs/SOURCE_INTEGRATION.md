# Spoken Ukrainian source integration

Stage 0, inspected 2026-11-16. This document describes contracts and proposed adapters, not an implemented integration. No ClassicUA translation text is included here.

## Reproducible source baseline

| Source | Revision inspected | Role |
| --- | --- | --- |
| [Spoken](https://github.com/rusty-key/spoken-wow/tree/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7) | `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`, local checkout | Player contracts, module data, naming and packaging |
| [ClassicUA](https://github.com/greenya/ClassicUA/tree/1770d208ad853d23d61105cf510d53804770d916) | `1770d208ad853d23d61105cf510d53804770d916`, version 7.1.1 | Intended Ukrainian source and terminology |
| [Spoken French](https://www.curseforge.com/wow/addons/spoken-french) | Live project page, observed 2026-11-16; listed meta package 1.1.0 | Product reference, not a source adapter |

ClassicUA's commit API identified the revision; files were read at that SHA. Large files were inspected in temporary storage outside the project. The recursive tree was also checked for license filenames. Future builds must pin commits and file hashes, never resolve a moving branch silently. The French page describes a dependency meta package that fetches the player and French audio packs. It does not establish Ukrainian runtime compatibility.

Read alongside [compatibility](COMPATIBILITY_MATRIX.md), [permissions](LEGAL_AND_ATTRIBUTION.md) and [roadmap](IMPLEMENTATION_PLAN.md).

## Spoken discovery and language metadata

The current [Community Packs guide](../community/README.md) is the distribution contract. The website accepts `quests`, `places`, and `readables`, not a separate gossip or bosses section. Gossip belongs to Quests. Bosses can load locally but cannot currently be listed as a Bosses community pack.

The Manager discovers approved submissions on the website. `community/packs.json` is frozen for old Managers, not a submission mechanism. Publication later requires a GitHub release asset, immutable pack id/language/section, increasing version, ZIP size and SHA-256, and administrative review. None of those publication operations is part of Stage 0 or Stage 1.

A community ZIP has exactly one root folder, `SpokenCommunity_<id>`, containing a matching `.toc`. Paths must be relative, use forward slashes in the archive, and contain no traversal. Runtime discovery uses TOC metadata and Lua registration, not the folder prefix:

| Module | Runtime discovery |
| --- | --- |
| Quests and Gossip | `X-SpokenQuests-DataModule-Version: 1`; legacy `X-VoiceOver-DataModule-*` also supported. Loader enumerates packs, then pack calls `VoiceOver.DataModules:Register(folder, module)`. Use the upstream load-on-demand pattern, not an eager registration before enumeration. |
| Places audio | `SpokenPlacesAudioPacks[folder]`, format `version = 1`, with zone/subzone clip tables |
| Places text | TOC declares Places language and lore; Lua calls `SpokenPlaces:RegisterLoreData(code, "zones", data)` and/or `"subzones"` |
| Readables | `SpokenReadablesAudioPacks[folder]`, `version = 1`, `pages` table; optional `books`, `places`, `index`, `extraIndex` |
| Bosses | `SpokenBossesAudioPacks[folder]`, `version = 1`, `bosses[map][key]`; set Lua `language` as well as the TOC language |

Evidence: `addons/Spoken/Languages.lua:80` and `:110`, `addons/Spoken_Quests/DataModules.lua:1`, `addons/Spoken_Readables/Audio.lua:125`, `addons/Spoken_Bosses/Audio.lua:32`, and Places `Language.lua:450`.

Use `X-SpokenQuests-Language`, `X-SpokenPlaces-Language`, `X-SpokenReadables-Language`, or `X-SpokenBosses-Language` with `ukUA`. All accept the `xxYY` shape. Missing or invalid metadata defaults to English. `X-Spoken-LanguageName: Ukrainian` and `X-Spoken-LanguageNative: Українська` provide names for a non-client language. The first installed pack providing a name wins. `X-Spoken-LanguageFont` is a pack-relative font path and needs separate redistribution rights. It affects language names and Places lore; it does not automatically set every module's caption font. Clips can use `present.font`.

`ukUA` is registered as a non-client language (`client = false`). Do not override `GetLocale`, mark Ukrainian as a client locale, or relabel Ukrainian data as `enUS`. Voice Auto follows the real client; users must explicitly select Ukrainian. Interface language, voice language, Places text language, matching locale, and source language are separate concerns.

## Runtime display is not offline preparation

The core supports `textOnly` sources/clips (`addons/Spoken/API.lua`, `SoundQueue.lua`), but a module must actually construct one. That capability alone does not make every module a text-only translation reader.

* Places supports Ukrainian lore pages without audio. Set `X-SpokenPlaces-Lore: 1`; installed metadata establishes readiness for a community language. Selection still checks glyph rendering. Registering lore replaces that language's whole `zones` or `subzones` table, so emit one combined table per kind rather than repeatedly registering individual rows. Users select the Places text language and reload. `NewLoreSound` still returns nil without audio (`Audio.lua:497`): reading a lore page and narrator playback are different paths.
* Quests and Gossip require resolved audio for their normal queue. `DataModules:ResolveSoundFile` (`:1110`) requires a filename in `SoundLengthLookupByFileName` and builds a sound path. `TextByFileName` and timings are used only when the recording language equals `Language:GetClientLanguage()`. Selecting Ukrainian voice on an English client does not make its Ukrainian pack text appear. ClassicUA may independently translate the game's quest/gossip frames, but that is ClassicUA's runtime behavior, not Spoken Community Pack text support.
* Readables can list a format-1 pack whose `pages` entries have text. This is not a safe text-only playback contract: `ClipFor` (`Audio.lua:239`) concatenates `entry.file` unconditionally, and `HasAudio` treats a page entry as audio. A text-only page can therefore trigger a nil concatenation or falsely claim audio. `UI/Readables.lua:408` selects page words by client language. `CaptionText` in `Reader.lua` prefers the clip language for non-client voices, so a real Ukrainian recording can have Ukrainian captions. That does not solve audio-free Ukrainian Compendium display on an English client. Do not add dummy files, durations, silence, or misleading language metadata to bypass this.
* Bosses already creates text-only story clips (`UI/Bosses.lua:396`) when no recording exists. However, its story selection first requires a core story and looks for pack text in `GetLocale()`, not the selected voice language (`CoreStory`/`Story` in that file). Ukrainian text-only stories on an English client are therefore not provided by selecting `ukUA`. Names also follow the client. The presence of `PackStoryText` is not a complete arbitrary-language text API.

These are verified code limitations at the inspected revision, not claims of in-game testing. Before proposing player changes, reproduce them in a strict Lua harness and WoW Forever, then seek an upstream extension to the public module contract. Keep the player external while that work is considered.

## Frozen identities and matching

| Content | Identity and mapping rule |
| --- | --- |
| Quest dialogue | `q:<questID>:accept`, `:progress`, `:complete`; alternate wordings `:w<n>`, optional player-sex `:m`/`:f`, voice variant `~<voice>`. Audio stems use `<questID>-<source>`, `-w<n>`, sex prefixes and voice suffixes. Match quest ID and source event, then validate wording and speaker. |
| Gossip | Existing `g:<md5>` uses MD5 of exact original text plus mapped speaker race plus gender, not Ukrainian text alone. Other minted forms are `g:b<broadcastTextID>-<voice>` or `g:<lang>-<md5>`, with aliases preserving identity. Spoken matches NPC/object and client text through lookup tables and fuzzy/token handling. |
| Readables | `b:<pageTextID>`; minted `b:n<uuid>` and book `n<uuid>` retain aliases after absorption. `pages`, `books`, `places`, `owners` and title/page/checksum indexes describe identity and structure. ClassicUA item IDs and object names are not pageText IDs. |
| Places | `z:<uiMapID>` and `s:<uiMapID>:<canonicalKey>`. Every language keeps the English canonical key; translated display names never become keys. Audio files use `<map>/zone` or stable subzone slugs with collision handling. |
| Bosses | `boss:<map>:<key>`. Resolve encounter/creature IDs to existing map/key; do not derive identity from a translated NPC name. |

Authoritative algorithms: `pipelines/quests/tts_cli/naming.py`, `tts_utils.py:72`, `apps/web/src/lib/contributions/naming.ts`, `pipelines/readables/tools/lib/naming.mjs`, `addons/Spoken_Readables/Checksum.lua`, `pipelines/places/tools/voice/naming.mjs`, and `pipelines/places/tools/bosses/build-lookup.mjs`.

Readable checksums normalize text then iterate UTF-8 bytes, starting from byte length and multiplying by 31 modulo 2147483647. They are neither ClassicUA hashes nor MD5. Readable matching tries client-language indexes, English/token matches, owner IDs, then guarded title/word overlap. Title and page number alone are insufficient. Forever may omit pages from an otherwise familiar chain; retain page IDs and validate the actual chain.

Quest pack text-keyed tables may use `LookupLocale = "enUS"` while audio language is `ukUA`; `ClientLocaleLookups` can provide actual client matching tables. Do not place Ukrainian strings in English matching tables. Gossip translation needs a crosswalk to the original Spoken moment and its speaker voice. Existing canonical IDs must not be reminted just because the Ukrainian text differs.

## ClassicUA loading and overrides

The pinned [ClassicUA_Camelot.toc](https://github.com/greenya/ClassicUA/blob/1770d208ad853d23d61105cf510d53804770d916/ClassicUA_Camelot.toc) targets Interface `16001` and loads:

1. UI slider template.
2. `entries/index.xml`: class, info, item suffix, language, misc, race, statistics, zone.
3. `entries/classic/index.xml`.
4. `entries/sod/index.xml`.
5. `entries/forever/index.xml`.
6. `scripts/index.xml` and runtime preparation.

Within each of the three content layers, the relevant order is gossip, item, item set, item text, NPC, object, object text, quest Alliance, quest Both, quest Horde, interspersed with the other XML-listed categories. Parse XML order, ignoring commented script tags; do not use filesystem sorting or expansion names as precedence rules.

Quests, item texts and NPC entries merge by top-level key: a later row replaces the earlier row entirely. A missing field or nil inside the later row does not fall back field by field. Object text similarly replaces an entire name entry. Gossip merges one level deeper: later NPC/common tables overwrite their individual hash keys. Its nested `!code` table is a value at that level and is replaced wholesale when supplied, not recursively merged.

Classic's hand-kept `object.lua` initializes the name-keyed table; later object layers assign their keys. `entries/zone.lua` supplies the common English-name-to-Ukrainian-name dictionary. The content-layer XMLs do not load a separate zone dictionary.

`scripts/entries.lua` prepares only the player's faction table, drops the opposite faction, and optionally removes AI-marked quests. Lookup prefers the faction row over `quest_both` for the same ID. An adapter should retain both faction views and record conflicts rather than merging them into a single global row. For a shared output, require identical resolved dialogue or split by the target's real faction rules; never assume the source filename alone establishes eligibility.

The Forever `item_text.lua` and `object_text.lua` contain empty tables. Their merge loops erase nothing. Classic and SoD readable entries remain usable candidates. Forever gossip is small but not empty: one NPC table and common entries are present. Ignoring inherited data would lose most coverage.

## Source shapes and inventory

Quest rows are sparse positional arrays: `[1]` title, `[2]` description, `[3]` objective summary, `[4]` progress, `[5]` completion. Named fields include `en`, `tasks`, and `ai`. Map description to Spoken `accept`, progress to `progress`, completion to `complete`. Do not voice the objective summary instead of description. Title and task translations are metadata/UI candidates, not additional dialogue events. Preserve nil slots; Lua array length is not a reliable way to enumerate these five fields.

Inventory below counts source row declarations before overrides, not unique effective entries, complete dialogue coverage, or verified Forever content:

| File family | Classic rows | SoD rows | Forever rows |
| --- | ---: | ---: | ---: |
| quest_alliance | 937 | 205 | 557 |
| quest_horde | 976 | 162 | 455 |
| quest_both | 2362 | 569 | 616 |
| item_text item IDs | 262 | 27 | 0 |
| object_text top-level names | 9 | 7 | 0 |
| gossip NPC table declarations | 9 | 6 | 1 |

Counts were obtained from line-anchored declarations in the inspected sources. Gossip also has `!common` and `!code`; counts do not measure greetings supported by Spoken, and readable names can contain multiple namesakes. A later adapter must emit parsed effective counts, missing fields, duplicate IDs, overwritten entries, mapped pages/moments, and exclusions with a declared denominator. No supported percentage can be inferred from these raw totals.

Forever quest declarations marked `ai=true`: Alliance 533/557, Horde 443/455, Both 612/616. No actual `ai=true` rows were found in the inspected Classic or SoD quest files; the schema comment describes the flag but is not a row. Preserve the flag and require review of the effective row; do not silently restore a human-translated Classic row where ClassicUA actually replaces it with an AI-marked Forever row.

Gossip maps NPC IDs or `!common` to numeric text hashes and optional `!code` fallback maps. It includes selectable menu options as well as page text. Spoken Gossip narrates greetings/pages; do not equate every option with a narratable line. The English comments help investigate matches but are not an authoritative canonical identity source. ClassicUA `get_text_hash` normalizes NBSP/repeated spaces, trims, lowercases and applies its custom numeric string hash. `get_text_code` uses word endpoints and prefix matching for stored codes of length 42. Neither can be copied into Spoken's MD5 field.

Item texts map item ID to ordered translated pages. Object texts map English object name to pages, or namesake variants with `h1`, a ClassicUA hash of the first English page. A readable crosswalk needs item/object owners, page chains and original page fingerprints from pinned, authorized public reference data. Resolve an `h1` only with the ClassicUA algorithm. Reject ambiguous names; do not invent a page ID from item ID, page number, or title.

NPC data maps creature ID to name, optional title, English `en`, and optional `feminine`/`feminine_tag`. It can guide speaker terminology but contains no voice assignment. Object and zone dictionaries are primarily English-name keyed and require disambiguation against target IDs. `docs/terms/ClassicUA.tbx` is a terminology reference candidate with the same unresolved permission boundary.

## Grammar and review policy

ClassicUA expands its own brace templates in `scripts/entries.lua`: name/race/class with grammatical cases and capitalization, and player-sex branches. Case forms can depend on player settings and the race/class tables loaded earlier. There are also numeric captures such as `{1}`, optional-text and chat-specific template processing. Spoken's `$N`, `$C`, `$R`, `$B` and `$g...:...;` support is not equivalent to that grammar.

Proposed adapter policy:

* Classify tokens with a parser; retain source location and original source hash. Reject unknown or nested unsupported forms rather than stripping braces.
* Separate display templates from future recording text. A recording must not bake in a tester's name, class or grammatical gender.
* Convert only demonstrated equivalent forms. Name cases and Ukrainian class/race inflection need a reviewed rendering strategy; generic English token substitution is insufficient. A player-sex branch may map to a supported Spoken branch only after module-specific tests prove rendering and matching.
* Track AI marking, missing/nil dialogue fields, source variants, namesakes, unresolved tokens, markup, English residue, capitalization and punctuation as review findings. Review inherited SoD rows for actual Forever applicability.
* Test coexistence with ClassicUA enabled and disabled. ClassicUA changes the displayed text; event order and UI hooks may affect the strings Spoken reads. Do not assume normal English matching survives those hooks.

## Independent builds and tools

Native Community Pack files can be emitted offline for Quests/Gossip, Readables and Places without the private Spoken production database. This means implementing a small serializer and validator against the public contracts, with pinned reference inputs; it does not mean every source row maps or every module displays Ukrainian without audio.

The official quest `build` reads the committed corpus and local audio and can operate without Postgres. Its release wrappers also sync/pull/check production state and must not be used for this project. Readables' official lookup builder reads the database; Places' lookup builder loads live takes/current lore through its store. Their release and sound-assembly wrappers are not general community authoring tools. `scripts/readables/package-audio.sh` requires MP3s and official publisher metadata. `scripts/spoken/package.sh` packages the player and must not be used to build Ukrainian packs.

Reuse narrowly scoped pure naming, quoting, normalization and archive-validation logic, with MIT notices when copied and parity tests pinned to the upstream revision. Do not run store/sync/export/release commands, modify upstream generated Lua, or populate a local corpus through production APIs. Reference snapshots are immutable build inputs; unresolved crosswalk decisions are a small reviewed manifest, not another editable translation database.
