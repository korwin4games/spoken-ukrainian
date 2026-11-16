# Spoken Ukrainian 🇺🇦

**[English](README.md) | [Українська](README.uk.md)**

**Spoken Ukrainian** is a community project bringing Ukrainian text localization and, in the future, Ukrainian voice narration to [Spoken](https://github.com/rusty-key/spoken-wow) for **World of Warcraft Forever**. It is developed as an independent collection of Spoken Community Packs; the original Spoken Player remains a separate dependency.

> **Development status:** Ukrainian language registration and an original text-only **Places diagnostic pack** have been implemented and manually tested in Forever. The ClassicUA source adapter is implemented. Full Ukrainian quest, dialogue, book, location and boss-story packs **have not yet been released**.

## How Spoken Ukrainian will work

```text
ClassicUA — version-pinned Ukrainian translations and terminology
    |
    v
ClassicUA adapter — parse, apply classic → sod → forever overrides    [done]
    |
    v
Canonical Spoken ID mapping + translation/grammar review              [planned]
    |
    v
Validated Ukrainian content + optional approved AI TTS narration      [planned]
    |
    v
Versioned Ukrainian Spoken Community Packs                            [planned]
    |
    v
Spoken Player + modules in WoW Forever
```

The planned packs cover **Quests** (quest text), **Gossip** (NPC conversations), **Readables** (books, letters and notes), **Places** (location lore) and **Bosses** (encounter stories). ClassicUA supplies existing game-text translations and terminology; it does **not** automatically provide authored Places or Bosses stories, which require separate content and provenance review.

The WoW client locale can remain `enUS`. `ukUA` is registered as a **Spoken content language**, not a new Blizzard client locale. Text-only Ukrainian lore already works for Places. Other modules currently have client-language and/or audio restrictions in the pinned Spoken runtime; supporting independent Ukrainian text there requires further tests and possibly upstream changes. See the [compatibility matrix](docs/COMPATIBILITY_MATRIX.md).

The intended player experience is to install Spoken and the corresponding Ukrainian Community Packs. Players should not need ClassicUA installed merely to use a completed pack. This is the **future design**, not a feature of the diagnostic build. Distribution may use Spoken's Community Pack Manager after a pack is approved.

### Keeping translations up to date

ClassicUA remains the upstream translation source rather than a one-time copy. Future updates will pin and audit a newer ClassicUA revision, compare **effective** translated records (after all overrides), reuse reviewed mappings to canonical Spoken identities, flag changed text and outdated audio for review, and rebuild only the affected packs after approval.

**Source-update diffing, mapping, audio generation and pack release automation are not implemented yet.** See the [Stage 3 specification](docs/STAGE_3_SPECIFICATION.md). Ordinary builds never silently pull the latest ClassicUA branch.

## ClassicUA and attribution

The project uses **[ClassicUA](https://github.com/greenya/ClassicUA)** as the intended main source of Ukrainian game-text translations and Warcraft terminology. Thank you to its maintainers and contributors for their work.

Maintainer **greenya** granted permission in [ClassicUA issue #100](https://github.com/greenya/ClassicUA/issues/100#issuecomment-6917008199) to use and adapt ClassicUA translations for Spoken Ukrainian and to create and distribute AI TTS narration based on them. The response confirms coverage of the repository's translations, states no additional publication restrictions and requests a project link plus acknowledgement that the translations were adapted.

> **За основу взято адаптовані переклади [ClassicUA](https://github.com/greenya/ClassicUA).**

This attribution applies to **future ClassicUA-derived content**. The existing diagnostic paragraph is original and contains no imported ClassicUA translations. The permission does not automatically cover unrelated artwork, fonts or independently sourced lore, or waive the terms of an eventual TTS provider. See [permission record](docs/CLASSICUA_PERMISSION.md) and [third-party content notes](THIRD_PARTY.md).

## Current status

| Component | Status |
| --- | --- |
| Stage 0 — architecture and source/compatibility review | Complete |
| Stage 1 — `ukUA` registration and original text-only Places diagnostic | Implemented; manually tested in Forever |
| Stage 2A — restricted ClassicUA Lua parser, override resolver and metadata-only audit | Implemented |
| Stage 2B — runtime compatibility of independent Ukrainian text | Offline characterization implemented; [results](docs/STAGE_2B_COMPATIBILITY.md), [manual Forever acceptance pending](docs/STAGE_2B_TESTING.md) |
| Stage 3 — canonical ClassicUA → Spoken ID mapping and update-ready comparison | Specified, not implemented |
| Ukrainian text/audio packs, updater and public releases | Not released |

## Build and test

The current downloadable **local build output is only a diagnostic pack**, not a complete Ukrainian localization.

```sh
python3 tools/version.py check
python3 tools/build.py
python3 -m unittest discover -s tests -v
```

Building requires Python 3. The tests additionally use Git, the system Lua 5.4 shared library and the pinned Spoken source checkout (normally in sibling `../spoken-wow`). Set `SPOKEN_SOURCE=/absolute/path/to/spoken-wow` if yours is elsewhere. These commands do not fetch source code, install packages or access production systems.

The build writes `dist/SpokenCommunity_ukrainian-diagnostic.zip` plus its SHA-256 sidecar. It contains only the addon TOC and `Lore.lua`, with original language/font test text for Elwynn Forest (map 1429). **Do not install the entire repository into AddOns.** See the [Stage 1 installation and testing guide](docs/STAGE_1_TESTING.md) for manual installation.

### Audit a pinned ClassicUA checkout (Stage 2A)

```sh
python3 tools/classicua_audit.py --source /absolute/path/to/clean-pinned-ClassicUA
```

The adapter reads a **separate, clean** ClassicUA checkout at the revision in [sources.lock.json](sources.lock.json), validates source hashes and resolves the real `classic → sod → forever` load/override behavior. Its metadata-only report is stored in ignored `build/classicua-audit.json`. It does not execute ClassicUA source Lua, export translations into packs or match Spoken canonical IDs. See the [implementation](docs/STAGE_2A_IMPLEMENTATION.md) and [test report](docs/STAGE_2A_TESTING.md).

## Project versions

The root [VERSION](VERSION) is the **project** version (initial baseline `0.0.1`), separate from independently versioned community addons (the diagnostic addon is `0.1.0`). Use `python3 tools/version.py show` and `python3 tools/version.py check`; changes are documented in [CHANGELOG.md](CHANGELOG.md). Tags and GitHub Releases are explicit, reviewed operations; they are not automatically created by version bumps. See [VERSIONING.md](docs/VERSIONING.md).

## Documentation

- [Implementation roadmap](docs/IMPLEMENTATION_PLAN.md) · [Source integration](docs/SOURCE_INTEGRATION.md) · [Compatibility matrix](docs/COMPATIBILITY_MATRIX.md)
- [Stage 3 mapping/update specification](docs/STAGE_3_SPECIFICATION.md) · [Permission record](docs/CLASSICUA_PERMISSION.md) · [Attribution](THIRD_PARTY.md)
- [Spoken Community Packs guide](https://github.com/rusty-key/spoken-wow/blob/master/community/README.md)

Stage 0 documents preserve the **historical state at the time they were written**, including an earlier unresolved-permission note. The subsequent permission is documented separately rather than rewriting their pinned historical contents.
