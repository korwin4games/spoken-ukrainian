# Places: source audit and first translation workstream

**Research date:** 2026-11-16. This is the starting point for **P0 Places**, not a corpus import, approved translation, integrated voice pack, or publication authorization.

## Three distinct source roles

| Source | Verified capability | What it does *not* prove |
| --- | --- | --- |
| **Spoken pinned source** | Canonical Places IDs (947 in Stage 4A). Public pinned English lore lives in `addons/Spoken_Places/Data/enUS/Zones.lua` and `Subzones.lua`; the former contains named `short`/`full` stories and `source` provenance URLs. A small original Ukrainian **diagnostic** Places pack already displayed in Forever | An imported/verified English-lore text index, reviewed Ukrainian lore, per-story text fallback or Ukrainian audio |
| **ClassicUA pinned source** | `entries/zone.lua` supplies English→Ukrainian **zone/subzone names** and terminology; `entries/classic/item_text.lua` and `object_text.lua` supply separately translated **book/document pages** | It does **not** provide equivalent full Places `short`/`full` zone histories. Name translations are not lore stories or canonical map-ID joins |
| **UA VoiceOver: Books & Lore** | CurseForge project `1733862`, author **MUSHLYA13**, release **1.1.0**, dated **2026-10-08**, for Forever client **1.60.1**. The publisher describes **~900 Ukrainian voiced zone/subzone stories** and **1000+ translated/voiced book, letter and plaque pages**, with Ukrainian synced subtitles. The listing declares **MIT** licensing and credits ForeverVO code | No independently verified ZIP manifest/source revision, file structure, full story/wording comparisons, matching map/subzone IDs, actual number of canonical Spoken matches, individual audio reuse rights, source translations' rights and notices |

**Source links:**
- Pinned ClassicUA [zone dictionary](https://github.com/greenya/ClassicUA/blob/1770d208ad853d23d61105cf510d53804770d916/entries/zone.lua), [book/item text](https://github.com/greenya/ClassicUA/blob/1770d208ad853d23d61105cf510d53804770d916/entries/classic/item_text.lua) and [object pages](https://github.com/greenya/ClassicUA/blob/1770d208ad853d23d61105cf510d53804770d916/entries/classic/object_text.lua).
- Pinned Spoken [English Zones](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Places/Data/enUS/Zones.lua) and [English Subzones](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/addons/Spoken_Places/Data/enUS/Subzones.lua).
- [UA VoiceOver: Books & Lore on CurseForge](https://www.curseforge.com/wow/addons/ua-voiceover-books-lore), [1.1.0 release](https://www.curseforge.com/wow/addons/ua-voiceover-books-lore/files/9100914).

**Important:** the apparent similarity between ~900 UA VoiceOver stories and 947 Spoken Places IDs is a **research lead, not verified overlap**. The CurseForge descriptions are publisher-provided claims, not audited corpus coverage. We did not inspect the 439 MB ZIP contents or find an independently verified GitHub source repository for that addon as part of this initial audit.

## Reviewable implementation plan (Places first)

1. **Verify actual pinned Spoken English originals.** Build a read-only extractor for `Zones.lua` and `Subzones.lua` using existing pinned blob SHA-256, actual canonical IDs `z:<mapID>` and `s:<mapID>:<slug>`, and exact original story fields `name`/`short`/`full`/`source`. Account for the seed catalogue (`pipelines/places/tools/seed/zones.json`), missing stories, variants and provenance; keep full English bodies in memory, not tracked reports. Do not infer canonical identity from a translated place name.
2. **Audit UA VoiceOver as an *optional* source adapter.** Obtain the legitimate addon archive from the author/official listing into an ignored local input directory, record version and SHA-256, identify actual packaged Ukrainian lore table(s) and source/author credits. Evaluate source and audio provenance/permissions; retain source data locally, never commit raw dumps or binary recordings by default.
3. **Compare candidates by original source identity.** Align actual map ID, parent zone, subzone slug/key, and English source/story paragraph references; compare `short` and `full` separately. Reject ambiguous titles, places with similar names and content that covers different periods/expansions. A candidate is *not* a reviewed translation.
4. **Apply ClassicUA zone dictionary as a terminology glossary**, with attention to inflection and names. Do not use it as a source for full lore text, and do not replace lore with only translated place names.
5. **Independently review Ukrainian stories and rights** (who wrote/transcribed/translated/voiced each story, permitted redistribution, credits, compatibility with English source's CC BY-SA where applicable). The listing's general MIT claim must not silently override third-party content/recording rights.
6. **Pilot a small coherent text-only Places pack.** Existing `SpokenPlaces:RegisterLoreData` can display Ukrainian for a selected dataset, but **does not have an independently verified per-record English fallback**. Test missing/untranslated zones under ordinary client locale, font, reload, disable/remove; block any partial distribution that hides available English without a safe tested policy. Add real audio only after explicit separate authorization and verified pack rights.

## Offline source-priority boundary

The project still uses the configurable providers `classicua`, `another` (stub), `own_translator` (mock), and `original_english`; **feature priority is unrelated to provider order**.

UA VoiceOver is an **unverified candidate for a future rights-cleared `another` adapter**, not an automatic switch-on. Until file/provenance/map-key checks and human review complete, it must produce **zero publishable source mappings, translations or audio**. If no approved Ukrainian story exists for a canonical Place, keep the original English/client content on supported surfaces rather than claiming Ukrainian coverage.

## Immediate acceptance checklist

- [x] Classify exact ClassicUA `zone.lua` content as glossary only.
- [x] Verify that ClassicUA separately has book/item and object page translations.
- [x] Identify official UA VoiceOver listing, approximate publisher-reported coverage, release ID and declared license.
- [ ] Inspect the actual published UA VoiceOver ZIP and verify its file list, story IDs, text bodies and audio rights.
- [ ] Build canonical Places English originals index with pinned references; distinguish `short` and `full`.
- [ ] Produce a metadata-only, **honest** candidate overlap report.
- [ ] Human-reviewed rights/translation pilot and observed safe client display.

This is a **source survey**, not an installation or content publication.
