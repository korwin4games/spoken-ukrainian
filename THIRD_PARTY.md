# Provenance and third-party content boundaries

## ClassicUA translation permission

The [ClassicUA](https://github.com/greenya/ClassicUA) project is the intended primary source of Ukrainian translated game text and terminology for future Spoken Ukrainian packs.

**За основу взято адаптовані переклади [ClassicUA](https://github.com/greenya/ClassicUA).**

In [ClassicUA issue #100](https://github.com/greenya/ClassicUA/issues/100#issuecomment-6917008199), maintainer **greenya** explicitly approved using and adapting its repository translations in Spoken Ukrainian, creating and distributing AI TTS narration from those translations, and their public distribution. The requested conditions are a link to ClassicUA and acknowledgement that the translations were adapted. The permission is described in [docs/CLASSICUA_PERMISSION.md](docs/CLASSICUA_PERMISSION.md).

This is a public project-specific approval, **not a blanket third-party asset license** or an independently assigned SPDX license. Maintain source revision and translation attribution when releasing derived text/audio. Separate rights and terms still apply to unrelated lore, game content, art, fonts, voice-model/provider usage and other third-party materials.

## Current diagnostic and upstream dependencies

The Ukrainian diagnostic paragraph in `addons/SpokenCommunity_ukrainian-diagnostic/Lore.lua` was originally authored for this project. It tests Unicode characters and punctuation; it is **not** a ClassicUA, Blizzard or Spoken text translation. `Elwynn Forest` and map `1429` identify the existing map. No third-party lore, artwork, fonts, audio or translation tables are bundled in the diagnostic archive.

Spoken is an external dependency. The tests read unmodified Spoken source from commit `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7` via local Git reads; no upstream implementation is vendored into the diagnostic archive. Spoken's code is MIT with third-party content exclusions in its own LICENSE and THIRD_PARTY.md.

The four Stage 0 documents remain preserved historical analyses. Their earlier "permission unresolved" notes predate the [maintainer's approval](docs/CLASSICUA_PERMISSION.md). Stage 2A's adapter reads a separately pinned ClassicUA checkout, generates metadata-only reports and does not yet import or publish translation text.

**No public translated pack, audio take or GitHub Release has been published by the current project build.** Explicit release authorization, code/runtime compatibility verification, content review and provider terms are separate from the granted translation permission.

Stage 3 tooling also reads the pinned public Spoken corpus and literal identity
reference tables in memory. Only IDs, structural evidence and hashes are reported;
no dialogue or lore snapshots are bundled. The ClassicUA numeric string fingerprint
is independently implemented from the pinned public algorithm in
`scripts/utils.lua` (commit `1770d208ad853d23d61105cf510d53804770d916`);
it is not a canonical Spoken identity. ClassicUA remains external and unmodified.
