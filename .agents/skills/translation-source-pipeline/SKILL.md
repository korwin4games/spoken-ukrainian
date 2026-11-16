---
name: translation-source-pipeline
description: Design, change, test or review Spoken Ukrainian's configurable ordered translation providers, sequential remaining-record resolution, English/client-language fallback choices, source provenance, or metadata-only coverage reports.
---

# Ordered translation source pipeline

## Start with the accepted contracts

1. Read `AGENTS.md`, `docs/TRANSLATION_SOURCE_CHAIN.md`, `docs/APPROVED_MODULES_AND_FALLBACK.md`, and `config/translation_sources.json`.
2. Inspect `adapters/translation_sources.py`, `adapters/spoken/text_index.py`, `tools/stage4_coverage.py`, `tests/test_translation_sources.py`, `tests/test_stage4_coverage.py`, `docs/STAGE_4A_INVENTORY_COVERAGE.md` and the canonical ID inventory interface (`docs/STAGE_3_IMPLEMENTATION.md`). Stage 4A now reads the real pinned public Spoken IDs and verified originals for Quests/Gossip/Readables, but remains offline and is **not** a completed ClassicUA join/pack pipeline; it is not wired into `tools/stage3_report.py` or the future pack builder.
3. Treat Stage 3's **0 reviewed real joins** as the baseline; target inventory size is not approved translation coverage. Stage 4B now makes a metadata-only Quest review queue but does **not** bind Ukrainian text into Stage 4A; see `docs/STAGE_4B_REVIEW_WORKBENCH.md`.

## Ordered matching behavior

- Config is an **ordered allow-list**, not merely a preference hint: arbitrary permutations/subsets, including English first or omitted, must be honored exactly. Reject duplicates, unknown providers, malformed/unknown-schema JSON, missing/blank files.
- Empty `sources: []` or `{}` means **actual WoW client language** from the caller, with zero provider calls. Do not hardcode `enUS`, read `GetLocale()` in Python, or spoof a WoW locale.
- Each provider receives only objects still without a **real Ukrainian candidate**. A result from `classicua` reserves the record for later independent review; `another` is a no-network stub, `own_translator` a non-publishable mock which **does not consume the record**.
- Explicit `original_english` assigns the remaining records to original English, then terminates resolution. Do not count those as Ukrainian translations; never add this provider when the config omits it.
- `resolve_translation` and `resolve_spoken_batch` must agree on **first real candidate wins**. An invalid/mock result must not select a source or prevent later lookups.
- If future independent review rejects a candidate, retry with a lower-priority source only after separately implementing an explicit review/retry workflow. **Not supported yet.**

## Identity, evidence and reporting

- For full indexed coverage, separate the **entire canonical inventory denominator** from the **verified-original eligible subset**; never invent original wording for Places/Bosses or ambiguous variants. All Stage 4A requests have `source_identity=None` until a separately attested source→target join is revalidated.
- Accept canonical Spoken IDs **only from an independently checked inventory**. Do not derive a canonical ID from Ukrainian text, a ClassicUA numeric Gossip hash, item ID, title or language name.
- Audit provenance: original source revision/file and SHA-256 separate from exact UTF-8 field text SHA-256. Reject mismatches, corrupt input or an unauthorized provider. File and field digests are not interchangeable.
- Keep content candidates as **pending**, never mark them approved or publishable. Separate source identity approval, translation/grammar/AI review, rights and runtime compatibility.
- A deterministic report must have **one row per unique canonical ID**, each with selected source/status and non-text fingerprint, plus per-source **new candidates**, **remaining for next source**, **mock skips**, **English selections**, and the **overall total**. Do not export source/translated text, secrets, or production API data.
- An approved-translation count stays **zero** until independent review supplies real approvals. Examples must be explicitly synthetic and give denominators.

## Verify

1. Use invented unit tests for permutations; English first/only/omitted, own mock first/only, empty policy with `deDE`, invalid configs, bad candidate hashes, missing providers and deterministic reports.
2. Check single-record vs batch equivalence; no unintended lower-priority calls after a real result; no actual translation/publication from mocks.
3. Run `python3 -m unittest discover -s tests -v`, `python3 tools/build.py` and `python3 tools/version.py check` when the required pinned test dependencies are present. Report CI evidence separately from local execution.
4. Confirm unchanged pinned repositories, `VERSION`, diagnostic package and README/architecture diagrams when relevant.

## Output

Report the configuration, per-provider candidate counts and unresolved remainder with a denominator, real approvals separately, test evidence and any blocked or future work. Never advertise offline fallback as a working in-game behavior.
