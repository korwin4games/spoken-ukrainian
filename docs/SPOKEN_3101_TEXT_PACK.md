# Spoken 3.10.1 Ukrainian Quest/Gossip text packs (private integration)

Issue #38 / PR #39. Text is independent of any Ukrainian voice pack. **This is a
private local-test build, not a public release.** Actual WoW: Forever client
acceptance remains outstanding.

## Verified upstream source contract

- Active source pin: official \`spoken/v3.10.1\` commit
  \`db5669b0a39815dd38568f0e871f4ced82bc9229\`.
- The Quest/Gossip corpus, aliases and all 13 Stage 3 file blobs are identical
  to Spoken 3.9.0. The active \`sources.lock.json\` file hashes were recomputed
  from the 3.10.1 Git blobs; the legacy Stage 1/2B 3.9.0 contract is preserved
  in \`tests/stage1_legacy_sources.json\`.
- Official text pack protocol: \`Spoken:RegisterText("ukUA", "quests",
  {titles = {...}, lines = {...}})\`, metadata \`X-Spoken-Text: ukUA\` and
  \`X-Spoken-TextFormat: 1\`.
- The upstream \`DataModules:LineIds\` maps \`ID-event[-wN]\` to
  \`q:ID:event[:wN]\`, hashes and \`bID-voice\` stems to \`g:...\`, and tries
  player sex suffixes \`:m\` / \`:f\` before the base ID.
- Spoken Compendium's Quest page renders **accept and complete** text;
  progress belongs to other supported contexts.
- Official contract: [TEXT-PACKS.md](https://github.com/rusty-key/spoken-wow/blob/spoken/v3.10.1/docs/contributors/TEXT-PACKS.md).

## Independent modules and load order

Each separately built ZIP contains \`Spoken_Ukrainian\` and exactly one of:

- \`Spoken_Quest_UA\`: public Quest text pack, existing native QuestFrame,
  Journal, quest-title hooks, and optional local preview. Does **not** register
  a fake voice/data module. Its .toc is always loaded to retain native hooks
  even when Ukrainian is not the chosen Text Language.
- \`Spoken_Gossip_UA\`: public Gossip text pack and existing NPC-specific
  native Gossip frames. Its .toc is always loaded for the same reason.
  Includes a licensed \`NotoSans-Regular.ttf\` and OFL attribution independently
  of the Quest addon; font bytes are reused from the reviewed Quest template.
- \`Spoken_Ukrainian\`: shared helper, depends on official \`Spoken\`.
  Calls \`Spoken:RegisterText\` only if the API exists; older versions retain
  the supported native hooks but cannot display Text Packs in Compendium.

The official Text Packs guide permits always-loaded addons, though
LoadOnDemand is preferred for a text-only addon with no native hooks.
Quest/Gossip here perform both jobs. The dependency chain does not require a
Ukrainian voice pack; \`Spoken_Quests\` remains the independent official provider
of the Quests tab and must be installed for Compendium Quest pages.

## Safety and intentionally omitted lines

- Only unambiguous imported Quest ID/event values are eligible. The
  exporter checks the *entire pinned English wording set* for the moment;
  more than one original blocks the base \`q:ID:event\`. It does not guess
  \`:wN\` or \`:m/:f\` translations without variant-specific proof.
- A shared Gossip \`g:...\` key is exported only when **every** context using
  that key in the complete pinned corpus is within the safe editor scope,
  every distinct NPC/hash selection exists, all verified English originals
  agree, and all translations agree. Gameobject or unsupported contexts,
  missing selections, stale evidence and conflicting translations block it.
  Native NPC/hash-specific Gossip translation still works separately.
- Public Text Pack placeholders use \`$N\`, \`$C\`, \`$R\`, \`$B\`, \`$Gmale:female;\`.
  Local declined grammatical forms that cannot be represented safely are
  omitted from the Text Pack rather than shown literally. This does not
  discard the corresponding native Quest/Gossip translation.
- Quest title candidates originate from current pinned ClassicUA fields.
  A single global title ID is omitted when faction sources disagree.
  Local selections and provisional imports are not human approvals.
- Nothing fakes audio, playback metadata, \`GetLocale()\`, or official addon
  files. Missing Text Pack values use Spoken's existing fallback.

## Building and installing

Use **clean** pinned Git checkouts, not arbitrary default branches:

\`\`\`bash
uv sync --locked
uv run --locked python tools/build_ukrainian.py --module Spoken_Quest_UA --classicua ../ClassicUA --spoken ../spoken-wow
uv run --locked python tools/build_ukrainian.py --module Spoken_Gossip_UA --classicua ../ClassicUA --spoken ../spoken-wow
\`\`\`

Or select the module in the private Translation Manager. \`Створити модуль\`
builds that module; \`Інсталювати\` first rebuilds it, verifies the ZIP
and SHA-256 sidecar, and uses the existing safe backup/rollback installer.

For direct CLI installation, close the game and use the validated installer:

\`\`\`bash
uv run --locked python tools/install_addon.py --addons "/path/to/World of Warcraft/_forever_/Interface/AddOns" --archive dist/Spoken_Quest_UA_Local_Test.zip --dry-run
uv run --locked python tools/install_addon.py --addons "/path/to/World of Warcraft/_forever_/Interface/AddOns" --archive dist/Spoken_Quest_UA_Local_Test.zip
\`\`\`

Substitute \`Spoken_Gossip_UA_Local_Test.zip\` for the independent Gossip pack.
Always back up the existing AddOns and SavedVariables before in-game testing.
The installer backs up replaced Ukrainian folders under
\`Interface/AddOns/.spoken-ukrainian-backups/\` and leaves official Spoken
folders untouched. To roll back manually, fully close WoW, remove only the
newly installed Ukrainian folders, then restore the corresponding named
folders from the latest backup.

## WoW: Forever manual acceptance — NOT EXECUTED

1. Install supported official \`Spoken\` and \`Spoken_Quests\` version 3.10.1.
   Install Quest alone; start WoW. Under Spoken Settings → Language choose
   **Text Language = Ukrainian** and run \`/reload\`. Enable Spoken's
   Developer log to diagnose refused text registration.
2. Verify Ukrainian \`і ї є ґ І Ї Є Ґ\` in the selector, Quest titles and
   the Quest accept/complete pages in Azeroth's Compendium. Check fallbacks
   when translation is absent. Progress is checked in its own supported context,
   **not** as a Compendium Quest page section.
3. Check native QuestFrame, Journal and quest giver labels, with Shift held
   and released. Verify placeholders and original English fallback.
4. Disable Quest; install **Gossip alone**, then reload. Confirm Ukrainian
   can be selected, Cyrillic renders, native NPC greetings/replies work, and
   no shared canonical ID displays another NPC's translation.
5. Enable both modules, then repeat without any Ukrainian audio pack. Ensure
   both datasets coexist and no false Play button or fake voice metadata appears.
6. Repeat with ClassicUA enabled/disabled. Verify precedence, all placeholder
   variants and English fallback. Check the WoW error log for Lua faults.
7. On an older unsupported Spoken version, confirm no crash and that native
   translations still work where supported; Compendium Text Pack is unavailable.
8. Test the installer backup and restore only with the game closed.

**Do not close issue #38 or merge PR #39 based only on CI.** Actual client
verification and a separate authorized merge are required.
