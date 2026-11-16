---
name: spoken-runtime-contracts
description: Investigate and test Spoken's ukUA Community Pack registration, Quests/Gossip captions, Readables text-only behavior, Places lore, Bosses stories, client-locale gates, audio availability and fallback.
---

# Spoken runtime contract workflow

## Evidence first
1. Read `docs/COMPATIBILITY_MATRIX.md`, `docs/SOURCE_INTEGRATION.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/STAGE_1_TESTING.md` and applicable upstream module docs.
2. Verify the Spoken revision in `sources.lock.json`. Inspect actual pinned public Lua functions and the current upstream Community Packs guide; do not infer behavior from another language's client locale.
3. Distinguish client game-window text, narrator captions, Compendium entries, lore pages and audio playback.

## Known baseline to characterize, not assume fixed
- A Places community pack can register original `ukUA` lore text without audio using `X-SpokenPlaces-Language`, `X-SpokenPlaces-Lore` and `RegisterLoreData`; selecting Text Language and validating glyphs are separate.
- Quest/Gossip playback resolves sounds, and caption selection has client-language restrictions. A translated game dialog from ClassicUA is not equivalent to translated Spoken captions.
- Readables `pages` entries without a file can falsely mark audio as available or break playback; Compendium text generally follows client-language selection.
- Bosses can have text-only core stories, but pack story selection for a non-client language on `enUS` has a locale gate; Bosses community distribution is not listed in the Manager's currently documented sections.
- `ukUA` is non-client; never spoof `GetLocale()`, monkey-patch the player, create fake/silent sound entries or change canonical IDs.

## Tests and recommendations
1. Build synthetic Lua fixtures using actual pinned code wherever feasible; mock only required WoW APIs. Keep `GetLocale() == "enUS"`.
2. Test voice vs text settings, absent/audio-present cases, disabled packs, English fallback, load order and no unexpected global writes.
3. Label baseline failing-capability characterizations honestly. Do not report them as a feature now working.
4. Propose the smallest upstream-compatible public extension only after reproducing a gap; avoid editing Spoken in this repository.
5. Provide manual Forever test steps when the full game client is unavailable. Never claim in-game verification from a stub.

## Output
Give a module matrix: source revision, exact surface, observed support, test evidence, blocker and potential upstream fix. Note permission and audio-generation gates independently.
