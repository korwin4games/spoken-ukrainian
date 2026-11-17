# Spoken Ukrainian — Quest Import naming and in-game test plan

**Status:** Offline Quest 1:1 importer in PR #17; **not an installable Quest
Community Pack**. This checklist does **not** claim a live WoW Forever test.

## Names and responsibilities

| Component | Name | What it actually is |
| --- | --- | --- |
| Parent project | **Spoken Ukrainian** | Independent translation/community-pack project. |
| Official Spoken module | `Spoken_Quests` | Installed upstream Spoken module. **Never rename, fork, patch, or replace it.** It owns both Quests and Gossip. |
| Quest import/review UI | **Quest Translation Import · Spoken_Quests (offline)** | Local browser tool (Python HTTP server) for ClassicUA Quest `accept`, `progress`, `complete` text. No Gossip implementation. |
| Quest CLI | `tools/review_ui_server.py --auto-import-one-to-one` | Offline import of audited unique Quest candidates to ignored `build/` storage, with summary counts across the entire Spoken inventory. |
| **Future** Ukrainian Quest pack | `SpokenCommunity_ukUA_Quests` — **proposed, not created** | Separate installable community-pack folder/TOC, **only after** verifying the upstream public Quest language/text contract and packaging rights. Do not mistake this proposed name for a working AddOn. |
| Existing playable diagnostic | `SpokenCommunity_ukrainian-diagnostic` | **Places** diagnostic: depends on `Spoken_Places`, registers one invented Ukrainian Elwynn Forest lore entry. It does not import ClassicUA or implement Quests. **Keep unchanged.** |

`ukUA` is a Spoken content language; it must not spoof the real WoW
`GetLocale()`. Compendium is the core UI, not a fifth module. Never
rename `Spoken_Quests` to `Spoken_Ukrainian_Quests`: that is a different
AddOn identity and breaks the intended upstream integration.

## Troubleshooting: `public_git_read_failed` at startup

The importer reads pinned **local Git checkouts** with `git -C`; it
does not fetch GitHub sources on demand. Example paths such as
`/absolute/path/to/ClassicUA` and `/absolute/path/to/spoken-wow`
are **placeholders**: replace them with *real* paths on your computer.

Verify each repo before starting:

```sh
git -C /your/real/spoken-wow rev-parse --show-toplevel
git -C /your/real/spoken-wow rev-parse HEAD
git -C /your/real/spoken-wow status --short
git -C /your/real/ClassicUA rev-parse --show-toplevel
git -C /your/real/ClassicUA rev-parse HEAD
git -C /your/real/ClassicUA status --short
```

The root path must be a directory with `.git` (or a Git worktree's
`.git` file). Both checkouts must have clean tracked files and
their **HEAD** at the exact pins:

- Spoken: `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`
- ClassicUA: `1770d208ad853d23d61105cf510d53804770d916`

For example, **only if** the two source repositories were cloned
as sibling directories of `spoken-ukrainian`, these flags are
`--classicua ../ClassicUA --spoken ../spoken-wow`. A ZIP unpacked
without `.git` is not sufficient. Use clean additional checkouts
for the pinned commits rather than resetting or discarding changes
from an existing working copy.

The CLI now prints targeted hints for missing paths, non-Git folders
and unreadable Spoken checkouts instead of only
`review_ui_pinned_sources_or_local_bind_failed`. If a valid Git root
has the wrong pinned SHA, the program reports
`public_revision_mismatch`; switching to a clean pinned checkout
is necessary.

## Step-by-step — verify the **offline** Quest importer

1. Use the PR #17 branch with *exact pinned* Spoken and ClassicUA
   checkouts. Run `python3 -m unittest discover -s tests -v` and verify
   the existing compatibility/Quest tests pass.
2. Run `python3 tools/review_ui_server.py --classicua /absolute/path/to/ClassicUA --spoken /absolute/path/to/spoken-wow`.
   Open `http://127.0.0.1:8765/` on the same computer.
3. Confirm the title **Quest Translation Import · Spoken_Quests**
   and that the interface says **offline** and **Quests only**.
4. Click **Автоімпорт Quests 1:1 · ClassicUA**. The summary counts the
   **entire** canonical Spoken inventory, while source imports refer
   only to the Quest slice. Check distinct totals for
   `machine_one_to_one_imported` (provisional) vs independently
   `human_reviewed_imported_total`.
5. Alternatively stop the server and run:
   ```sh
   python3 tools/review_ui_server.py \
     --classicua /absolute/path/to/ClassicUA \
     --spoken /absolute/path/to/spoken-wow \
     --auto-import-one-to-one
   ```
   The console prints the source breakdown and actual imported counts.
   The only generated content is under ignored
   `build/machine-one-to-one.json` and/or
   `build/translation-reviews.json`; this is **not** game content.
6. Run the command again on unchanged inputs. Confirm the results are
   idempotent and no duplicate versions are created. Do not copy
   those JSON files into `Interface/AddOns`.

## Step-by-step — inspect WoW Forever **without a Quest pack**

This is a **baseline/manual check**, not proof of Ukrainian Quest import
display (a Quest pack has not been generated).

1. Exit WoW completely. Back up the existing game
   `Interface/AddOns` configuration. Do not overwrite official
   `Spoken` or `Spoken_Quests` files.
2. In AddOns, enable official `Spoken` and `Spoken_Quests`.
   The existing `SpokenCommunity_ukrainian-diagnostic` is
   **Places-only** and can be left disabled for this isolated test.
   Neither the offline importer nor `SpokenCommunity_ukUA_Quests`
   should be shown as an installed addon.
3. Log in to WoW Forever. Open Spoken options and confirm the
   official **Quests** module loads without Lua errors. Record client
   locale and options for voice/text fallback; do **not** change
   `GetLocale()`.
4. Visit a quest giver and inspect **accept**, **progress** and
   **completion**, when available. Compare native Blizzard/ClassicUA
   quest-window text with Spoken's own captions/transcript separately;
   enabling ClassicUA for native frames does **not** prove that Spoken
   captions are localized. Check a Gossip interaction separately:
   Gossip is under `Spoken_Quests` but is not included in this importer.
5. Optional: toggle ClassicUA on/off and `/reload`, observing only
   the effects on the native quest window. With no Ukrainian Quest
   Community Pack installed, **do not expect** imported `build/`
   translations to appear in Spoken.
6. Record any Lua error, screenshot of the AddOns list and Spoken
   options, quest ID/event, English-client locale, and whether
   Spoken's caption, native Blizzard frame or audio changed.
   Re-enable normal addons and original fallback settings afterward.

## Blocking acceptance criteria for a future playable Quest pack

A future **`SpokenCommunity_ukUA_Quests`** is ready to test in the
game only after all of the following: (1) confirmed public
`Spoken_Quests` Community Pack registration and canonical-ID
contract, (2) safe text-only captions on an `enUS` client **without
invented audio**, (3) independent review/promotion of machine-provisional
pairs before publication, (4) signed-off source attribution/rights and
revalidated current source bytes, (5) isolated install/remove and
English fallback tests in the actual WoW Forever client. The pinned
Stage 2B baseline does **not** establish independent Ukrainian
text-only Quest captions on `enUS`; therefore renaming a TOC
would not make this feature work.

**Do not report "tested in game" until a human has run these acceptance
steps on a real client and supplied observations.** Automated Lua
contract tests are useful but are not a WoW game session.
