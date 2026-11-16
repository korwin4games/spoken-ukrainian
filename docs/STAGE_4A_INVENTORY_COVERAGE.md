# Stage 4A — pinned Spoken inventory → ordered source-coverage dry-run

**Scope:** first offline bridge from actual public Spoken canonical targets to the configurable source-priority resolver. **Not** a real Ukrainian localization, confirmed translation coverage, new reviewed ClassicUA joins, pack builder, live fallback, or TTS task.

## What is implemented

- Read a **clean, exact-revision** Spoken checkout through Stage 3 `PublicSource` and `build_index`. Every public reference is SHA-256 validated against `tests/stage3_sources.json`; its revision must match `sources.lock.json`.
- Independently extract original English text **in memory** from the pinned Quests/Gossip corpus and Readables pages. Accept only one unambiguous text whose deterministic wording digest occurs in the existing canonical target's evidence contexts.
- Traverse the *real* complete inventory of canonical Spoken IDs, preserving **all four module-family totals**. If an English original cannot be established from the public verified corpus, mark the target `public_original_not_verified` instead of fabricating a text or translating a different record.
- Pass eligible records to the **existing ordered** `resolve_spoken_batch`. Real `classicua` content is **deliberately unbound** because Stage 3 has **0 independently approved real source→target joins**. An indexed target ID is not a ClassicUA field ID. The pipeline therefore uses `TranslationRequest(source_identity=None, original_english=verified_text, canonical_spoken_id=...)`.
- Existing `another` stub and `own_translator` mock remain inert/non-publishable. Explicit `original_english` marks unclaimed eligible records as English-only; empty `sources: []` or `{}` selects the **caller-supplied actual client locale**, not necessarily English. All rules for subsets, ordering and omissions remain unchanged.
- Write deterministic **metadata-only** report under ignored `build/` with one row per public canonical identity, per-stage candidate/remaining totals and final totals by family. Never write source/translated wording bodies to JSON, Git, stdout or error messages.

**This is an intentional discovery-only bridge.** It does not yet connect the audited ClassicUA field text to approved canonical joins. Real fields must remain locked behind independent evidence verification; an automatic same-number/name match is not allowed. Future separately reviewed work may extend original-text indexing for Places/Bosses with the real pinned story references, and bind independently approved ClassicUA joins after revalidating historical and current provenance.

## Run

```sh
python3 tools/stage4_coverage.py \
  --spoken /absolute/path/to/clean-pinned-spoken-wow
```

Default policy is [`config/translation_sources.json`](../config/translation_sources.json). Output: `build/stage4-source-coverage.json`.

For explicit English-only selection:

```sh
python3 tools/stage4_coverage.py \
  --spoken /absolute/path/to/clean-pinned-spoken-wow \
  --policy config/examples/english-only.json
```

For an **empty** provider list:

```sh
python3 tools/stage4_coverage.py \
  --spoken /absolute/path/to/clean-pinned-spoken-wow \
  --policy config/examples/client-language.json \
  --client-locale deDE
```

The locale value is passed by the caller. This offline Python process **cannot detect the real WoW client locale**; using `deDE` above is only a demonstration. No `GetLocale()` spoofing is implemented. The CLI does not make network requests or write to the pinned source checkout.

## Report contract

| Field | Meaning |
| --- | --- |
| `coverage.total_spoken_identities` | All canonical target IDs in the pinned inventory, not a count of translations |
| `coverage.with_verified_public_original` | IDs with exactly one verified pinned English wording eligible for offline lookup |
| `coverage.without_verified_public_original` | Target IDs for which this stage cannot safely provide original wording |
| `coverage.translation_candidates_pending_review` | New Ukrainian candidates; currently 0 due to no independently approved source joins |
| `coverage.approved_translations` | Always 0 in this stage, independently of English choices |
| `coverage.without_approved_translation` | Total target identities, because no content has been approved |
| `coverage.original_english_selected` | Explicit English source assignments *among text-eligible IDs*, not working in-game fallback |
| `coverage.client_language_selected` | Text-eligible IDs assigned caller-supplied client locale under empty policy |
| `coverage.families` | Per-family total/with-original/no-original denominators |
| `stages` | Provider sequence: new candidates, mock skips, original-English selections, remaining after each pass, eligible total |
| `records` | Exactly one metadata-only row per canonical ID (including excluded IDs), stable sorted output |

The `stages[*].total` is the **eligible subset** (verified English originals), while `coverage.total_spoken_identities` is the **complete canonical inventory**. They are different denominators. No per-source English selection implies a live Places/Compendium subtitle fallback or guarantees a stored English voice.

## Safety and next gate

The Stage 3 source inventory contains tens of thousands of ClassicUA **unmapped candidate units**; its apparent key overlap does not prove a source→Spoken join. The present pipeline **must** report zero real Ukrainian translation approvals and no ClassicUA matches. Next:
1. Independently verify real source→target joins with the existing Stage 3 `JoinProof` and two-reviewer workflow, preserving file/field hashes and faction/voice/readable-chain context.
2. Only then bind the audited **effective ClassicUA field text** to a corresponding canonical Spoken ID. Handle competing faction/voice variants conservatively; do not auto-join.
3. Evaluate explicit review-rejected candidates with the next provider under a separately designed retry workflow.
4. Expand original-text intake for Places and Bosses only with verified public story text and rights.
5. Keep runtime display limitations per module from Stage 2B, human approval and license/attribution as independent release gates.

## Verification

Synthetic tests: `tests/test_stage4_coverage.py` check all canonical rows counted exactly once, original-context matching, ambiguous wording exclusion, source identity `None`, configurable English/empty policies, mock behavior, metadata-only outputs and no fake ClassicUA mapping. Run the full test suite and deterministic diagnostic build through the existing CI.

These tests do **not** constitute a full real-world input/output count or real Forever game acceptance. No upstream source revisions or `VERSION` are changed.

## First real pinned CI observation

GitHub Actions on the pinned Spoken revision `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7` (2026-11-16, Stage 4A run): **19,639** canonical IDs in total; **18,277** had exactly one verified public English original suitable for this offline lookup, and **1,362** did not.

| Family | Target IDs | Verified English originals | Without verified originals |
| --- | ---: | ---: | ---: |
| Quests | 12,594 | 12,498 | 96 |
| Gossip | 4,641 | 4,641 | 0 |
| Readables | 1,160 | 1,138 | 22 |
| Places | 947 | 0 | 947 |
| Bosses | 297 | 0 | 297 |
| **Total** | **19,639** | **18,277** | **1,362** |

With default policy, all eligible 18,277 entries selected **explicit Original English** and **0 Ukrainian candidates** were identified, as designed in the absence of approved canonical source joins. These are **verified-original indexing statistics**, not Ukrainian translation coverage. Source-only audit counts and the canonical ID denominator are intentionally different. For future source revisions, rerun the command rather than assuming these frozen counts remain current.

See [first real Stage 4A CI](https://github.com/korwin4games/spoken-ukrainian/actions/runs/43918214762) for the actual pinned-checkout run.
