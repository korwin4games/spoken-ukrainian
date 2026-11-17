# Stage 1 testing

Automated implementation: complete. Full in-game acceptance: passed, as reported by the user on 2026-11-16.

## Automated commands and results

From `/home/korwin/projects/wow/spoken-ukrainian`:

```sh
uv run --locked python tools/build.py
uv run --locked python -m unittest discover -s tests -v
```

For a different local upstream checkout:

```sh
SPOKEN_SOURCE=/absolute/path/to/spoken-wow uv run --locked python -m unittest discover -s tests -v
```

Final result: 16 tests passed. Tests require Python 3, Git and the system Lua 5.4 shared library. Missing prerequisites fail rather than skipping the contract tests. No pip/npm packages or network access are needed.

| Coverage | Automated result |
| --- | --- |
| Exact folder, TOC, dependencies, Lua load list | Passed |
| Exact ZIP entries, CRC, SHA-256 and reported size | Passed |
| Byte-identical repeated builds and changed source mtime/mode | Passed |
| Path traversal, absolute/mixed paths, extra assets and symlinks rejected | Passed |
| Original diagnostic bytes match recorded provenance hashes | Passed; this is integrity evidence, not an automated copyright detector |
| Pinned source hashes and map 1429/Elwynn/Forever references | Passed |
| Metadata discovers non-client `ukUA` with native name and menu choices | Passed on fixture `enUS` |
| Zones then empty subzones, one entry, required glyphs and punctuation | Passed |
| Voice/text settings independent and reload resolves chosen text | Passed |
| English lore references, English UI strings and voice fallback preserved | Passed |
| Disabled/removed pack and stale Ukrainian preference recover to English | Passed |
| Missing font blocks selection; missing Places metadata rejects lore | Passed |
| No audio registry/clip/playback from diagnostic content | Passed |
| No other pack global accesses, network/database/queue operations | Passed in restricted execution |
| Four Stage 0 document hashes preserved; upstream unchanged during tests | Passed |

The test suite snapshots tracked and nonignored untracked upstream file contents before and after running. This detects content changes during tests; it does not monitor file access or ignored caches. The task also compared the upstream checkout's 4076-file baseline after implementation. No upstream file modifications were made. Git's internal metadata/access times are outside this content comparison.

Archive:

```text
SpokenCommunity_ukrainian-diagnostic.zip
Size: 1651 bytes
SHA-256: 5a2519858229c9aa004dbef075d1c8c51561e33f09828112504e0558005c8a8e
```

The `.zip.sha256` sidecar permits local verification:

```sh
cd dist
sha256sum -c SpokenCommunity_ukrainian-diagnostic.zip.sha256
```

## GitHub Actions

`.github/workflows/ci.yml` runs on pushes, pull requests and manual dispatch. It checks out this project and the Spoken revision read from `sources.lock.json` into separate directories, sets up Python 3.12, and installs the Lua 5.4 shared library on Ubuntu. It then runs:

```sh
uv run --locked python tools/build.py
uv run --locked python -m unittest discover -s tests -v
```

`SPOKEN_SOURCE` points to the separate pinned checkout. The workflow has read-only repository permissions and publishes no artifacts or releases. Runner setup downloads public source and dependencies; the build and tests remain offline.

## Harness scope and limitations

`tests/contract.lua` executes complete, unmodified pinned `Languages.lua`, `UI/Options.lua`, `API.lua`, Places `Data/Languages.lua`, `Language.lua`, `Core.lua` and `Audio.lua`. It does not replace `RegisterLoreData`, the registry or language-selection logic. The pack receives a restricted proxy exposing only the real registration API so calls and forbidden global accesses can be checked; that proxy exists only in tests.

The Python runner embeds system Lua 5.4 through `ctypes`. Upstream implementation chunks are loaded with `load(..., environment)` into the requested test environment. A test-only `setfenv(1, environment)` compatibility stub asserts the expected target because the environment was already set at chunk load. The addon itself uses ordinary Lua table literals and method calls compatible with the target game. These tests are not proof of Lua 5.1/client parity and do not modify source or ship a shim.

Necessary fixtures model addon metadata/enable state, profile settings, `GetLocale() == "enUS"`, frames, and font-string width. Font fixtures exercise both success and missing-glyph guards in the actual upstream code, but cannot prove actual fonts. Synthetic English lore is used instead of copying upstream prose. Metadata loading is supplied before dependent Lua, modeling the TOC dependency contract. The complete event lifecycle, actual settings widgets, Compendium rendering and other addons' hooks are not simulated. Game testing must confirm those.

No ClassicUA files were read or imported for Stage 1. Content provenance rests on original authorship, a two-file archive allowlist, byte hashes and code inspection. Runtime sandbox assertions prevent the addon from using any API beyond lore registration; they do not purport to detect the origin of arbitrary future text.

## Installed environment observed read-only

| Field | Observation |
| --- | --- |
| AddOns path | `/media/korwin/00C6E733C6E7281C1/Games/World of Warcraft/_forever_/Interface/AddOns/` |
| Installed Spoken TOC | Version 3.9.0, Interface 16001 |
| Installed Spoken_Places TOC | Version 3.9.0, Interfaces 11509/20506/16001 |
| Pinned source tested | `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7` |
| ClassicUA folder | Absent at initial inspection; user subsequently reported successful enabled/disabled testing. Exact version not supplied. |
| Actual Forever build | User reports the environment checks passed; exact build number not supplied in the report |
| Actual client locale | enUS, based on the user-reported manual check |
| Interactive game session/screenshots | User reports all manual tests passed; screenshots not supplied |
| AddOns directory writes by this task | None |

Installed TOC versions are filesystem observations, not confirmation that the game loaded those versions or that their source bytes match the pinned checkout.

## Exact manual installation

Exit WoW Forever completely before adding the new addon. Keep the existing `Spoken` and `Spoken_Places` folders installed and enabled. The commands below are for the user to run; they were not executed against the game directory by this task.

```sh
cd /home/korwin/projects/wow/spoken-ukrainian
uv run --locked python tools/build.py
(cd dist && sha256sum -c SpokenCommunity_ukrainian-diagnostic.zip.sha256)
unzip -l dist/SpokenCommunity_ukrainian-diagnostic.zip
unzip -n dist/SpokenCommunity_ukrainian-diagnostic.zip -d '/media/korwin/00C6E733C6E7281C1/Games/World of Warcraft/_forever_/Interface/AddOns/'
```

`-n` avoids overwriting an existing file. If that diagnostic folder already exists, stop and inspect it before installing; do not merge different versions. The expected files are:

```text
/media/korwin/00C6E733C6E7281C1/Games/World of Warcraft/_forever_/Interface/AddOns/
  SpokenCommunity_ukrainian-diagnostic/
    SpokenCommunity_ukrainian-diagnostic.toc
    Lore.lua
```

Do not copy the repository, docs, tests or `dist` folder into AddOns. Start Forever again and enable **Spoken Ukrainian Diagnostic**, **Spoken** and **Spoken Places** in the AddOns list.

## Manual test procedure

Record current settings first so they can be restored. Enable Lua error reporting with `/console scriptErrors 1` for this session, recording the previous setting. First test with ClassicUA disabled. For isolated silence testing, disable all audio-pack addons, retaining Spoken, Spoken_Places and the diagnostic pack; alternatively use an isolated addon/profile setup and restore it afterwards. The diagnostic pack cannot disable unrelated English audio or other modules.

1. Confirm the diagnostic title/version in the addon list and dependencies enabled. Log in; check for Lua errors.
2. Record the game environment with `/dump GetBuildInfo()` and `/dump GetLocale()`. The latter must report `enUS`. Record loaded metadata using `/dump C_AddOns.GetAddOnMetadata("Spoken", "Version")` and the corresponding `Spoken_Places` value.
3. Verify the live map with `/dump C_Map.GetMapInfo(1429)`: expect the Elwynn Forest identity. Do not change the map ID if that fails; record the discrepancy.
4. Open Spoken settings, Language, Voice Language. Confirm **Українська** is listed. Selecting it is a registration check, not a request for a Ukrainian recording. Record If a Voice Is Missing and restore its previous value after testing.
5. Open Places settings and Text Language. Confirm **Українська** is listed. Select it and accept the reload prompt, or type `/reload`. Confirm the voice choice remains independent. Optionally check `/dump SpokenPlaces:GetLanguage()` reports `ukUA` and `/dump GetLocale()` remains `enUS`.
6. Open Azeroth's Compendium, Places (`/spp window`). Turn off **Found Only** and **Voiced Only** filters if they hide the entry. If Elwynn is undiscovered, temporarily enable Spoken's **Unlock Undiscovered Places**. Search/select **Elwynn Forest** under Eastern Kingdoms.
7. Read the diagnostic paragraph. It must identify itself as a language/font test and contain no real game lore. Inspect `і ї є ґ І Ї Є Ґ`, three apostrophe forms, «guillemets», curly and straight quotes, punctuation, dash and ellipsis for boxes, missing characters or clipping. The zone heading may stay English because it comes from the client.
8. Confirm the diagnostic pack adds no voice-pack row/recording and no sound. With other audio packs disabled, there must be no clip; `/dump SpokenPlaces:HasAudio(1429)` should return false. An absent/disabled Play button is expected. Do not require silence while unrelated packs remain active: upstream fallback audio is separate.
9. Set Voice Language back to its recorded value. Set Places Text Language to English and reload. Confirm ordinary English lore returns and the client locale is unchanged.
10. Repeat Ukrainian selection and reload once to check persistence, then restore English. Exit the game, disable the diagnostic addon, log back in and confirm Ukrainian disappears when no other ukUA pack exists and English behavior returns. Also check a stale ukUA preference recovers to English when the pack is disabled.
11. With the game closed, remove only `SpokenCommunity_ukrainian-diagnostic` if uninstalling. Leave all other addons untouched. Restore audio-pack enable states, discovery filters, unlock setting, language choices and the previous scriptErrors value.
12. If ClassicUA becomes available, repeat steps 1–10 with it enabled, recording its version and any errors or changed display behavior. Do not install ClassicUA automatically for this task.

If Ukrainian is hidden, record whether the metadata is present and whether the upstream font guard rejects it. Do not spoof the client locale, force readiness or patch registry functions. No bundled font is promised; evaluate a separately licensed font only if real testing establishes the need.

## Manual result ledger

All manual checks passed successfully, as reported by the user on 2026-11-16, with ClassicUA disabled and enabled. These results record the user's testing, not an interactive game session performed by the automation agent.

| Check | ClassicUA disabled | ClassicUA enabled |
| --- | --- | --- |
| Exact loaded Spoken/Places versions, Forever build and enUS locale recorded | Passed | Passed |
| Diagnostic addon listed; dependencies load without Lua errors | Passed | Passed |
| Live map 1429 resolves to Elwynn | Passed | Passed |
| Ukrainian Voice Language entry | Passed | Passed |
| Ukrainian Places Text Language entry | Passed | Passed |
| Selection, reload and settings separation | Passed | Passed |
| Compendium diagnostic entry shown | Passed | Passed |
| All required glyphs and punctuation render | Passed | Passed |
| No diagnostic recording or playback | Passed | Passed |
| English restored after switch/reload | Passed | Passed |
| Disable/remove recovers ordinary behavior | Passed | Passed |

The user confirmed all manual checks passed on 2026-11-16. Exact loaded version strings, the Forever build number, screenshots and detailed logs were not supplied with that confirmation. Stage 1 manual acceptance is recorded as passed on that basis. No claim is made for Ukrainian Quest, Gossip, Readables or Bosses text display; Stage 2 is not started.
