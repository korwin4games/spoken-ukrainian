# Spoken Ukrainian compatibility matrix

Stage 0 baseline: Spoken `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`; ClassicUA `1770d208ad853d23d61105cf510d53804770d916`. Scope: WoW Forever, Ukrainian content on a real supported client locale, typically `enUS`. No game testing has been performed.

Source paths below are relative to ClassicUA unless prefixed with Spoken. `classic → sod → forever` means actual TOC order, not a union of translations. Coverage is candidate source coverage before overrides and validation. See [source integration](SOURCE_INTEGRATION.md) for the inventory method and exact runtime evidence.

## Quests: Alliance

| Dimension | Finding |
| --- | --- |
| Source | `entries/{classic,sod,forever}/quest_alliance.lua`; corresponding `quest_both.lua` for runtime faction fallback; NPC/object/item terminology as needed |
| Target | `q:<id>:accept/progress/complete`, alternate wordings and player-sex variants; a version-1 Quests data module, quest/speaker lookup tables and eventual filename-duration/text tables |
| Mapping | Resolve each faction table through layer replacement; Alliance row beats shared row at runtime. Map positional fields 2/4/5 to accept/progress/complete. Validate ID, original wording, giver and Forever eligibility. Use Spoken race-mask partitioning rather than source filename alone. |
| Available coverage | 937 Classic, 205 SoD, 557 Forever row declarations; 533 Forever rows AI-marked. Totals overlap and contain incomplete fields. |
| Missing content | Effective per-event completeness and target crosswalk remain unmeasured; alternate wordings and speaker variants may lack translations; no audio supplied. |
| Text-only | Offline preparation yes. Normal Spoken Ukrainian quest captions on an English client: unsupported by the current pack contract, including when Ukrainian audio is selected. ClassicUA may separately translate the game window. |
| Validation | Sparse slots, whole-row replacement, faction/shared collisions, exact ID/source/wording, all player tokens, AI review, lookup locale, both fallback choices and coexistence with ClassicUA |
| Risks | Wrong-field mapping; retaining stale Classic fields erased by a Forever row; inherited SoD content unavailable in Forever; client-language caption gate |

## Quests: Horde

| Dimension | Finding |
| --- | --- |
| Source | `entries/{classic,sod,forever}/quest_horde.lua`, runtime fallback to resolved `quest_both.lua`, plus terminology tables |
| Target | Same quest identity and data-module structures as Alliance, distributed independently as a quests-section community pack |
| Mapping | Resolve Horde view independently. Horde row beats shared row. Use fields 2/4/5 and preserve missing fields and canonical alternate-wording identities. |
| Available coverage | 976 Classic, 162 SoD, 455 Forever declarations; 443 Forever rows AI-marked |
| Missing content | Unmapped IDs, per-event holes, alternate wordings, actual Forever eligibility and all audio |
| Text-only | Offline preparation yes; no supported independent Ukrainian caption display in Spoken on an English client |
| Validation | Same checks as Alliance, with Horde race masks and Horde-specific source precedence |
| Risks | Assuming Alliance/Horde files are disjoint, using a shared row over a faction row, grammar loss, AI quality and display gate |

## Quests: Shared

| Dimension | Finding |
| --- | --- |
| Source | `entries/{classic,sod,forever}/quest_both.lua`, compared with both effective faction tables |
| Target | Shared quest module using canonical `q:` IDs and existing filename conventions |
| Mapping | Layer replacement within `quest_both`; check both faction runtime views before exporting one shared translation. Divergent rows require explicit handling under existing target identity/wording rules, not arbitrary preference. |
| Available coverage | 2362 Classic, 569 SoD, 616 Forever declarations; 612 Forever rows AI-marked |
| Missing content | Verified shared eligibility, three-event completeness, variant alignment and audio |
| Text-only | Same limitation as faction quests |
| Validation | Cross-faction agreement, race-mask partition, IDs shared across languages, nil positions and AI-reviewed status |
| Risks | `both` interpreted as guaranteed identical runtime dialogue; merging source rows field by field; large AI-marked Forever share |

## Gossip

| Dimension | Finding |
| --- | --- |
| Source | `entries/{classic,sod,forever}/gossip.lua`; `scripts/utils.lua` and `scripts/entries.lua` define source matching; NPC terminology |
| Target | Quests data module; `GossipLookupByNPCID/Name` or object equivalents, client-locale text keys, canonical `g:` stems, optional aliases, eventual durations and `TextByFileName` |
| Mapping | Resolve hash entries with the source's one-level merge; preserve `!common`, replace supplied `!code` values as upstream does. Join NPC/object and original page text to pinned Spoken moments, then retain their existing stem. Resolve speaker race/gender/voice explicitly. Filter menu options from greetings/pages. |
| Available coverage | 9/6/1 numeric NPC table declarations across Classic/SoD/Forever, plus common strings and code maps. Raw translated literals: 375/47/5. These are not unique Spoken greeting counts. Forever gossip is not empty. |
| Missing content | A deterministic source-to-Spoken moment crosswalk, voice metadata absent from ClassicUA, unsupported options, unmatched dynamic text and audio |
| Text-only | Offline preparation yes; current queue/caption path has the same audio and client-language restrictions as Quests |
| Validation | Distinct hash algorithms, exact source text, NPC scope, common fallback, code collisions/prefixes, token substitution, aliases, ClassicUA hook order, missing-greeting behavior |
| Risks | Putting ClassicUA's numeric hash into a Spoken MD5 field; hashing Ukrainian text to rename an existing moment; matching options as spoken pages; losing inherited `!code` semantics |

## Readables

| Dimension | Finding |
| --- | --- |
| Source | `entries/{classic,sod,forever}/item_text.lua`, `object_text.lua`; item IDs, object names and namesake `h1`; runtime page lookup in `scripts/entries.lua` |
| Target | `b:<pageTextID>` and persistent minted aliases; format-1 `SpokenReadablesAudioPacks`, `pages[id]`, optional books/places and matching indexes |
| Mapping | Item ID → owner/book → canonical page chain; object name + first-page source fingerprint + owner evidence → chain. Match translated page positions to validated Forever chain; preserve skipped-page evidence. Export target page IDs and separate client recognition indexes from Ukrainian text. |
| Available coverage | Classic: 262 item entries, 697 page-string literals; 9 object names, 24 page-string literals. SoD: 27 item entries, 52 page-string literals; 7 object names, 9 page-string literals. Forever item/object text tables are empty and preserve prior entries. Namesakes and shared pages prevent adding these as unique coverage. |
| Missing content | Owner-to-page crosswalk for each candidate; unique object identity for ambiguous names; actual Forever chain differences; Ukrainian standalone display contract and all audio |
| Text-only | Pack text can be accessed programmatically, but text-only page entries are unsafe: playback expects `entry.file` and audio availability counts the entry itself. Compendium text follows client language. There is no supported Ukrainian audio-free display on an English client at this baseline. With real Ukrainian audio, non-client voice captions can be Ukrainian. |
| Validation | UTF-8 checksum parity, namesake `h1`, owner IDs, chain order and lengths, skipped pages, token pages, sparse/missing text, mail exclusion, ambiguous titles rejected, no false audio availability |
| Risks | Confusing item/object/page IDs; title-only mapping; text-only entries causing missing-file failures; falsely assuming French client indexes select Ukrainian text |

## Places

| Dimension | Finding |
| --- | --- |
| Source | Common `entries/zone.lua` terminology; object/NPC names where relevant. ClassicUA does not supply Spoken's original zone/subzone lore stories. |
| Target | `z:<uiMapID>`, `s:<uiMapID>:<EnglishCanonicalKey>`; `RegisterLoreData("ukUA", "zones"/"subzones", table)` with `name`, `short`, `full` and provenance/source fields; optional format-1 audio registry later |
| Mapping | Join names to pinned map/subzone identities; keep canonical keys. Translate or author lore separately under its own permissions. A terminology hit is not translated story coverage. Emit combined tables per kind. |
| Available coverage | Name dictionary candidates only; zero ClassicUA coverage of Spoken-specific stories established. Spoken's baseline coverage export lists 841 English lore lines; that is a future reference denominator, not a Ukrainian milestone. |
| Missing content | Reviewed Ukrainian lore prose and summaries, ambiguous map-name crosswalks, complete font verification, audio |
| Text-only | Yes for lore pages with Places language/lore metadata and drawable native name. No narrator playback without clips. Displayed map labels can still come from the client through `GetMapName`. |
| Validation | TOC declaration before load, readiness and font checks, explicit text-language selection and reload, stable map/key mapping, separate client aliases, partial coverage behavior, one registration per kind |
| Risks | Treating zone terminology as lore; overclaiming readiness because lore metadata is trusted; loss of script glyphs; replacing whole tables; expecting every game map label to become Ukrainian |

## Bosses

| Dimension | Finding |
| --- | --- |
| Source | Effective `entries/{classic,sod,forever}/npc.lua`, object/zone terminology where relevant. No source of Spoken Bosses' authored stories established. |
| Target | `boss:<map>:<key>` via encounter/creature crosswalk; `SpokenBossesAudioPacks[folder].bosses[map][key]` with optional text and actual audio fields |
| Mapping | Identify encounter and creature IDs against pinned boss metadata, then retain map/key. Use names as terminology only. Translate or author each story separately with provenance. |
| Available coverage | NPC name candidates, including feminine forms; zero ClassicUA coverage of Spoken-specific boss stories established |
| Missing content | Ukrainian stories, validated boss identity crosswalk, independent non-client text selection, audio, Manager Bosses section |
| Text-only | Core boss stories can use text-only narrator clips. Pack story overrides currently follow `GetLocale()` and require a core story, so Ukrainian story display on an English client is not enabled by Ukrainian voice selection. |
| Validation | Encounter/creature/map/key correctness, existing-story requirement, retired bosses, locale selection, no-audio story clips, Forever dungeon availability and names |
| Risks | Name-only joins, assuming audio pack text is an arbitrary-language story registry, attributing Spoken/wiki stories to ClassicUA, no standalone Manager listing |

## Cross-module conclusions

All listed formats can be prepared offline without the private Spoken database, provided the required identity evidence is available. Unknown mappings remain rejected with reasons. That feasibility does not remove runtime display gates or licensing blockers.

The first supported text-only test should use Places and original diagnostic prose. Quest/Gossip, Readables and Bosses Ukrainian text display need demonstrated upstream capability or a separately reviewed upstream extension. No pack should monkey-patch the player to hide those limitations. The target remains the full Ukrainian equivalent across modules; the milestones must expose these dependencies rather than claim early completeness.
