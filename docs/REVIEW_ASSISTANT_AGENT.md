# Review assistant agent — proposal (not implemented)

This is a **design proposal**, not a new authenticated reviewer account or an
approval implementation. The current UI remains a local single-user tool.

## Goal

An optional helper may reduce the cost of manually reviewing thousands of
Spoken ↔ ClassicUA candidates. It must **never** count as either of the two
independent Stage 3 human reviewers or attest to text/rights checks it did not
perform. An LLM recommendation is not evidence of identity.

## Suggested workflow

1. The local review application generates a bounded **candidate summary**
   from already audited pinned context (canonical ID, source ID, event,
   verified English/UA context, variant, provenance). Only consented local
   text may be sent to an AI provider; by default it remains on device.
2. An agent may propose `possible_match`, `likely_mismatch`,
   `needs_human_review` and a short explanation, with optional suggested
   reviewer checklist and confidence. These are hints, not review decisions.
3. The user sees **Agent suggestion** in a separate read-only panel and can
   independently inspect files and accept or ignore the suggestion as context.
4. Evidence reviewer and mapping reviewer **independently** examine exact
   pinned originals and provide their own attestations. The existing Stage 3
   JoinProof gate remains unchanged.
5. Content reviewer separately checks text, grammar, AI restrictions and
   licensing before a content decision. Approval and import remain separate.

## Proposed identity model

- `reviewer_id`: a locally selected human label (current behavior).
- `assistant_agent_id`: stable tool/model identifier for **suggestions only**.
- `suggested_at`, `model_version`, `input_digest`, `summary_digest`,
  `source_revision`: explain where a suggestion came from.
- `suggestion_status`: `unreviewed` / `dismissed` / `considered`.
- No agent credential or role is authorized to submit `/api/mapping/approve`
  or `/api/translations/decide` on behalf of a human.

These are **future** schema ideas; do not change production review files until
the threat model and schema migration have been reviewed.

## Safety and implementation boundaries

- Default to local-only processing. No raw copyrighted source text is sent to
  cloud services without an explicit per-operation choice and rights review.
- Keep agent notes outside canonical approval ledgers; mark them untrusted.
- Do not automatically pre-check human attestation boxes, invent reviewer IDs,
  assume a particular NPC from translated names, or auto-approve anything.
- Persist only minimal suggested metadata under ignored `build/`, with
  source digests and explicit retention; protect against prompt injection in
  reviewed source text.
- Add deterministic synthetic tests before activating any assistant mode.

## Decision

Do not implement an agent login yet. First finish browser testing of the
form-based two-human workflow and decide whether the bottleneck is identifying
candidates, checking translation quality, or entering proof metadata. A
review-assistant role can then be scoped to the bottleneck without weakening
the established human approval gates.
