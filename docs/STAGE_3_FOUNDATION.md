# Stage 3 foundation — effective units, reviewed join contracts and semantic diffs

**Historical foundation record.** Current offline tooling, coverage and remaining independent-review gates are documented in [Stage 3 implementation](STAGE_3_IMPLEMENTATION.md). The limitations and results below describe the foundation commit, not the later implementation.

**Status at foundation commit: implemented foundation, NOT complete Stage 3.** Branch: `feat/stage3-canonical-mapping`. This document records what is implemented and validated, and what is expressly not. Follow [full Stage 3 task](STAGE_3_TASK.md), [Stage 3 specification](STAGE_3_SPECIFICATION.md), [architecture decision](ARCHITECTURE_UNMODIFIED_SPOKEN.md) and [Stage 2B limitations](STAGE_2B_COMPATIBILITY.md).

## Implemented

`adapters/crosswalk.py` builds metadata-only `EffectiveUnit` records from **already resolved** Stage 2A `Dataset` (not raw ClassicUA Lua and not an independently interpreted source):
- `quest:<faction>:<ID>:<accept|progress|complete>` units use existing `Dataset.faction_views()`, slots 2/4/5, whole-row replacement, AI flags and the actual origin of each field. Title/objective are excluded.
- Numeric-owner Gossip translated strings and item/object text page strings become **opaque hashed source identities**, not Spoken IDs. Shared `!common`, `!code` and numeric namesake `h1` metadata are excluded from this preliminary source-unit extraction.
- Includes SHA-256 of effective translated field bytes, separate grammar-finding digest, AI flag, provenance revision/file/layer and optional explicitly supplied identity evidence digest. No raw translation bodies, gossip wording or object titles are serialized.
- `VerifiedTarget`, `VerifiedJoin`, `MappingDecision`, `approve_mapping()` ensure review cannot occur from a syntactically valid target ID alone. Source and target public evidence, explicit source-to-target join proof and human reviewer are required. Quest numeric ID and event must agree. Mapping review and content/grammar/AI review statuses are distinct. **No real reviewed target or join inventory has been added**, and no real mapping is approved.
- `compare_effective()` classifies effective additions, removals, changed text, grammar changes, origin changes, AI changes and identity-evidence changes. Unrelated source-file SHA drift is not treated as an effective text edit. Content/grammar/origin changes mark downstream audio stale if audio exists, without minting or changing canonical IDs.
- `metadata_report()` / `metadata_json()` produce deterministic metadata-only results. This report is **source-unit impact, not mapped Spoken coverage**.

`tests/test_crosswalk.py` adds **16 synthetic tests**. Test corpus is invented; real ClassicUA translation bodies and real private/production data are not committed. Previously implemented adapter, diagnostic and Stage 2B runtime contracts are preserved.

## Verified checks

GitHub Actions for commit `94ae19648aec06046ab4f93d521d7d97f8e43dac`: [run 43888792821](https://github.com/korwin4games/spoken-ukrainian/actions/runs/43888792821) **successful**:

- `python3 tools/version.py check` → `0.0.1`
- `python3 tools/build.py` → unchanged 1651-byte ZIP; SHA-256 `5a2519858229c9aa004dbef075d1c8c51561e33f09828112504e0558005c8a8e`
- `python3 -m unittest discover -s tests -v` → **104 tests passed**, no failures.

Later documentation commits require their own CI status check; the evidence above refers only to the named code/test commit. Manual Forever acceptance is not implied.

## Explicit limitations — Stage 3 is NOT complete

1. **No actual canonical Spoken target index** yet for Quests, Gossip, Readables, Places or Bosses. The strict `VerifiedTarget` contract describes desired provenance but does not acquire or verify it.
2. **No actual reviewed ClassicUA → Spoken mapping**, voice/speaker/faction/owner/page-chain lookup, validated alias, or source-to-target identity-match evidence. Existence of both source and target in a fixture does not prove they are the same spoken moment.
3. Preliminary Gossip and Readables source-unit filters must be checked against actual pinned source shapes and runtime matching rules before declaring authoritative coverage or using the units in production.
4. `VerifiedTarget` currently models quest/gossip/readable target families; Places `z:/s:` and Bosses `boss:` inventory/crosswalk rules remain future work. ClassicUA zone terminology and NPC names are **not stories**.
5. No approved source-update check with **two independently pinned datasets**, reviewed mapping persistence/store, comprehensive impact report, CLI or mapping coverage denominator exists yet. Unit-level diff primitives are ready for integration.
6. No Ukrainian text-only Readables pack, Quest/Gossip translated captions, Bosses Ukrainian story display or audio has been enabled. Stage 2B player gates remain. Spoken Player and ClassicUA are unmodified.

## Next work package

Follow [docs/STAGE_3_TASK.md](STAGE_3_TASK.md) to build the **verified public Spoken canonical index and explicit match evidence** for each category; add real structural/parity tests with pinned public reference functions, mapping-review validation and metadata-only coverage reporting. Reject incomplete or ambiguous identities rather than inventing canonical IDs. Preserve all locks until an explicitly authorized update task.

Do not merge, bump project `VERSION`, publish packs, generate TTS or submit upstream player changes merely because the foundation tests pass.
