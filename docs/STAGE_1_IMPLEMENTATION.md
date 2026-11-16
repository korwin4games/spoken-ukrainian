# Stage 1 implementation

Implemented 2026-11-16 as an independent sibling workspace at `/home/korwin/projects/wow/spoken-ukrainian`. Automated implementation is complete; the user reported all in-game acceptance checks passed on 2026-11-16. The upstream Spoken checkout and the game AddOns directory are read-only inputs to this task.

## Project structure

```text
spoken-ukrainian/
  .gitignore
  README.md
  THIRD_PARTY.md
  sources.lock.json
  addons/SpokenCommunity_ukrainian-diagnostic/
    SpokenCommunity_ukrainian-diagnostic.toc
    Lore.lua
  tools/build.py
  tests/
    test_stage1.py
    contract.lua
    lua_runtime.py
  docs/
    IMPLEMENTATION_PLAN.md
    SOURCE_INTEGRATION.md
    COMPATIBILITY_MATRIX.md
    LEGAL_AND_ATTRIBUTION.md
    STAGE_1_IMPLEMENTATION.md
    STAGE_1_TESTING.md
  dist/                           ignored local outputs
    SpokenCommunity_ukrainian-diagnostic.zip
    SpokenCommunity_ukrainian-diagnostic.zip.sha256
```

A local Git repository has no remote; nothing is pushed or published. The four Stage 0 files are preserved byte for byte, with hashes in `sources.lock.json`. Their roadmap is unchanged because implementation did not reveal a new architectural discrepancy. Historical upstream-relative links retain their original source context; use the pinned upstream URLs when following those outside Spoken's checkout.

## Public contract and source pin

Tests read source using `git show` at Spoken commit `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`, version 3.9.0. `sources.lock.json` lists SHA-256 hashes for every tested source/reference file and diagnostic addon file. The test command verifies those hashes before executing code. A different current checkout HEAD does not silently change the tested implementation. No upstream code is copied into the installable addon.

The TOC uses exactly the requested metadata and loads only `Lore.lua`. `Dependencies: Spoken, Spoken_Places` establishes addon load order. The installed addon list and metadata are available to Spoken's registry before the dependent pack's Lua runs; the pack does not call `DeclareLanguage` or manipulate registry internals.

Relevant pinned source:

- `addons/Spoken/Languages.lua:80,110`: metadata scan, native names, non-client language declarations, disabled-addon exclusion.
- `addons/Spoken/UI/Options.lua:198,234,245`: name rendering, actual client language and installed language choices.
- `addons/Spoken/API.lua:502,537,575`: language preferences, registry access and voice selection.
- `addons/Spoken_Places/Language.lua:136,252,346,430,450`: community lore readiness, font gate, text-language selection/reload, allowed language loading and lore registration.
- `addons/Spoken_Places/Core.lua:10,244`: public `SpokenPlaces` global and zone lookup.
- `addons/Spoken_Places/Audio.lua:405,497`: no clip without a real recording.

The only public runtime API used by the diagnostic Lua is:

```lua
SpokenPlaces:RegisterLoreData("ukUA", "zones", zones)
SpokenPlaces:RegisterLoreData("ukUA", "subzones", {})
```

One combined zones table contains exactly map `1429` with `name`, `short` and `full`. Empty subzones explicitly establishes a complete empty table for this small dataset. Registration replaces a whole kind only within Ukrainian; it does not append rows or replace English tables. No saved variables, hooks, timers, event handlers, slash commands, audio registry or playback calls are introduced.

## Map and text provenance

The pinned `pipelines/places/tools/seed/zones.json` maps `1429` to `Elwynn Forest`. `seed/forever-places.json` contains Forever-specific subarea handling under that map; it excludes an unreachable duplicate subarea, not Elwynn itself. Spoken and Places TOCs support `16001`. These are repository identity checks; live `C_Map.GetMapInfo(1429)` confirmation remains in the manual procedure.

The paragraph explicitly describes a language/font diagnostic, not Warcraft lore. It contains `і ї є ґ І Ї Є Ґ`, ASCII/curly/modifier apostrophes, guillemets, curly/straight quotation marks, punctuation, a dash and an ellipsis. The `name` remains the English map identity so the entry can be found on an English client. The text is original task content, with no source translation import. See `THIRD_PARTY.md`.

## Language and fallback behavior

Spoken discovers `ukUA` from Places metadata and labels it `Українська` when fonts draw the name. The registry marks it `client = false`, `builtin = false`. `GetLocale()` stays `enUS`; no runtime function is replaced.

Voice Language belongs to Spoken. Text Language belongs to Places and takes effect after reload. Selecting either does not change the other. The native-language name and lore are subject to upstream font checks. No font is bundled and no rendering guard is bypassed. Missing glyphs may hide Ukrainian from the Places menu; this must be tested in game.

English interface-string fallback and configured voice fallback remain available. Places lore itself has no per-page fallback: with Ukrainian selected this intentionally partial pack contains only the diagnostic zone and no subzones. Other lore may be absent until Text Language is restored to English. Existing English audio packs can still be selected or used as fallback by upstream Spoken; this pack provides and requests no audio. Disable other voice packs for the isolated silence test.

## Build and dependencies

```sh
cd /home/korwin/projects/wow/spoken-ukrainian
python3 tools/build.py
python3 -m unittest discover -s tests -v
```

Python standard library only for build and test orchestration. The Lua contract tests use the already installed `liblua5.4` through `ctypes`, without a Python package or interpreter installation. The Stage 0 Node preference was advisory; Python's standard ZIP/hash/test support avoids npm dependencies for this two-file pack. No parser, source adapter or database is needed in Stage 1.

The builder allowlists exactly two regular files, rejects symlinks and extra entries, validates exact metadata/load order, and writes sorted ZIP_STORED entries with fixed 1980 timestamps and fixed file permissions. It ignores source mtime and permissions. Stored bytes avoid zlib version differences. ZIP paths are relative POSIX paths under the sole addon folder. The SHA-256 sidecar is outside the archive.

Output is `dist/SpokenCommunity_ukrainian-diagnostic.zip`. Build prints its size and SHA-256. Build and tests do not contact GitHub, Spoken services, databases or TTS providers. Tests require the pinned commit already present in the sibling checkout, or `SPOKEN_SOURCE` pointing to another local checkout. There is no automatic fetching.

## Verification limits and next steps

See [STAGE_1_TESTING.md](STAGE_1_TESTING.md) for results, exact installation commands and pending manual checks. Contract tests execute the real pinned source with necessary client API fixtures; they do not load the complete UI or prove game font rendering, load lifecycle or ClassicUA coexistence. The system Lua runtime is 5.4, not WoW's Lua runtime; the test-only environment bridge is described there.

No new architectural blocker was found. The user reported successful manual checks of client fonts, dependency lifecycle and Compendium presentation; exact build details and screenshots were not supplied. No new support is claimed for Ukrainian Quests, Gossip, Readables or Bosses. Stop at Stage 1; source adapters and any further stage require a separate task.
