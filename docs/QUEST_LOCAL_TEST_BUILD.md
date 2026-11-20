# Install and test the private Quest and Gossip addons

| Addon | Dependencies | Native game text |
| --- | --- | --- |
| `Spoken_Quest_UA` | `Spoken_Ukrainian`, official `Spoken` and `Spoken_Quests` | NPC QuestFrame titles, descriptions, objectives, progress and completion. Accepted Quest Journal titles, description and overall objectives when corresponding imported fields exist. Quest labels in the quest lists shown by Gossip and NPC greeting windows. |
| `Spoken_Gossip_UA` | `Spoken_Ukrainian`, which depends on official `Spoken` | Exact NPC/English-hash greetings and reply choices, with NPC-specific precedence, common fallback and scoped exclusions. |

The Quest module registers through the pinned public load-on-demand Community Pack interface with an empty sound-length table. Native game windows, the optional Quest preview, and Spoken narrator captions are separate surfaces.

The Forever Journal adapter uses the hooks demonstrated in pinned ClassicUA
`1770d208ad853d23d61105cf510d53804770d916` in `scripts/frame_hooks.lua`
(`quest_info_quest_id`, `update_forever_quest_log_list` and
`prepare_forever_quest_texts`). It resolves details using
`C_QuestLog.GetSelectedQuest()` during `QuestInfo_Display` and finds list
row IDs in the pool during `QuestScrollFrame:UpdateBackground`. It uses only
emitted Quest fields. ClassicUA's separate objective-row hook uses
`entries.translate_quest_objective` for live task lines. The build has no
audited equivalent for those dynamic task lines or reward items. If the client omits the verified
hooks, the corresponding surface stays native. The static Noto Sans font
ships in the Quest addon with its [OFL notice](../addons/Spoken_Quest_UA/OFL-NotoSans.txt).
The Quest widgets keep their size and font flags and restore the original
font when Shift shows the captured native text.

## Build each module

Prepare clean checkouts of ClassicUA and Spoken at the revisions in [sources.lock.json](../sources.lock.json). See the [CLI guide](CLI.md) for checkout setup.

```bash
uv sync --locked
uv run --locked python tools/build_ukrainian.py --module Spoken_Quest_UA --classicua ../ClassicUA --spoken ../spoken-wow
uv run --locked python tools/build_ukrainian.py --module Spoken_Gossip_UA --classicua ../ClassicUA --spoken ../spoken-wow
```

Each private ZIP under `dist/` contains the shared addon and one selected module, with its own `.zip.sha256` sidecar. The output names are `Spoken_Quest_UA_Local_Test.zip` and `Spoken_Gossip_UA_Local_Test.zip`. Keep both ZIPs and SQLite data private.

## Safe local addon installer with uv

1. Close WoW Forever. If previously installed, move `Spoken_Quests_UA` out of `Interface/AddOns` to a backup location. For manual installation, disabling it for all characters also prevents duplicate hooks. The installer requires the folder to be moved and reports its presence before writing. Keep your translation database and source checkouts.
2. Substitute the real game path below. Run the dry run for the ZIP you want, then remove `--dry-run` to install. Repeat with the other ZIP to install both.
3. Restart the client. Enable the shared addon and the selected module, including official dependencies. Disable ClassicUA when testing these hooks. Either new module can be disabled independently.

```bash
uv run --locked python tools/install_addon.py --addons "/path/to/Forever/Interface/AddOns" --archive dist/Spoken_Quest_UA_Local_Test.zip --dry-run
uv run --locked python tools/install_addon.py --addons "/path/to/Forever/Interface/AddOns" --archive dist/Spoken_Gossip_UA_Local_Test.zip --dry-run
```

## Native QuestFrame translation (issue 19)

1. Enable Quest alone. Open an eligible NPC quest and test the title, accept text and objectives. Check progress and completion separately. Hold Shift for the original and release it to restore Ukrainian. Check an untranslated quest for native English. The opt-in preview is available via `/spokenuk preview on`.
2. Enable Gossip alone. Check a verified greeting and reply, a common fallback and an unmatched reply. Test each with Shift and confirm a Quest window still shows native text.
3. Enable both and repeat on a quest giver that also has Gossip choices. Check that Quest titles and Gossip dialogue both translate and restore independently. Verify player-name substitution and `і ї є ґ` in the game font.
4. Repeat with ClassicUA enabled to check that it takes precedence. Confirm official Spoken behavior is intact.

Lua simulations exercise the native hooks. Record actual client results separately. Use the [Translation Manager guide](TRANSLATION_MANAGER.md) for build and review status.
