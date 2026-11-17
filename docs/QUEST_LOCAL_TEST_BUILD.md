# Spoken Ukrainian — local Quest test build (WoW Forever)

**Status: local test only, not released.** Builds two independently installable
addon folders from the `spoken-ukrainian` project while **automatically running
ClassicUA 1:1 Quest auto-import on EVERY build**. Never modifies upstream
Spoken Player / `Spoken_Quests`, game files, native quest windows, or `GetLocale()`.

## Names and packaging

| AddOn folder (must match TOC) | WoW AddOns title | Purpose |
| --- | --- | --- |
| `Spoken_Ukrainian` | **Spoken Ukrainian** | Core namespace and opt-in preview command. Depends on official `Spoken`. |
| `Spoken_Quests_UA` | **Spoken Ukrainian: Quests** | Official `Spoken_Quests` **data-module** format v1, language `ukUA`, plus local opt-in standalone Quest preview. Depends on official `Spoken_Quests` and our `Spoken_Ukrainian`. |
| `Spoken_Quests` | Official Spoken Quests | **Unmodified external dependency**, not bundled. Also owns Gossip, which is not translated by the Quest-only importer. |
| `SpokenCommunity_ukrainian-diagnostic` | Existing Places diagnostic | Separate existing addon, preserved unchanged; not part of this ZIP. |

`Spoken_Quests_UA` is **LoadOnDemand**, is discovered by
`## X-SpokenQuests-DataModule-Version: 1` and
`## X-SpokenQuests-Language: ukUA`, and registers through
`VoiceOver.DataModules:Register`. It has
`SoundLengthLookupByFileName = {}` intentionally: no silent MP3 files,
fake sound durations, recording playback or unsupported Spoken
`textOnly` spoofing.

## AI-marked ClassicUA Quest translations

The optional provider setting `allow_ai_transations` (**literal spelling**,
for compatibility with the requested config key) is **false by default**
if omitted. The project's current `config/translation_sources.json` has:

```json
{
  "name": "classicua",
  "save_translations": true,
  "auto_approve_one_to_one": true,
  "allow_ai_transations": true
}
```

On every build, the mandatory `auto_import_one_to_one` action reads that
policy. With `true`, AI-marked ClassicUA Quest fields can enter **only**
the private **machine-provisional** import store after all unchanged
source/target 1:1 uniqueness, faction, context and SHA-256 checks. With
`false`, the next import removes those AI entries from its *current
imports* (without erasing historical ledger versions), and the new
test ZIP excludes them. No flag changes the independent human Stage 3
mapping approvals, source rights, actual Spoken audio/caption availability,
or publishing restrictions.

For example Quest **97279** (`Wayward Weapons`) is marked `ai=true` in
the pinned ClassicUA Forever Horde source, so it was previously excluded
by the AI setting. Enabling the setting removes **that exclusion only**:
it will not invent a Spoken corpus voice-line target if none exists or
overrule ambiguous cross-faction or speaker variants. Confirm the
actual generated `Translations.lua` contains `[97279]` and the
required `accept` / `progress` / `complete` event before assuming a
specific in-game Quest dialog can be previewed.

## Build steps

From the project repository with Python 3.12+ and Git installed:

```sh
cd /path/to/spoken-ukrainian
python3 tools/build_ukrainian.py \
  --classicua ../ClassicUA \
  --spoken ../spoken-wow
```

The two paths must be **clean local Git checkout roots** with HEAD at the exact
revisions recorded in `sources.lock.json`. These names are examples only.
The command performs, **in this order**:

1. Verify source folders are real Git checkouts. Audit the exact pinned
   ClassicUA and Spoken revisions, original English/Quest IDs and source
   policy; any mismatch **fails the build**.
2. **Automatically call** the existing
   `translation_action("auto_import_one_to_one", {"source": "classicua"})`
   (same as Review UI/CLI). Import source texts into private ignored
   `build/machine-one-to-one.json` and/or `build/translation-reviews.json`,
   preserving revision history and separate human mapping approvals.
3. Re-read validated *current* import references. Keep only actual Quest
   `accept`, `progress`, `complete` records; never count English,
   Gossip, Places, Readables or Bosses as imported quests.
4. For in-game matching via public `GetQuestID()`, group by Quest ID and
   event. If multiple voice/wording variants disagree, **skip** the whole
   ambiguous moment: never display the wrong speaker's text. With no
   remaining moments, the build **fails** (does not quietly create an empty
   ZIP).
5. Generate `Spoken_Quests_UA/Translations.lua` **only inside the
   ignored output ZIP**; source text is never committed. Write a
   deterministic ZIP with two addon folders, safe file names and SHA-256
   sidecar. Archive output is atomic on success.

Output (local only):

```text
dist/
  Spoken_Ukrainian_Quest_Local_Test.zip
  Spoken_Ukrainian_Quest_Local_Test.zip.sha256
```

The console prints full-Spoken inventory totals, imported Quest records,
machine-only vs human-reviewed imports, and **previewable Quest moments**.
Those numbers differ: a provisional pair might share a voice/wording
variant whose moment must be skipped in the preview.

### Important: what this build can and cannot prove

The baseline `Spoken_Quests` v3.9.0 `DataModules:PrepareSound` / 
`ResolveSoundFile` requires a real clip duration from
`SoundLengthLookupByFileName` to enqueue a line; with no Ukrainian MP3s it
does **not** enable native Spoken Ukrainian narrator captions.
The importer's local build therefore provides an opt-in, **separate**
`Spoken Ukrainian — Quest preview (TEST)` frame using only public WoW
quest events and `GetQuestID`. It does not replace normal quest dialogs,
Spoken's captions, the Compendium or audio.

Machine 1:1 translations remain **provisional**, with a visible label
in the preview. This package is for a **local user testing the mapping**,
not a release, redistribution, public CI artifact or an alternative to
human-reviewed publishing checks.

## Install and test in the real game

1. Quit WoW Forever completely. Keep a backup of your
   `Interface/AddOns` folder. Leave official **`Spoken`** and
   **`Spoken_Quests`** installed and enabled. Install neither fake
   audio nor a modified official addon.
2. Extract the test ZIP so the layout is exactly:

   ```text
   World of Warcraft/_forever_/Interface/AddOns/
     Spoken/                       (official, unchanged)
     Spoken_Quests/                (official, unchanged)
     Spoken_Ukrainian/
       Spoken_Ukrainian.toc
       Core.lua
     Spoken_Quests_UA/
       Spoken_Quests_UA.toc
       Translations.lua
       Module.lua
   ```

   **No extra nesting** such as `AddOns/Spoken_Ukrainian_Quest_Local_Test/Spoken_Ukrainian/`.
   The test ZIP contains only the last two folders.
3. On character selection → **AddOns**, check the title
   **Spoken Ukrainian** and the pack
   **Spoken Ukrainian: Quests**. Both must be enabled (note
   `Spoken_Quests_UA` is **LoadOnDemand**). Unrelated older diagnostics
   can be disabled for isolation.
4. Log in; type `/spokenuk status` and then
   **`/spokenuk preview on`**. (The preview defaults **OFF** on login.)
   A `Spoken_Quests` module-list entry should identify the Ukrainian
   pack; it is correctly audio-silent.
5. Select an **imported, previewable Quest ID** from the generated
   `dist` build output or inspect the **local** generated
   `Spoken_Quests_UA/Translations.lua` in the installed test ZIP.
   Visit its NPC. Check **accept**, **progress**, and **complete**
   separately *as available*. The preview panel should show the
   Ukrainian text, matching Quest ID + event, with
   **machine 1:1 (provisional)** or **human-reviewed** label.
6. Check an **untranslated or ambiguous** quest: no Ukrainian
   test preview should appear. Verify original WoW/ClassicUA quest
   window and Spoken captions/audio are unchanged. Test once with
   ClassicUA enabled and once without it; only native quest frames
   should depend on ClassicUA.
7. Type `/spokenuk preview off`. The test panel closes and stops
   reacting; no text injection or patched Blizzard frames remain.
   Try `/reload`, repeat. Disable or remove the two Ukrainian addon
   folders and verify the original Spoken behavior returns.
8. Record quest ID, event, screenshot, whether the preview showed the
   expected Ukrainian text, addons' load/error status and real
   `GetLocale()`. **Manual user confirmation is necessary** to claim
   acceptance in WoW Forever; automated Lua tests cannot launch the game.

## Known limitations and next gate

- The preview **is not** a substitute for original Spoken subtitles.
  Producing normal no-audio Ukrainian subtitles requires an official,
  supported public upstream text-only API; do not monkey-patch the
  player or claim this gate is passed.
- Quest ID cannot always be read from the game at event time, especially
  with other quest UI replacements. The test preview then remains silent,
  rather than guessing using NPC title/fuzzy text.
- Two different translations for one QuestID + event remain ambiguous
  and are omitted rather than selecting an arbitrary voice variant.
- Gossip is **not** included. Places, Readables, Bosses and Compendium UI
  are separate workstreams.
- Do not publish or upload the `dist/` ZIP or any generated corpus
  without independently reviewed mapping/content and authorized release
  approval. The historical diagnostic ZIP remains unchanged.
