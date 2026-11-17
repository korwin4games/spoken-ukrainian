---
name: classicua-adapter
description: Audit or modify Spoken Ukrainian's pinned ClassicUA source adapter, restricted Lua parser, TOC/XML load order, override resolver, provenance, grammar classification, or metadata-only inventory.
---

# ClassicUA source adapter workflow

## Read and locate
1. Read relevant parts of `docs/SOURCE_INTEGRATION.md`, `docs/STAGE_2A_IMPLEMENTATION.md`, `docs/STAGE_2A_TESTING.md`, and `docs/CLASSICUA_PERMISSION.md` (current permission); `docs/LEGAL_AND_ATTRIBUTION.md` is Stage 0 historical context.
2. Inspect `adapters/classicua/{lua,grammar,model,source}.py`, `tools/classicua_audit.py`, `tests/test_classicua.py` and `sources.lock.json` as needed.
3. Confirm the source checkout is clean and exactly at the pinned ClassicUA revision. The audit must not fetch, checkout, modify or execute ClassicUA source code.

## Preserve semantics
- Traverse `ClassicUA_Camelot.toc` and included XML in actual load order: `classic → sod → forever`, after common entries. Filesystem sorting is not precedence.
- Quests, NPC, item text, object text: later top-level keys replace **whole** rows. Missing/nil fields do not inherit. Empty Forever readables do not erase inherited rows.
- Gossip: per-hash or `!common` entry merge; supplied nested `!code` replaces the prior table as a value, not recursively.
- Resolve Alliance and Horde separately; faction-specific rows take precedence over shared entries; preserve AI-filter behavior and conflicts.
- Retain sparse quest slots: 1 title, 2 description, 3 objective, 4 progress, 5 completion. Do not interpret objective as voiced dialogue.
- Preserve namesake `h1` evidence, explicit nil, provenance, translation AI flags and unsupported grammar; classify tokens without expanding player data.
- No ClassicUA source key/hash is automatically a Spoken canonical ID. For validated Stage 3 joins use `.agents/skills/canonical-mapping-review/SKILL.md`; for ordered provider lookup use `.agents/skills/translation-source-pipeline/SKILL.md`.
- Keep source **file SHA-256** distinct from effective **field text SHA-256**; preserve origin and overridden-layer evidence. The source adapter does not by itself approve a translation for publication.

## Verify
1. Add small **invented** Lua fixtures and regression tests before changing parser or merge rules.
2. Run `uv run --locked python -m unittest discover -s tests -v` and `uv run --locked python tools/build.py`.
3. Optional pinned local audit: `uv run --locked python tools/classicua_audit.py --source /absolute/path/to/ClassicUA`. Inspect metadata-only reports in ignored `build/`; check deterministic output and provenance integrity. Do not copy source text into reports, console output or commits.
4. State raw vs effective counts, unresolved variants, unknown tokens and permission blockers. **Never** label source inventory as Spoken coverage.

## Output
Summarize changed files, tests, source revision (if audited), counts with denominators, unchanged diagnostic behavior and next mapping/rights blockers. Do not generate translated packs or audio.
