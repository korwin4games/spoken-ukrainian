# Spoken ↔ ClassicUA Gossip mapping audit

## Source revisions and reproduction

| Source | Commit | Role |
| --- | --- | --- |
| Spoken 3.9.0 | `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7` | Historical project pin |
| Spoken 3.10.1 | `db5669b0a39815dd38568f0e871f4ced82bc9229` | Official `spoken/v3.10.1` tag and matching TOC version |
| ClassicUA 7.1.1 | `1770d208ad853d23d61105cf510d53804770d916` | Clean project pin, Camelot manifest |

The [audit baseline manifest](../config/gossip_audit_baselines.json) fingerprints the corpus, aliases and TOC at each Spoken commit. The separately fetched 3.10.1 commit may live in a fetch-only repository. The corpus and alias files have identical SHA-256 values at the two revisions. ClassicUA loads `classic → sod → forever`; later layers override supplied Gossip keys and replace supplied `!code` tables whole. The tool reads Git objects and uses the existing audited parser and overlay resolver.

```sh
git init build/spoken-3.10.1
git -C build/spoken-3.10.1 fetch --depth=1 https://github.com/rusty-key/spoken-wow.git refs/tags/spoken/v3.10.1
uv sync --locked
uv run --locked python tools/gossip_mapping_audit.py --classicua build/pinned-ClassicUA --spoken-390 build/pinned-spoken --spoken-3101 build/spoken-3.10.1
```

Add `--zip dist/Spoken_Gossip_UA_Local_Test.zip` to count entries in an existing ZIP and verify its sidecar checksum. The tool writes `build/gossip-mapping-summary.json` and `build/gossip-mapping-evidence.json`. The latter holds English wording, corpus indices, canonical IDs, source key and comment lines, layer paths, Git revisions, file fingerprints and translation fingerprints. Keep it private. The audit reads source and optional ZIP data directly, with no SQLite or translation workflow side effects.

## Coverage before and after

| Measure | Spoken 3.9.0 | Spoken 3.10.1 |
| --- | ---: | ---: |
| Raw Gossip corpus rows | 7,760 | 7,760 |
| Eligible creature rows | 7,599 | 7,599 |
| Excluded gameobject rows | 161 | 161 |
| Distinct NPC/hash pairs after collapsing eligible rows | 7,429 | 7,429 |
| Scoped exact NPC + original/hash | 3 | 3 |
| Exact original/hash via `!common` | 2,379 | 2,379 |
| Unmatched by either direct route | 5,047 | 5,047 |
| Unique normalized original English texts across all rows | 3,419 | 3,419 |
| Canonical Gossip IDs across all rows | 4,641 | 4,641 |
| Canonical IDs represented by at least one direct occurrence | 663 | 663 |

The historical counter groups by positive creature/vehicle NPC ID and ClassicUA hash, and allows corpus `text` when the original is absent. The audit reproduced **2,382 / 7,429 (32.1%)** with hash-verified source comments and matching normalized `originalText`. No pair needed the historical missing-original fallback. The 170 duplicate eligible rows collapse into existing pairs. The audit keeps all members, including Spoken's `g:<md5>:m` and `g:<md5>:f` IDs. ClassicUA hashes remain lookup keys. The corpus has 109 distinct voice values, 274 rows with a player-gender tag and 1,766 rows where `text` differs from `originalText`.

The audit verified 427/427 Gossip declarations against their English comments (375 Classic, 47 SoD and 5 Forever). All 427 are effective and serializable by the source lookup filter, comprising 100 NPC-scoped records and 327 common records. Only 216 source records win a direct Spoken occurrence lookup (3 scoped and 213 common). The inspected local ZIP independently contains 216 translation entries (3 NPC/hash and 213 common). All 216 match effective ClassicUA keys and translation fingerprints. The 26 effective dynamic patterns have separate provenance.

## Remaining unmatched NPC/wording pairs

The following categories are mutually exclusive and identical for both pins. Detailed evidence retains overlapping candidate routes.

| Testable reason | Pairs |
| --- | ---: |
| Spoken corpus `text` matches a scoped or common comment exactly after normalization, while `originalText` differs | 166 |
| Exact English overlap in ClassicUA Chat, without a Gossip lookup in scope | 8 |
| Exact Gossip wording exists under another NPC ID only | 4 |
| None of the audited routes returned a candidate | 4,868 |
| Same-context alternate original backed by a published Spoken alias | 0 |
| ClassicUA dynamic code pattern hit | 0 |
| ClassicUA reply-only article/period alternative | 0 |
| Audited glossary hit from a spell term | 1 |
| Missing original, numeric-hash collision or ambiguous NPC type within the historical denominator | 0 |
| **Total** | **5,047** |

The 166 alternate-field matches have exact text evidence. Their role as displayed English needs separate verification because Spoken exports prepared recording text independently of original wording. Spoken publishes 454 alias stems, which can represent shared BroadcastText/voice or merged recordings. The corpus carries zero explicit BroadcastText IDs and the alias artifact supplies stem links without numeric BroadcastText IDs or per-edge reasons. The audit checks same-NPC/type alias targets with independently stored originals and keeps links involving missing or localized stems in the raw alias artifact.

The cross-family scan covers verified chat comment originals from loaded declarations and explicit English keys/fields in the restricted ClassicUA dataset, plus the loaded `misc`, item and spell dictionaries. Chat hits are wording overlaps, including possible superseded declarations. Glossary checks cover these terms and audited object, zone, NPC and quest terms. Runtime-global strings, English bodies absent from source records, unexported BroadcastText data, and actual menu-option text are outside this denominator. Native replies have their own lookup path and require a separate context inventory before they can contribute any coverage claim. Exact source wording evidence does not establish an independent Stage 3 mapping, Ukrainian voice, or live-client acceptance.

## Recommended implementation PRs

1. Give the private Gossip editor the Quest-style write/paste and choose flows for one verified NPC/type and original at a time. Reuse a single selection across variants only when pinned evidence establishes their shared context. Keep the existing review decisions, drafts, provenance and imports intact in SQLite. Record newly saved text as a local selection ready for import. Keep existing approval meanings for older decisions and retain the legacy CLI and batch paths until compatibility is verified.
2. Add a separately invoked, checksum-verified incremental Gossip import for ready contexts. Preserve unrelated ZIP entries and decisions. Keep NPC overrides and common values distinct, with explicit validation before a shared edit affects other NPCs. Leave the full rebuild separate.
3. Audit native player replies, object contexts, current display wording and BroadcastText identity independently before expanding automatic reuse. This is the follow-up for the 166 prepared-text candidates and the coverage gaps across source families.
