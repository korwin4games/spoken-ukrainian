# Spoken 3.10.1 text-pack integration (DRAFT)

**Scope:** issue #38 / PR #39. Text-only Ukrainian packs are separate from voice packs and retain private, local-testing restrictions.

## Verified upstream API and current pin

The official upstream tag `spoken/v3.10.1` resolves to commit `db5669b0a39815dd38568f0e871f4ced82bc9229`. In the published upstream source:

- `docs/contributors/TEXT-PACKS.md` specifies `X-Spoken-Text: ukUA`, `X-Spoken-TextFormat: 1`, and `Spoken:RegisterText("ukUA", "quests", { titles = ..., lines = ... })`.
- `addons/Spoken_Quests/UI/QuestsTab.lua` uses `Spoken:TextIn` and `DataModules:TextPackText`.
- The Text Language setting must be **Ukrainian** followed by a reload. The English game-client locale must not be spoofed.

**Not yet complete:** `sources.lock.json` and Stage 3/4 snapshots still pin 3.9.0. The exporter currently works from the old audited corpus, so a new 3.10.1 runtime may have a different canonical ID, revised English wording or new quests. Do **not** claim complete live coverage or merge this PR before validating and migrating all source pins, SHA-256 fingerprints, canonical mappings, tests and review decisions.

## Intended independent addons

- `Spoken_Ukrainian`: shared helper. Calls public `Spoken:RegisterText` only when present.
- `Spoken_Quest_UA`: Quest text-only addon, canonical `quests.titles[questID]` and `quests.lines["q:id:stage"]`; preserves native QuestFrame, QuestJournal and Shift behavior.
- `Spoken_Gossip_UA`: independent NPC-frame localization and optional canonical `quests.lines["g:..."]` text, using Spoken line IDs rather than ClassicUA NPC/hash keys.

No addon fabricates audio, sound lengths or human approval.

For Compendium, a line omitted for unsupported grammatical cases or ambiguous canonical mappings must fall back to upstream words. Direct QuestFrame translations may still include local declined placeholders; that does not mean they can safely be exported as Spoken Text Pack placeholders.

## Safe test plan (not yet executed in game)

1. Back up the existing `Interface/AddOns` and addon settings. Do not replace official Spoken using a local Ukrainian ZIP.
2. Verify official Spoken and Spoken_Quests version 3.10.1 or an audited compatible commit; ensure the Ukrainian Quest and Gossip modules can be independently enabled/disabled.
3. Prepare clean ClassicUA and Spoken source checkouts at **the revisions expected by `sources.lock.json`**; do not point the old pipeline at 3.10.1 until the migration is complete.
4. Build each private ZIP:

   ```bash
   uv run --locked python tools/build_ukrainian.py --module Spoken_Quest_UA --classicua ../ClassicUA --spoken ../spoken-wow
   uv run --locked python tools/build_ukrainian.py --module Spoken_Gossip_UA --classicua ../ClassicUA --spoken ../spoken-wow
   ```

5. Install one module at a time using the reviewed installer. In Spoken settings, set **Language → Text Language → Ukrainian**, then `/reload`. If Ukrainian is absent from the selector, inspect add-on enablement, format metadata, load-order failures and Cyrillic font coverage.
6. Check Compendium Quest list titles and accept/progress/complete pages against exact canonical IDs. Missing/unsupported words must fall back to English; no fake audio Play controls.
7. Check NPC QuestFrame/Journal and gossip panes with and without the other Ukrainian module, with and without ClassicUA. Verify Shift, `$N`, `$C`, `$R`, `$B`, `$G`, and `і, ї, є, ґ, І, Ї, Є, Ґ`.
8. Verify that a single `g:...` ID reused by NPCs with conflicting Ukrainian translations is excluded, not silently overwritten.
9. Verify ZIP SHA-256, safe rollback, import statistics, and no change to approvals or source provenance.

**No user-reported in-game verification yet.** These instructions describe future manual testing, not successful tests.

## Remaining blockers

- Re-pin Spoken 3.10.1 after full source audit, update historical fixtures/baselines without losing decisions.
- Confirm the official text pack discovery/load order for the Quest addon with real add-on dependency constraints.
- Confirm independent Gossip Cyrillic font coverage.
- Test in WoW: Forever and verify fallback for mixed-language voice/text subtitles.
- Update bilingual install/CLI guides when implementation and actual commands are finalized.

Reference: https://github.com/rusty-key/spoken-wow/blob/spoken/v3.10.1/docs/contributors/TEXT-PACKS.md
