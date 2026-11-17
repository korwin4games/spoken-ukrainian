# Near-term priority: Places → Readables → Bosses → Compendium UI → Quests

**Decision: 2026-11-16.** The user prioritizes **Places**, **Books and Notes**, **Bosses**, then **Azeroth's Compendium interface strings** (titles, tabs, buttons, filters, search, messages). **Quests/Gossip** remain after those stages. Compendium content from Places/Readables/Bosses can be translated earlier; only the shared window *chrome* is postponed. This changes execution order only: no new official module, no new language-client claim, no source pin changes, no audio, no release authorization.

## Scope and exact ordering

| Priority | User-facing scope | Upstream ownership | First output |
| --- | --- | --- | --- |
| **P0** | **Places** | `Spoken_Places` zone/subzone lore and its Compendium view | Verify English lore originals; audit UA VoiceOver translations; pilot a cleared text-only Places pack |
| **P1** | **Books and Notes** | `Spoken_Readables` books, letters, notes, plaques and Compendium Readables tab | Verify complete page/owner chains; audit ClassicUA and UA VoiceOver content; pilot reviewed Ukrainian page translations |
| **P2** | **Bosses** | `Spoken_Bosses` boss lore and Compendium boss pages | Verify source stories, translations/rights and supported story-language selection |
| **P3** | **Compendium interface** | Shared core `Spoken` UI (`addons/Spoken/UI/Compendium.lua`) with core/module locales | Translate reviewed UI labels/tabs/buttons/filters/search/messages after content priorities; get an upstream-supported UI-language selection route |
| **P4** | **Quests and Gossip** | `Spoken_Quests` | Preserve Stage 3/4B/4C and local Quest Review UI; tackle after content and Compendium chrome |

**Compendium is NOT a fifth Community Pack**. It is a shared window showing material supplied by the four existing official modules. Two different jobs must be separated: translating the **Compendium chrome** (labels, buttons and controls), and translating **content displayed in Compendium** (Places/Readables/Bosses, later Quests). The four approved module targets remain `Spoken_Quests` (including Gossip), `Spoken_Places`, `Spoken_Readables` and `Spoken_Bosses`.

## Verified pinned baseline and hard limits

The pinned Spoken revision is `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`. Counts from [Stage 4A](STAGE_4A_INVENTORY_COVERAGE.md) describe **canonical identities**, never translation coverage.

**Compendium:** The shared UI uses the official core's locale strings. The pinned `addons/Spoken/Locale/frFR.lua`, for example, is gated by `GetLocale() == "frFR"`. Ukrainian `ukUA` is a **Spoken content language**, not an actual Blizzard client locale. The current Community Pack contract cannot be claimed to translate the UI chrome on an `enUS` client by itself. Investigate whether upstream offers a safe, explicit UI-language preference; if not, document/request one. Do not spoof `GetLocale()` or patch Player internals.

**Places:** **947** canonical IDs; **0** currently indexed as verified original English text by our Stage 4A tool, even though pinned public English `addons/Spoken_Places/Data/enUS/Zones.lua` and `Subzones.lua` source files exist. This is a **missing extractor/verification step**, not proof there are no English stories. Stage 1 already tested an original Ukrainian diagnostic text-only Places pack in Forever. Selected-language Places lore currently has **no per-record English fallback**; a partial Ukrainian set can hide English stories if published without a safe policy. Keep provenance, authorship and source licence/attribution review separate.

**Books and Notes = Readables:** **1,160** canonical page IDs, **1,138** currently with a uniquely verified original English record and **22** without one. The pinned Readables Compendium uses client/English page/title text even where non-client `ukUA` pack text can be looked up. A text-only pack entry may falsely advertise audio and fail on missing `file`. Do not release text-only Ukrainian Readables before an upstream-supported page/text-language and audio-safety contract is verified. Preserve page order, owners, titles, source and canonical `b:<pageID>` identities.

**Bosses:** **297** canonical IDs, **0** included in the current Stage 4A original-English text index. The pinned upstream has original boss story data, but it needs independent canonical reconciliation and provenance/rights review. The Compendium story renderer is selected by client language on `enUS`; simply installing Ukrainian pack text is not proof it displays in Ukrainian. ClassicUA NPC names are not original authored boss stories.

**Quests/Gossip:** Existing Stage 3 reviewed-join requirements, Stage 4B workbench and Stage 4C synthetic bridge remain in the repository; the local Quest Review UI and its private approval ledger were merged into `main` via PR #14. They remain supporting workflows, not the immediate Places/Readables/Bosses translation critical path. No real approvals are implied.

See [Stage 2B tests](STAGE_2B_COMPATIBILITY.md), [approved module scope](APPROVED_MODULES_AND_FALLBACK.md), and [upstream requirements](UPSTREAM_REQUIREMENTS.md).

## Next implementation milestones

1. **Places (P0 — start now).** Confirm that ClassicUA's \`entries/zone.lua\` is a *name glossary*, not lore. Audit [UA VoiceOver: Books & Lore](PLACES_SOURCE_AUDIT.md) as a potentially **far more complete existing Ukrainian lore source**, while keeping its claimed ~900 stories distinct from actual audited canonical matches. Verify each source's rights and source/story identity, then add a read-only pinned English \`Zones.lua\`/\`Subzones.lua\` original index. Test a small rights-cleared text-only Ukrainian Places pack, especially untranslated-entry English fallback. **Acceptance:** an independently reviewed and genuinely supported first Places slice in Forever, without copied unreviewed third-party text.
2. **Readables (P1).** ClassicUA already provides translated item and object page texts, while UA VoiceOver claims 1000+ voiced translated pages. Inspect the actual sources, use stable page ID/owner/page-chain evidence, and avoid merging different versions of a document. Resolve missing-file audio safety and independent Compendium text language with upstream. **Acceptance:** a reviewed multi-page Ukrainian book or note displayed safely under supported UI contracts.
3. **Bosses (P2).** Independently verify pinned boss-story originals and authorship, obtain or prepare cleared Ukrainian stories, validate canonical map/key identity, and resolve the pinned client's selected-language story rendering with upstream. **Acceptance:** one reviewed Ukrainian boss story actually displayed on the normal client with a safe English/silence path.
4. **Compendium *interface chrome* (P3).** Inventory stable localized UI keys and prepare Ukrainian titles, tabs, buttons, filters, search and messages; preserve placeholders. Confirm general-purpose upstream opt-in UI language selection for an ordinary English-client account or explicitly document its unavailability. **Acceptance:** an independently reviewed catalogue and, once supported, visibly Ukrainian controls; do not misrepresent \`ukUA\` content packs as changing client-locale UI.
5. **Quests/Gossip (P4).** Resume already-developed Stage 3 mapping, Stage 4B reviewers and Stage 4C candidate binding. PR #14 is already merged into `main`; preserve its existing review, candidate-retention and explicit inert import gates without making them prerequisites for Places/Readables/Bosses.

## Non-goals and safeguards

- Preserve the unchanged official Spoken Player and the exactly **four** approved module targets; do not invent a fifth Compendium pack.
- Do **not** change `config/translation_sources.json`. **Content-feature priority** differs from the existing **translation-provider priority** (`classicua → another → own_translator → original_english`). The two optional providers remain a stub and a mock respectively.
- Original texts are not automatically approved translations, and matching ID alone is not approved mapping. Keep human quality/provenance/rights checks and no fake audio, locale spoof or public release.
- No bulk copied upstream story/text content in tracked manifests. Build verified offline indexes and review decisions first; any distributable translation content needs a separately cleared scoped implementation.

This document is a product-roadmap update, not a translation pack, capability patch or release.
