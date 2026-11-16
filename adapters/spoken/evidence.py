"""Strict explicit identity proof validation; no translated-name or fuzzy joins."""
from dataclasses import asdict, dataclass
from adapters.crosswalk import FULL_SHA, VerifiedJoin, approve_mapping, digest
from adapters.mapping import retain_review, target_context

REQUIRED = {
    'quest': {'npc_id', 'npc_type', 'voice', 'faction', 'wording_sha256', 'source', 'quest_id', 'player_gender'},
    'gossip': {'npc_id', 'npc_type', 'voice', 'wording_sha256', 'source', 'player_gender'},
    'readable': {'book', 'number', 'chain', 'owners', 'checksum', 'wording_sha256'},
    'places': {'map_id', 'kind'},
    'bosses': {'map_id', 'creatures'},
}


@dataclass(frozen=True)
class JoinProof:
    source_context_sha256: str
    target_context_sha256: str
    facts: dict
    source_reference: str
    source_blob_sha256: str
    target_reference: str
    target_blob_sha256: str
    evidence_reviewer: str
    greeting: bool = False

    def __post_init__(self):
        for value in (self.source_context_sha256, self.target_context_sha256,
                      self.source_blob_sha256, self.target_blob_sha256):
            if type(value) is not str or not FULL_SHA.fullmatch(value):
                raise ValueError('invalid_join_proof_digest')
        if (type(self.facts) is not dict or type(self.greeting) is not bool
                or any(type(v) is not str or not v.strip() for v in
                       (self.source_reference, self.target_reference, self.evidence_reviewer))):
            raise ValueError('invalid_join_proof_metadata')


def approve_review(unit, target_id, inventory, proof, reviewer):
    """An independent reviewer must inspect the explicit source-to-target context.

    Reference hashes alone are not proof: required facts must match one whole
    target context, avoiding combinations of different speakers and voices.
    """
    target = inventory.targets.get(target_id)
    if target is None:
        raise ValueError('target_unavailable')
    if not isinstance(proof, JoinProof):
        raise ValueError('explicit_join_proof_required')
    if (not proof.evidence_reviewer.strip() or proof.evidence_reviewer.strip() == reviewer.strip()
            or not proof.source_reference or proof.target_reference != target.evidence_ref
            or proof.target_blob_sha256 != target.evidence_sha256
            or not FULL_SHA.fullmatch(proof.source_blob_sha256)):
        raise ValueError('independent_reference_review_required')
    if unit.context_sha256 != proof.source_context_sha256:
        raise ValueError('source_context_mismatch')
    if target_context(inventory, target_id) != proof.target_context_sha256:
        raise ValueError('target_context_mismatch')
    required = REQUIRED[unit.family]
    if set(proof.facts) != required:
        raise ValueError('incomplete_identity_facts')
    if not any(all(c.get(k) == v for k, v in proof.facts.items()) for c in inventory.contexts[target_id]):
        raise ValueError('speaker_voice_owner_chain_or_wording_mismatch')
    if unit.family == 'quest':
        faction = unit.source_id.split(':')[1]
        if proof.facts['faction'] not in (faction, 'both', 'neutral'):
            raise ValueError('unverified_faction_eligibility')
    if unit.family == 'gossip' and not proof.greeting:
        raise ValueError('gossip_option_or_unverified_greeting')
    # These categories are terminology/no source stories; never claim translated lore.
    if unit.family in ('places', 'bosses'):
        raise ValueError('classicua_has_no_story_source')
    join_sha = digest([proof.source_context_sha256, proof.target_context_sha256,
                       proof.facts, proof.source_reference, proof.source_blob_sha256,
                       proof.target_reference, proof.target_blob_sha256,
                       proof.evidence_reviewer, proof.greeting])
    if unit.identity_evidence_sha256 != join_sha:
        raise ValueError('source_evidence_not_bound_to_join_proof')
    join = VerifiedJoin(unit.source_id, target_id, join_sha, target.evidence_sha256,
                        proof.source_reference, join_sha)
    decision = approve_mapping(unit, target_id, inventory.targets,
                               {(unit.source_id, target_id): join}, reviewer)
    return retain_review(decision, unit, inventory, asdict(proof))


def proof_digest(proof):
    return digest([proof.source_context_sha256, proof.target_context_sha256,
                   proof.facts, proof.source_reference, proof.source_blob_sha256,
                   proof.target_reference, proof.target_blob_sha256,
                   proof.evidence_reviewer, proof.greeting])
