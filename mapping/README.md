# Reviewed identity decisions

`example.synthetic.json` is a single invented metadata attestation for schema
version 1. It has **no real mapping approval** and must not be supplied as a
production review inventory. Its source/target references and reviewers are
explicitly invented. No translation body is stored.

`adapters.mapping.load_reviews(..., source_inventories=...)` requires independently
audited historical source inventories and rejects unknown schema fields, duplicate source
reviews and invalid review states. `assess_review()` checks each stored proof
against current source and target context; a stale/tampered record is invalidated.
Use `adapters.spoken.evidence.approve_review(..., source_inventory=...)` to create a review after two
independent reviewers have inspected the identity evidence. It requires exact
speaker/voice/wording/eligibility or owner/chain/checksum facts, explicit reference
hashes and an evidence reviewer distinct from the mapping approver.

See [review procedure](../docs/STAGE_3_IMPLEMENTATION.md). The foundational
`approve_mapping()` is a lower-level provenance primitive; it does not perform
this full contextual review and is not a reviewed-file ingestion path.

Source references must equal
`classicua:<full-revision>:<effective-file>#<effective-source-id>`. The source blob
hash and exact effective unit must match `adapters.classicua.evidence.from_audit()`
for a successful `audit_checkout()` result. Alternate artifacts are rejected.
Schema version 1 already retains the reviewed revision, file, field/context/text
hashes, grammar, AI and origin baseline; no migration or automatic completion of
old records occurs. The synthetic example has been regenerated from actual hashed
invented fixture bytes; it remains **synthetic**, with no real approval.
