# Reviewed identity decisions

`example.synthetic.json` is a single invented metadata attestation for schema
version 1. It has **no real mapping approval** and must not be supplied as a
production review inventory. Its source/target references and reviewers are
explicitly invented. No translation body is stored.

`adapters.mapping.load_reviews()` rejects unknown schema fields, duplicate source
reviews and invalid review states. `assess_review()` checks each stored proof
against current source and target context; a stale/tampered record is invalidated.
Use `adapters.spoken.evidence.approve_review()` to create a review after two
independent reviewers have inspected the identity evidence. It requires exact
speaker/voice/wording/eligibility or owner/chain/checksum facts, explicit reference
hashes and an evidence reviewer distinct from the mapping approver.

See [review procedure](../docs/STAGE_3_IMPLEMENTATION.md). The foundational
`approve_mapping()` is a lower-level provenance primitive; it does not perform
this full contextual review and is not a reviewed-file ingestion path.
