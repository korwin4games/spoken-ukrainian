# Stage 4C foundation — reviewed Quest identity → ClassicUA candidate

**Status:** synthetic-tested offline bridge, **not enabled in the production Stage 4A CLI**. There are still **0 independently reviewed real source→Spoken joins** in this repository, no approved translated text, no Ukrainian packs, no live fallback or TTS. Never claim otherwise based on this code's synthetic tests.

## Contract

New `adapters/reviewed_bridge.py` provides:

- `approved_quest_bindings(dataset, source_inventory, spoken_inventory, reviews)` — receives a fully **Stage 2A audited** effective ClassicUA Dataset, its matching immutable `SourceInventory`, an exactly pinned public Spoken inventory, and existing **Stage 3 `ReviewedMapping`** objects with independently attested `JoinProof`.
- Every review must pass `load_reviews()` against a trusted audited baseline, then `assess_review()` against the current public target context. Missing, stale, removed, wrong-family or conflicting mappings fail closed.
- For every identity-approved Quest source field, find the exact effective faction/event leaf at position 2/4/5, honoring `classic → sod → forever` and same-faction/shared override. Verify the **real UTF-8 text SHA-256** and origin revision, file, layer and file SHA-256 against the audited unit. Text stays in memory.
- If different audited source fields would map to one canonical target (e.g. Horde and Alliance voices/wording), refuse arbitrary selection until a separate explicit faction strategy is approved.
- `reviewed_quest_batch(originals, dataset, source, inventory, reviews, policy, client_locale)` receives **verified original-English records** from Stage 4A, makes `TranslationRequest` objects with a source ID *only for reviewed target IDs*, and calls the existing `resolve_spoken_batch()` in exact configured provider order.
- A ClassicUA result becomes **`candidate_pending_review`**, never an approved translation, pack or guaranteed in-game caption. `another` stays an offline stub, `own_translator` stays a non-publishable mock. Explicit English-only or empty client-locale policies keep their approved semantics.

## Important separation of counts

| State | What it proves |
| --- | --- |
| Canonical Spoken ID | Public identity exists; **not** a ClassicUA match |
| Stage 3 reviewed mapping | Independently attested *identity* join, still not approved wording |
| ClassicUA candidate | Audited Ukrainian field found for approved join; **needs content/grammar/AI/rights review** |
| Approved Ukrainian text | Not produced by this bridge, currently **0 real approvals** |
| Audio/runtime display | Separate Stage 2B and future Stage 5/6 gates |

This bridge never guesses a source ID from the target Quest number or translated text. A complete Stage 4A real-source run with **no approved Stage 3 mappings** still has zero Ukrainian candidates. Until a human supplies legitimate independent proofs, Stage 4C can only validate behavior using invented records/reviewers in tests.

## Synthetic tests

`tests/test_reviewed_bridge.py` exercises:
- valid *invented* two-reviewer Stage 3 identity approval → real effective-field hash verified → candidate only, **0 approved texts**;
- no reviews → explicit English fallback, no guessed binding;
- source priority English-first and mock-before-ClassicUA;
- stale/forged mapping evidence, altered target voice and tampered effective source text rejected;
- approved identity without verified original, invalid/unknown target inputs and metadata-only report behavior.

Run:

```sh
python3 -m unittest discover -s tests -v
```

## Next gate

1. Collect real Quest source+target evidence for a small, human-reviewed sample using `docs/STAGE_4B_REVIEW_WORKBENCH.md` and a second independent reviewer. Do not invent names or proofs.
2. Add an **explicit opt-in CLI path** using those actual reviewed mappings and both pinned source checkouts, preserving Stage 4A's complete-inventory reporting, exclusions, and its true client-locale behavior.
3. Independently verify Ukrainian text/grammar/AI/rights; only then consider a runtime-compatible text pack. The original Spoken Player must remain unmodified.

No unreviewed translations are exported to tracked files, log output or GitHub artifacts by this stage.
