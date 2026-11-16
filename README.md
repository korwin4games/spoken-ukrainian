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

No publication, production access, TTS or Stage 2 work is included.
