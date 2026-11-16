---
name: canonical-mapping-review
description: Work on Stage 3 source-to-canonical-Spoken ID crosswalks, independently reviewed join evidence, source and target provenance, mapping persistence, effective-source diffs, review invalidation, and real versus candidate coverage.
---

# Evidence-gated canonical mapping review

## Orient to the pinned evidence

1. Read `AGENTS.md`, `docs/STAGE_3_SPECIFICATION.md`, `docs/STAGE_3_IMPLEMENTATION.md`, `docs/CLASSICUA_PERMISSION.md`, and the relevant `docs/COMPATIBILITY_MATRIX.md` module sections.
2. Inspect `adapters/crosswalk.py`, `adapters/mapping.py`, `adapters/spoken/evidence.py`, `adapters/review_workbench.py`, `tools/stage4b_workbench.py`, `docs/STAGE_4B_REVIEW_WORKBENCH.md`, source provenance code, and `tests/test_crosswalk.py` / `tests/test_stage3.py` / `tests/test_review_workbench.py`.
3. Use exact pinned Spoken and ClassicUA commits, supplemental public evidence manifests and clean local checkouts. Do not alter upstream, run untrusted Lua, call private APIs or advance pins silently.

## Identity is not translation

- The **target canonical Spoken ID already exists**; never mint one from a translated title, name, source hash or client locale. Inventory of 25,983 candidate source units and canonical IDs is **not** verified coverage; the currently approved real joins are **zero**.
- Quests: require exact quest ID/event, faction eligibility, original wording, player gender, speaker/voice and variant context; never infer eligibility from source filename or reuse a different voice's speaker.
- Gossip: prove NPC/object, **greeting vs menu option**, original moment and voice. Numeric ClassicUA hashes and Spoken `g:` IDs use different algorithms; known aliases do not justify guesswork.
- Readables: require book/owner, original first page, exact ordered/sparse chain and per-page canonical `b:` ID. Item ID, title and page ordinal are not pageText IDs.
- Places and Bosses: preserve existing `z:`, `s:` or `boss:` target references, but ClassicUA terminology is **not** authored zone lore or boss stories.

## Candidate review queue

- Use Stage 4B for **Quest ID/event candidate hints only** (default 40 Horde units); ensure metadata-only sorted output, no AI-marked automatic proposals, separate voice variants, faction conflicts, and strict pagination.
- Manual decisions in `build/stage4b-decisions.json` are **rejected/deferred only** and must be validated against an actual pinned candidate pair. Do not call them approved mappings.
- Promotion requires a separately supplied explicit `JoinProof` and two distinct real human reviewers. `approve_explicit_join` must re-run existing Stage 3 `approve_review`, `load_reviews` and `assess_review`; never fabricate reviewer identities or treat test fixtures as actual approvals.

## Approval gates and updates

- A **source evidence reviewer** must independently attest source-to-target context; a distinct **mapping reviewer** approves the join. The proof gate validates internal evidence consistency; it cannot magically prove human attestation is true.
- Verify pinned source revision/file SHA and effective **field SHA** against actual source evidence; bind target public reference and contextual facts to one complete target context. Wrong/missing evidence, ambiguous matches and unknown source ownership remain unapproved.
- Keep **identity approval** separate from text, grammar, AI-marker, attribution/rights and sound/pack readiness. Never auto-approve a real join just because an index lookup returned a candidate.
- When **effective translated text** changes but identity context stays valid, preserve mapping ID, reset dependent content/grammar review, and flag affected recordings for re-review. **Source-file-only drift** or line movement with unchanged effective content does not invalidate a mapping. Speaker/voice/owner/page chain/target identity changes require identity review.
- After translation removal or conflict, report unresolved eligibility/fallback honestly; no dummy English/translated content, no fake audio, no automatic publication or update.

## Test and report

1. Add small **synthetic** fixtures for positive and negative provenance, cross-family/variant ambiguity, rejected joins, update diff stability, and saved-review corruption.
2. Run the relevant `tests/test_crosswalk.py` and `tests/test_stage3.py`, then full `python3 -m unittest discover -s tests -v` where prerequisites are installed.
3. Report the distinct denominators: source candidates, target inventory, real independently reviewed intersections, unknown/missing, approval states and blocked runtime surfaces. Use zero where no approvals exist; never substitute target-count for coverage.
4. Record exact pinned revisions, files changed, CI/local test evidence and remaining independent human review or module compatibility blockers.

Do not generate translated packs, story bodies, TTS, releases, or an automatic updater from a mapping-review task.
