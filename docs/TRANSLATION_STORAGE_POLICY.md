# Translation storage and source update policy

**Status: design and validated configuration only.** This document defines how opted-in source text will eventually be persisted after independently checked source-to-Spoken mapping. **No source-copy writer, upstream update watcher, Git auto-commit, runtime pack integration or approved real mapping is implemented by this PR.** Changing the option does not itself write any files.

## Configuration

`config/translation_sources.json` schema v2 keeps ordered provider selection and adds one boolean per source:

```json
{
  "schema_version": 2,
  "sources": [
    {"name": "classicua", "save_translations": true},
    {"name": "another", "save_translations": false},
    {"name": "own_translator", "save_translations": true},
    {"name": "original_english", "save_translations": false}
  ]
}
```

- `save_translations: true` **opts a provider into a future reviewed storage workflow**, it is not automatic approval or an immediate disk write.
- `false` keeps provider lookup available in its configured order but excludes it from our persistent translation corpus.
- `original_english` can never be marked saveable: it is a fallback, not a Ukrainian translation.
- The existing `own_translator` is **mock-only**. Its opted-in flag will have no effect until a real provider and explicit review contract exist. `another` is a stub and is not opted in.
- Schema v1 (ordered list of source names) remains readable with *all save flags false*. `sources: []` and `{}` still use the actual client locale with zero provider calls. Versions, types, unknown keys, duplicates, missing flags and saving English are rejected, not guessed.
- Source priority decides **which candidate is considered**. Storage eligibility only governs **whether that chosen candidate may later enter our local review/store workflow**; it does not change provider priority, bypass reviews, choose runtime locale, or guarantee publication.

## Planned repository layout

```text
translations/ukUA/
  places/zones/<map-id>.yaml               # our curated/rewritten text
  places/subzones/<map-id>/<slug>.yaml
  readables/pages/<spoken-page-id>.yaml
  bosses/<map-id>/<boss-key>.yaml
  quests/...                                # including Gossip in Quests module
  ui/...
  imported/classicua/<family>/<id>.yaml    # source copies; source-owned
  imported/another/<family>/<id>.yaml      # only after separate provenance/rights clearance
```

The exact filesystem encoding of special canonical IDs and voice/page variants must be deterministic and collision-free before a writer is added. **Canonical IDs live inside records**, never inferred from filenames. `ukUA` means a Spoken content language, not a real client locale. Compendium is part of the core UI, not a fifth official module.

- **Our curated translations** live directly under family directories and may adapt an imported text, recording `derived_from` attribution.
- **Saved provider translations** live under `imported/<provider>/` and are treated as immutable per reviewed import. A revised snapshot is a proposed new version, never a silent overwrite of a manually edited file.
- **Unreviewed original external data** stays in ignored `build/` as a staging artifact; `dist/` contains generated output only. The project must not commit raw source snapshots, bulk corpora, audio or copyrighted stories without explicit scoped authorization and provenance/rights review.

## Planned record (illustrative, invented text)

```yaml
schema_version: 1
canonical_spoken_id: "b:123"
locale: "ukUA"
source:
  provider: classicua
  source_id: "verified-source-identity"
  revision: "<pinned-commit>"
  effective_field_sha256: "<64-char-sha256>"
  source_blob_sha256: "<64-char-sha256>"
  original_english_sha256: "<64-char-sha256>"
translation:
  text: "Вигаданий переклад для прикладу."
  sha256: "<64-char-sha256>"
review:
  identity: approved
  content: pending
  rights: reviewed
```

Real metadata will include the source effective layer/path and evidence/reviewer references, original wording or page-chain evidence, attribution (ClassicUA permission record), and audio-dependency invalidation where applicable. Approval of *identity* alone is not approval of *text*, rights, or publication.

## Planned opt-in import

1. Read **pinned, clean** ClassicUA and Spoken revisions through existing audited adapters. Confirm the *exact* canonical Spoken identity, owner/page-chain/speaker/voice context and a separately approved Stage 3 mapping; name similarity is not sufficient.
2. Resolve the exact **effective ClassicUA field after overrides**. Verify its original bytes, SHA-256, source revision and permission/attribution. `save_translations=true` authorizes local candidate staging for the selected provider, not automatic publishing.
3. Create a reviewable candidate in ignored `build/`. After explicit scoped import review, commit its text/metadata in `translations/ukUA/imported/classicua/` with `content: pending` unless independent text review has passed. Do not turn a candidate into an approved translation by copying it.
4. Store our independently authored or edited translation separately in the curated family directory, with `provider: own` or `derived_from`, and independent review fields. Never modify ClassicUA upstream.
5. A future pack builder consumes **approved and rights-cleared** records only after the relevant Spoken module's runtime text/audio/fallback contract is actually verified. Current Readables and Bosses limitations remain unchanged.

## Planned upstream update check

A later separate workflow may detect a newer ClassicUA revision, but must **not silently change `sources.lock.json`** or overwrite approved text.

- Resolve old and candidate revisions using the identical effective-load rules (Classic/SoD/Forever and field overrides). Compare **effective text and identity context**, not file paths or Git diffs alone.
- **Unchanged effective text and identity:** keep reviews, avoid repeated imports.
- **Changed effective text, same independently valid identity:** propose a new imported version, flag text/grammar review and affected audio stale. Preserve any curated override untouched.
- **Changed mapping evidence, page chain, speaker/voice:** require mapping re-review; do not carry over approvals.
- **Removed source:** report deletion or unresolved fallback; never silently use an outdated copy in a new release.
- **New source:** propose a candidate only after verified canonical identity. Ambiguous identity stays unresolved.

The check should produce **metadata-only** counts/IDs/hashes and a human-reviewable PR; avoid raw third-party text in CI logs or PR descriptions. A person approves the source revision, imported changes, rights and any resulting pack. No auto-merge, auto-release, auto-TTS or background monitoring is included here.

## Relationship to existing stages

Stage 3 already models the ID and effective-source-evidence contract; Stage 4A inventories canonical Spoken targets; Stage 4C has only a synthetic reviewed-Quest bridge. Real human-approved source→target joins remain zero. This PR provides **the opt-in policy schema**, not those missing approval/runtime capabilities. This policy supersedes the earlier assumption in Stage 3 that no copies would ever be stored; the default remains no copies for historical v1 configs and for providers marked `false`.
