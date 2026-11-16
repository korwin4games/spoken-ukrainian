# Near-term priority: Compendium → Places → Readables → Bosses

**Decision: 2026-11-16.** The user prioritizes **Ukrainian text** in Azeroth's Compendium, Places, Books and Notes, and Bosses, in that order. Quest/Gossip identity reviews are deferred. This changes execution order only: no new official module, no new language-client claim, no source pin changes, no audio, no release authorization.

## Scope and exact ordering

| Priority | User-facing scope | Upstream ownership | First output |
| --- | --- | --- | --- |
| **P0** | **Azeroth's Compendium** | Shared core `Spoken` UI (`addons/Spoken/UI/Compendium.lua`) with core/module locales | Ukrainian UI-string inventory, reviewed labels/buttons/filters/search/messages, testable upstream language-selection route |
| **P1** | **Places** | `Spoken_Places` zone/subzone lore and its Compendium view | Verified public English-lore intake plus small rights-cleared Ukrainian Places text-only pilot |
| **P2** | **Books and Notes** | `Spoken_Readables` books, letters, notes, plaques and Compendium Readables tab | Verified books/page-order/owners, Ukrainian page pilot, and upstream-safe text-only/browser contract |
| **P3** | **Bosses** | `Spoken_Bosses` boss lore and Compendium boss pages | Verified boss-story originals/rights, Ukrainian story pilot, tested story-text selection |
| **Deferred** | **Quests and Gossip** | `Spoken_Quests` | Preserve Stage 3/4B/4C and local Quest Review UI; do not block first-wave work on these |

**Compendium is NOT a fifth Community Pack**. It is a shared window showing material supplied by the four existing official modules. Two different jobs must be separated: translating the **Compendium chrome** (labels, buttons and controls), and translating **content displayed in Compendium** (Places/Readables/Bosses, later Quests). The four approved module targets remain `Spoken_Quests` (including Gossip), `Spoken_Places`, `Spoken_Readables` and `Spoken_Bosses`.

## Verified pinned baseline and hard limits

The pinned Spoken revision is `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`. Counts from [Stage 4A](STAGE_4A_INVENTORY_COVERAGE.md) describe **canonical identities**, never translation coverage.

**Compendium:** The shared UI uses the official core's locale strings. The pinned `addons/Spoken/Locale/frFR.lua`, for example, is gated by `GetLocale() == "frFR"`. Ukrainian `ukUA` is a **Spoken content language**, not an actual Blizzard client locale. The current Community Pack contract cannot be claimed to translate the UI chrome on an `enUS` client by itself. Investigate whether upstream offers a safe, explicit UI-language preference; if not, document/request one. Do not spoof `GetLocale()` or patch Player internals.

**Places:** **947** canonical IDs; **0** currently indexed as verified original English text by our Stage 4A tool, even though pinned public English `addons/Spoken_Places/Data/enUS/Zones.lua` and `Subzones.lua` source files exist. This is a **missing extractor/verification step**, not proof there are no English stories. Stage 1 already tested an original Ukrainian diagnostic text-only Places pack in Forever. Selected-language Places lore currently has **no per-record English fallback**; a partial Ukrainian set can hide English stories if published without a safe policy. Keep provenance, authorship and source licence/attribution review separate.

**Books and Notes = Readables:** **1,160** canonical page IDs, **1,138** currently with a uniquely verified original English record and **22** without one. The pinned Readables Compendium uses client/English page/title text even where non-client `ukUA` pack text can be looked up. A text-only pack entry may falsely advertise audio and fail on missing `file`. Do not release text-only Ukrainian Readables before an upstream-supported page/text-language and audio-safety contract is verified. Preserve page order, owners, titles, source and canonical `b:<pageID>` identities.

**Bosses:** **297** canonical IDs, **0** included in the current Stage 4A original-English text index. The pinned upstream has original boss story data, but it needs independent canonical reconciliation and provenance/rights review. The Compendium story renderer is selected by client language on `enUS`; simply installing Ukrainian pack text is not proof it displays in Ukrainian. ClassicUA NPC names are not original authored boss stories.

**Quests/Gossip:** Existing Stage 3 reviewed-join requirements, Stage 4B workbench and Stage 4C synthetic bridge remain in the repository; the local Quest Review UI PR can be finished independently, but its review queue is no longer the immediate content-translation critical path.

See [Stage 2B tests](STAGE_2B_COMPATIBILITY.md), [approved module scope](APPROVED_MODULES_AND_FALLBACK.md), and [upstream requirements](UPSTREAM_REQUIREMENTS.md).

## Next implementation milestones

1. **Compendium chrome and capability audit (P0).** Enumerate stable source keys and references from core and module locale files. Prepare Ukrainian UI labels, terminology and format/placeholder tests for independent language review. Confirm a supported non-client UI-language route or file an explicit upstream enhancement. **Acceptance:** reviewed string-key catalogue + truthful runtime feasibility status, not a claim the enUS UI is already Ukrainian.
2. **Places (P1, first realistically deployable text).** Expand the pinned English-original index for real `enUS` Zones/Subzones with hashes and canonical map/subzone IDs; retain source provenance/licence. Translate and review a small, coherently covered group of places. Test the existing Places text-only community contract and safe English behavior for uncovered stories in Forever. **Acceptance:** one real, cleared Ukrainian lore pilot visible in game without fake audio or hidden untranslated entries.
3. **Readables (P2).** Verify book/title/page/owner chains and independently review Ukrainian text. Resolve missing-file audio safety and independent text display with upstream. **Acceptance:** at least one translated multi-page book/note browsable in a supported Compendium with correct language/fallback and no nil-file exception.
4. **Bosses (P3).** Build an independently verifiable canonical boss-story source index with rights/attribution, review Ukrainian lore, and obtain a supported story selection route. **Acceptance:** a cleared boss story shown in Ukrainian on an ordinary client with safe English/silence behavior.
5. **Return to Quest/Gossip mapping**, after priority 0–3 has a clear path; do not discard prior work.

## Non-goals and safeguards

- Preserve the unchanged official Spoken Player and the exactly **four** approved module targets; do not invent a fifth Compendium pack.
- Do **not** change `config/translation_sources.json`. **Content-feature priority** differs from the existing **translation-provider priority** (`classicua → another → own_translator → original_english`). The two optional providers remain a stub and a mock respectively.
- Original texts are not automatically approved translations, and matching ID alone is not approved mapping. Keep human quality/provenance/rights checks and no fake audio, locale spoof or public release.
- No bulk copied upstream story/text content in tracked manifests. Build verified offline indexes and review decisions first; any distributable translation content needs a separately cleared scoped implementation.

This document is a product-roadmap update, not a translation pack, capability patch or release.
