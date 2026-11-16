# Stage 4B — canonical Quest mapping review workbench

**Status:** Offline metadata-only workbench for *human* review of ClassicUA ↔ Spoken identities. A matching quest number and event means **candidate**, never an approved mapping. The tool does not translate, generate audio, modify upstream files, publish packs, or automatically bind Ukrainian text to Stage 4A.

## Inputs and candidate queue

Both source repositories must be clean, local and pinned to `sources.lock.json` and `tests/stage3_sources.json`. Stage 2A resolves effective ClassicUA data with actual `classic → sod → forever` load/override rules, and Stage 3 provides verified canonical Spoken target IDs. Existing `adapters.mapping.candidates()` generates conservative Quest ID/event hints; it never assumes matching names or hash values prove identity.

```sh
python3 tools/stage4b_workbench.py \
  --classicua /absolute/path/to/clean-pinned-ClassicUA \
  --spoken /absolute/path/to/clean-pinned-spoken-wow \
  --faction horde --limit 40
```

By default, the CLI displays at most **40 Horde Quest source units**, with options for `--faction alliance`, `--offset` and a limit of 1–100. It excludes AI-marked units, absent targets and obvious faction conflicts from the actionable queue, with distinct counts. Multiple voice/wording variants remain **separate target options**. The reviewer must compare one complete NPC/voice/faction/player-gender/wording variant against pinned references.

Output is a metadata-only `build/stage4b-review-queue.json` with source/target IDs, public references and SHA-256, source field digest, candidate options and required review checklist. Neither English nor Ukrainian text bodies leave the tool.

## Reject or defer

Only a real human should record a decision after inspecting pinned context. The following IDs and reviewer are **illustrative** and must be replaced with actual queue values:

```sh
python3 tools/stage4b_workbench.py \
  --classicua /absolute/path/to/clean-pinned-ClassicUA \
  --spoken /absolute/path/to/clean-pinned-spoken-wow \
  --source-id 'quest:horde:42:accept' \
  --target-id 'q:42:accept' \
  --decision rejected --reason wrong_speaker \
  --reviewer 'Actual reviewer identifier'
```

Use `--decision deferred --reason insufficient_evidence` to retain the candidate with a note. Decisions are written under ignored `build/stage4b-decisions.json`. The strict **schema version 2** binds each decision to exact audited ClassicUA/Spoken revisions, source field SHA-256, and source/target context/blob SHA-256. It rejects stale decisions after source/target evidence changes; re-review and record a fresh decision rather than silently migrating a version-1 file. It permits **only rejected/deferred**, requires real reviewer metadata and known reason codes, and rejects duplicate/unknown pairs and unexpected text/body fields. A manual decision file is never an identity approval.

## Independently attested Stage 3 approval

Identity approval requires a separate, human-authored `JoinProof` and **two distinct actual reviewers**. The evidence reviewer must examine the pinned source field and the exact target NPC/voice/faction/gender/wording context; the mapping reviewer independently attests the join. Numeric ID/event alone cannot prove the human comparison happened.

The local `--approve-request` JSON has this structure:

```json
{
  "schema_version": 1,
  "source_id": "<actual audited source_id>",
  "target_id": "<actual canonical target_id>",
  "mapping_reviewer": "<actual distinct mapping reviewer>",
  "proof": {
    "source_context_sha256": "<audited source context SHA-256>",
    "target_context_sha256": "<complete target context SHA-256>",
    "facts": {},
    "source_reference": "<audited ClassicUA file/field ref>",
    "source_blob_sha256": "<audited ClassicUA blob SHA-256>",
    "target_reference": "<pinned Spoken public ref>",
    "target_blob_sha256": "<pinned Spoken blob SHA-256>",
    "evidence_reviewer": "<actual evidence reviewer>",
    "greeting": false
  }
}
```

**This is a nonworking illustrative template, not real proof.** For a Quest, replace `facts` with exactly one independently checked target context containing `npc_id`, `npc_type`, `voice`, `faction`, `wording_sha256`, `source`, `quest_id`, and `player_gender`. All hashes/refs must come from the independently pinned audit and public inventory. The software validates internal consistency, but it cannot establish that humans actually examined an external reference.

```sh
python3 tools/stage4b_workbench.py \
  --classicua /absolute/path/to/clean-pinned-ClassicUA \
  --spoken /absolute/path/to/clean-pinned-spoken-wow \
  --approve-request /private/local/real-join-request.json \
  --reviews build/stage4b-reviewed-mappings.json
```

This invokes existing Stage 3 `approve_review()`, `load_reviews()` and `assess_review()`, then writes **only validated identity review metadata** under ignored `build/`. It rejects forged/stale provenance, wrong context, self-review, duplicated approvals and conflicts with a rejected pair. Approved identity does *not* approve text, grammar, AI output, licensing, narration or live display.

To inspect existing reviewed mappings, run with only `--reviews build/stage4b-reviewed-mappings.json`. Existing Stage 3 schema is reused, not forked.

## Acceptance and next step

The default CLI and CI do **not** manufacture reviewers, approval records or Ukrainian translations. Synthetic tests use explicitly invented evidence and reviewers. A production pilot begins with actual independently reviewed Quest source↔target proofs; until then, real approvals remain **zero**.

Stage 4B is **not connected to Stage 4A translation assignment yet**. Stage 4C will consume *approved* reviewed joins and audited effective ClassicUA text to populate the configurable provider chain, with candidate text/grammar/AI/rights review still separate. Gossip, Readables, Places and Bosses need independent evidence routes later; all runtime display restrictions documented by Stage 2B remain.

No source pins, project version, diagnostic archive, player code, releases or paid services change.
