# Spoken Ukrainian

Local Stage 1 Places diagnostic Community Pack for WoW Forever. Spoken Player and Spoken_Places are external dependencies. This pack registers `ukUA` and supplies one original language/font test for Elwynn Forest (`1429`). It contains no audio or imported translations.

```sh
python3 tools/build.py
python3 -m unittest discover -s tests -v
```

Build requires Python 3. Tests additionally require Git, the system Lua 5.4 shared library, and the pinned Spoken commit in the sibling `../spoken-wow` checkout. Set `SPOKEN_SOURCE=/absolute/path/to/spoken-wow` to use another checkout. Nothing fetches source or installs packages automatically.

Output: `dist/SpokenCommunity_ukrainian-diagnostic.zip`, with a `.zip.sha256` sidecar. The archive contains only its TOC and `Lore.lua` in one addon folder. Do not install the whole project in AddOns.

[Implementation](docs/STAGE_1_IMPLEMENTATION.md) describes the contract, structure and limitations. [Testing and exact manual installation](docs/STAGE_1_TESTING.md) records automated results and pending in-game checks. The user reported all Stage 1 manual checks passed on 2026-11-16. This does not establish Ukrainian Quests, Gossip, Readables or Bosses display support.

Stage 0 documents are preserved byte for byte in `docs/`. Their upstream-relative source links retain their original checkout context; the pinned Community Packs guide is at https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/community/README.md.

## ClassicUA source audit (Stage 2A)

A read-only Python adapter parses a separate, clean ClassicUA checkout at commit `1770d208ad853d23d61105cf510d53804770d916`, resolves actual loading/override semantics and reports source inventory/provenance. It does not execute source Lua, create translated packs or convert source IDs to Spoken IDs.

```sh
python3 tools/classicua_audit.py --source /absolute/path/to/ClassicUA
python3 -m unittest discover -s tests -v
```

The metadata-only report is written to ignored `build/classicua-audit.json`; no translation bodies are serialized. Its detailed provenance makes the local report about 52 MB. The 36 new tests use synthetic fixtures and need no ClassicUA installation. The standard suite now has 52 tests, including all 16 Stage 1 tests. CI already discovers them and never downloads the ClassicUA corpus.

See [Stage 2A implementation](docs/STAGE_2A_IMPLEMENTATION.md) and [test results/source inventory](docs/STAGE_2A_TESTING.md). Source redistribution and TTS permissions remain unresolved. No production access, generation, translated pack publication or Stage 3 mapping is included.

## Versioning

The authoritative [VERSION](VERSION) file defines the project version, initially **0.0.1**. Use the CLI to read the current value; no configuration duplicates it.

```sh
python3 tools/version.py show
python3 tools/version.py check
python3 tools/version.py bump patch --dry-run
python3 tools/version.py bump patch
python3 -m unittest discover -s tests -v
```

PATCH fixes bugs; MINOR adds features and may carry explicitly marked BREAKING changes during 0.x. The first stable MAJOR requires explicit approval (`--approve-stable`); after 1.0.0, public-interface breaks increment MAJOR. Bumps change only VERSION. Prepare the matching new dated [changelog](CHANGELOG.md) section manually before `check` and commit; historical sections are preserved.

The diagnostic addon stays at **0.1.0**, independently of the project version. Annotated project Git tags use `v<project-version>`. A GitHub Release is a separate optional publication attached to a tag. Committing, tagging, pushing and publishing are explicit reviewed operations; the CLI and CI do none automatically. See [VERSIONING.md](docs/VERSIONING.md) for the full policy and release preparation steps.
