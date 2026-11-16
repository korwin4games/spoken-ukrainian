# Approved product scope — four modules and English fallback

**Decision accepted: 2026-11-16. Status: product requirements, not a claim of current runtime support or release readiness.** Applies to the Ukrainian content planned for the **unchanged** official Spoken Player on WoW Forever with a real `GetLocale() == "enUS"`.

This decision supplements [the immutable-Player architecture](ARCHITECTURE_UNMODIFIED_SPOKEN.md), [Stage 2B compatibility](STAGE_2B_COMPATIBILITY.md) and [Stage 3 mapping implementation](STAGE_3_IMPLEMENTATION.md). Historical Stage 0 and characterization documents remain evidence of what was known/tested at the time.

## Exactly four official module targets

The **original Spoken core** (`Spoken`) remains an external installed prerequisite, not a fifth Ukrainian content module and not a fork. Ukrainian distribution is planned as up to **four independently installable Community Packs**, each requiring its corresponding official module:

| Approved module target | Planned Ukrainian content | Relationship |
| --- | --- | --- |
| `Spoken_Quests` | Quest offer/progress/completion and **Gossip** NPC conversations | **One module.** Gossip is a content category under Quests, not a fifth addon/module. |
| `Spoken_Places` | Zone and subzone lore | Old product name **Spoken Zones** maps to current Places. |
| `Spoken_Readables` | Books, letters, notes and plaques | Old product name **Spoken Books** maps to current Readables. |
| `Spoken_Bosses` | Dungeon and raid boss stories | Separate official module, subject to story rights and runtime selection support. |

These are **module targets**, not an instruction to duplicate, rename, overwrite or redistribute the official module code. Packaging names, content splitting, optional per-faction audio archives and release versions will be decided and validated in later stages; none are authorized here. A missing/disabled Ukrainian pack must not disable other official modules or Ukrainian packs.

## Approved missing-translation and audio policy

1. **Text goal:** when an *approved* Ukrainian translation exists **and its canonical mapping and current display contract are valid**, show Ukrainian for the applicable surface. Otherwise preserve the available **original English** text, not blank text, invented text, a missing-file error, or the wrong translation. This is a **per-record product requirement**. It must not be declared implemented for a module until tested on that surface.
2. **Audio goal (independent setting):** use genuine authorized Ukrainian narration when available; if absent, use genuine English narration **only** when installed and permitted by the user's **If a Voice Is Missing** choice. Under **Stay Silent** or absent English audio, do not play an unavailable clip. Text must remain accessible where the official module supports text without sound.
3. **Narrator/subtitles are independent of native frames.** Native Blizzard quest, Gossip and readable windows remain owned by the client (or optionally ClassicUA). Ukrainian native text from ClassicUA does **not** automatically translate Spoken's narrator captions, Compendium, tooltip, map label, or other Spoken-controlled surfaces.
4. **No unsupported fallback workaround:** never spoof `GetLocale()`, treat `ukUA` as `enUS`, monkey-patch Spoken, manufacture silent/dummy MP3 filenames/durations, or invent canonical IDs to force a text/audio path.
5. **Missing ClassicUA translation:** process each missing indexed Spoken record through the explicitly ordered offline [translation source chain](TRANSLATION_SOURCE_CHAIN.md): `classicua`, independently cleared alternative (`another`, currently stub), own translation (`own_translator`, currently **mock**), and optionally explicit `original_english`. Any source may be reordered or removed. The next source sees **only records without a candidate** from previous sources. The mock never marks a record translated. Empty `sources: []` or `{}` selects the actual client language and performs no provider calls. Candidate discovery never approves content or canonical identities. Without approved Ukrainian content, preserve original English/client content on supported surfaces; the existing Spoken limitations remain. ClassicUA zone/NPC terminology is not authored Places/Bosses lore.

## Verified pinned-baseline limitations and release gates

| Official module | What the current pinned player already supports | Gap to approved per-record fallback goal |
| --- | --- | --- |
| Quests (+ Gossip) | Original native/corpus English remains accessible; recorded audio can use selected voice with configurable English fallback | `enUS` Spoken captions and Compendium do not independently select `ukUA` pack text; text-only UK records cannot queue narration. Need actual public support, proof of safe behavior and game acceptance before claiming Ukrainian display. |
| Places | Independent `ukUA` **text-only lore** works; Stage 1 diagnostic was tested in Forever | **No per-record English lore fallback** inside a selected Ukrainian dataset. Do not publish a partially covered Places text set that silently hides English stories. Require tested safe coverage/fallback behavior or mark affected entries blocked; missing lore must never be marketed as translated. |
| Readables | Native/Compendium English baseline and existing English fallback paths | Audio-free `ukUA` page may falsely advertise audio and throw on missing `file`; on `enUS`, Compendium chooses client/English text. **Do not ship text-only Ukrainian Readables entries** until safe supported contract exists and is tested. |
| Bosses | English core story can be shown without audio where it exists | Ukrainian pack story display is client-language-gated on `enUS`; no ClassicUA-authored boss story source. Require independent story rights, canonical identity and tested display behavior. |

Unresolved display cases are **blocked**, not solved by a mere offline source↔target mapping or by installing ClassicUA. Official upstream API improvements may be evaluated in a separate reviewed/pinned task; our project does not patch Spoken. A standalone helper with its own UI is a separately authorized optional decision, not assumed here.

## Verification and acceptance for later Ukrainian packs

For **each** of the four module targets, test representative cases in a real Forever `enUS` client, separately with ClassicUA off and on:

- Approved Ukrainian text present vs missing; unknown/ambiguous/unreviewed identity; ordinary original English display preserved.
- Ukrainian recording present vs absent; English recording installed vs absent; English fallback vs **Stay Silent**; no fake MP3, exceptions or wrong caption/timing language.
- Native client frame vs Spoken-owned caption vs Compendium vs Places/boss story; record the actual surface and do not conflate them.
- Module/pack enabled, disabled and removed; stale preference; reload, Unicode rendering and return to English.
- Independent install/disable of each Ukrainian pack, including **Gossip under Quests**; no changes to other module behavior.
- Provenance, canonical IDs, actual content permissions and review approval; no automatic approval from a Stage 3 candidate count.

Until independently verified real joins are approved, **Stage 3's 0 real mappings and inventory counts remain the truthful baseline**. This document does not authorize release, VERSION bump, audio generation or new translated content.

## Source nomenclature

The pinned upstream [Spoken README](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/README.md) identifies retired **Spoken Zones** / **Spoken Books** with the modern **Spoken Places** / **Spoken Readables** module naming and identifies Gossip as part of `Spoken_Quests`.
