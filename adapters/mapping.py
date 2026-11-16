"""Versioned review attestations and deterministic candidate/impact reports.

Attestations are explicit human inputs, never inferred from ID syntax or titles.
This validates their consistency, not the truth of a human's external evidence.
"""
from collections import Counter
from dataclasses import asdict, dataclass, fields
import re

from adapters.crosswalk import (FULL_SHA, MappingDecision, TARGET_PATTERNS,
                                compare_effective, digest)

SOURCE_ID = re.compile(r'(?:quest:(?:alliance|horde):[1-9][0-9]*:(?:accept|progress|complete)|(?:gossip|readable):[a-f0-9]{64})\Z')


@dataclass(frozen=True)
class ReviewedMapping:
    decision: MappingDecision
    source_context_sha256: str
    target_context_sha256: str
    grammar_sha256: str
    ai: bool
    origin_file: str
    origin_layer: str
    evidence: dict

    def __post_init__(self):
        if not SOURCE_ID.fullmatch(self.decision.source_id):
            raise ValueError('invalid_source_identity')
        if not any(p.fullmatch(self.decision.target_id) for p in TARGET_PATTERNS.values()):
            raise ValueError('invalid_target_identity')
        for sha in (self.source_context_sha256, self.target_context_sha256, self.grammar_sha256):
            if not FULL_SHA.fullmatch(sha):
                raise ValueError('invalid_review_context_digest')
        if type(self.ai) is not bool:
            raise ValueError('invalid_review_ai_marker')


def review_file(records):
    """The only writable mapping schema; bodies and unknown fields are forbidden."""
    return {'schema_version': 1, 'decisions': [asdict(r) for r in sorted(records, key=lambda r: r.decision.source_id)]}


def load_reviews(data):
    if set(data) != {'schema_version', 'decisions'} or data['schema_version'] != 1:
        raise ValueError('unsupported_review_schema')
    result = []
    seen = set()
    try:
        for row in data['decisions']:
            if set(row) != {f.name for f in fields(ReviewedMapping)}:
                raise ValueError('unknown_review_field')
            decision = row['decision']
            if set(decision) != {f.name for f in fields(MappingDecision)}:
                raise ValueError('unknown_decision_field')
            r = ReviewedMapping(**(row | {'decision': MappingDecision(**decision)}))
            from adapters.spoken.evidence import JoinProof, REQUIRED
            proof = JoinProof(**r.evidence)
            family = r.decision.source_id.split(':')[0]
            if set(proof.facts) != REQUIRED[family]:
                raise ValueError('incomplete_identity_facts')
            if r.decision.source_id in seen:
                raise ValueError('duplicate_source_review')
            seen.add(r.decision.source_id)
            result.append(r)
    except (TypeError, KeyError):
        raise ValueError('malformed_review_record') from None
    return sorted(result, key=lambda r: r.decision.source_id)


def target_context(inventory, identity):
    return digest([inventory.contexts[identity], inventory.aliases.get(identity, [])])


def retain_review(decision, unit, inventory, evidence):
    """Persist the reviewed baseline, including content-independent identity context."""
    return ReviewedMapping(decision, unit.context_sha256,
                           target_context(inventory, decision.target_id), unit.grammar_sha256,
                           unit.ai, unit.origin_file, unit.origin_layer, evidence)


def assess_review(review, units, inventory):
    d = review.decision
    u = units.get(d.source_id)
    t = inventory.targets.get(d.target_id)
    reasons = []
    if u is None:
        reasons.append('source_removed')
    if t is None:
        reasons.append('target_unavailable')
    if u and t:
        if u.family != t.family:
            reasons.append('cross_family_join')
        if u.family == 'quest':
            parts = u.source_id.split(':')
            if t.canonical_id.split('~')[0].split(':')[:3] != ['q', parts[2], parts[3]]:
                reasons.append('quest_event_mismatch')
        if u.context_sha256 != review.source_context_sha256:
            reasons.append('source_context_changed')
        if u.identity_evidence_sha256 != d.source_evidence_sha256:
            reasons.append('source_join_evidence_changed')
        if (t.spoken_revision != d.target_revision or t.evidence_sha256 != d.target_evidence_sha256
                or target_context(inventory, t.canonical_id) != review.target_context_sha256):
            reasons.append('target_identity_context_changed')
    if u and t and not reasons:
        # Persisted JSON must pass the same contextual proof gate as a new approval.
        from adapters.spoken.evidence import JoinProof, approve_review
        try:
            proof = JoinProof(**review.evidence)
            if (d.join_evidence_sha256 != d.source_evidence_sha256
                    or d.join_evidence_ref != proof.source_reference):
                raise ValueError('stored_join_attestation_mismatch')
            approve_review(u, d.target_id, inventory, proof, d.review_by)
        except (ValueError, TypeError, KeyError, AttributeError):
            reasons.append('stored_join_proof_invalid')
    content = bool(u and u.effective_sha256 != d.text_sha256)
    grammar = bool(u and u.grammar_sha256 != review.grammar_sha256)
    origin = bool(u and (u.origin_file, u.origin_layer) != (review.origin_file, review.origin_layer))
    # Origin is content provenance; unrelated file-only drift retains prior reviews.
    ai = bool(u and u.ai != review.ai)
    return {'source_id': d.source_id, 'target_id': d.target_id,
            'mapping_status': 'invalidated' if reasons else 'approved', 'reasons': sorted(reasons),
            'content_status': 'pending' if content or origin or reasons else d.content_status,
            'grammar_status': 'pending' if content or grammar or origin or reasons else d.grammar_status,
            'ai_status': 'pending' if ai or content or reasons else d.ai_status,
            'audio': 'stale_if_present' if content or grammar or origin or reasons else 'not_assessed',
            'origin_changed': origin}


def candidates(units, inventory):
    """Conservative candidates: quest ID/event intersection is NOT approval.

    Gossip requires original moment/greeting proof; readable ordinal/owner alone
    cannot prove the server page chain. No fuzzy/name/title fallback is used.
    """
    quest_index = {}
    for identity, target in inventory.targets.items():
        if target.family == 'quest':
            base = ':'.join(identity.split('~')[0].split(':')[:3])
            quest_index.setdefault(base, []).append(identity)
    rows = []
    for key, unit in sorted(units.items()):
        hits = []
        reason = {'gossip': 'greeting_moment_voice_evidence_required',
                  'readable': 'owner_page_chain_checksum_evidence_required'}.get(unit.family)
        if unit.family == 'quest':
            _, faction, quest, event = key.split(':')
            hits = sorted(quest_index.get(f'q:{quest}:{event}', []))
            reason = 'target_unavailable' if not hits else 'speaker_wording_eligibility_review_required'
            if len(hits) > 1:
                reason = 'multiple_wording_or_voice_variants'
            if hits and all(all(c['faction'] not in (faction, 'both', 'neutral', 'unknown')
                                for c in inventory.contexts[h]) for h in hits):
                reason = 'faction_eligibility_conflict'
        rows.append({'source_id': key, 'candidates': hits,
                     'status': 'excluded' if unit.ai else 'ambiguous' if len(hits) > 1 else 'unresolved',
                     'reason': 'ai_independent_review_required' if unit.ai else reason})
    return rows


RUNTIME = {'quest': 'blocked_independent_ukUA_captions_on_enUS',
           'gossip': 'blocked_independent_ukUA_captions_on_enUS',
           'readable': 'blocked_text_only_audio_safety_and_enUS_compendium',
           'places': 'diagnostic_text_supported_separate_story_rights_required',
           'bosses': 'blocked_ukUA_story_selection_on_enUS'}


def coverage_report(units, inventory, reviews=(), old_units=None):
    assessed = [assess_review(r, units, inventory) for r in reviews]
    approved = {r['source_id']: r for r in assessed if r['mapping_status'] == 'approved'}
    rows = candidates(units, inventory)
    for row in rows:
        if row['source_id'] in approved:
            row.update(status='mapped', reason='reviewed_identity_join',
                       candidates=[approved[row['source_id']]['target_id']])
    families = {}
    for family in sorted(TARGET_PATTERNS):
        ids = {k for k, u in units.items() if u.family == family}
        mapped = [r for k, r in approved.items() if k in ids]
        families[family] = {
            'resolved_source_units': len(ids),
            'inventoried_target_units': sum(t.family == family for t in inventory.targets.values()),
            'approved_source_joins': len(mapped),
            'confirmed_unique_canonical_intersections': len({r['target_id'] for r in mapped}),
            'candidate_status_counts': dict(sorted(Counter(r['status'] for r in rows if r['source_id'] in ids).items())),
            'ai_marked_source_units': sum(units[k].ai for k in ids),
            'content_approved_source_joins': sum(r['content_status'] == 'approved' for r in mapped),
            'grammar_approved_source_joins': sum(r['grammar_status'] == 'approved' for r in mapped),
            'ai_approved_source_joins': sum(r['ai_status'] == 'approved' for r in mapped),
            'runtime_display': RUNTIME[family]}
    return {'schema_version': 1, 'scope': 'offline public identity inventory; no pack or runtime readiness',
            'spoken_revision': inventory.revision, 'public_files': inventory.files,
            'coverage': families, 'candidates': rows, 'reviews': sorted(assessed, key=lambda r: r['source_id']),
            'effective_diff': compare_effective(old_units, units) if old_units is not None else [],
            'source_provenance': {k: {'revision': u.source_revision, 'file_sha256': u.source_file_sha256,
                'origin_file': u.origin_file, 'origin_layer': u.origin_layer,
                'category': u.source_category, 'field_sha256': u.effective_sha256,
                'context_sha256': u.context_sha256, 'grammar_sha256': u.grammar_sha256,
                'ai': u.ai, 'identity_evidence_sha256': u.identity_evidence_sha256, 'predecessors': list(u.predecessors)} for k, u in sorted(units.items())},
            'non_story_categories': {'places': 'zone_terminology_only', 'bosses': 'no_source_stories'}}


def extraction_exclusions(dataset):
    """Explicit non-unit denominators, with no names, keys or source values."""
    counts = Counter()
    views, _ = dataset.faction_views(include_ai=True)
    for rows in views.values():
        for record in rows.values():
            for path, leaf in record.fields.items():
                if path not in ((2,), (4,), (5,)):
                    counts['quest_title_objective_or_metadata'] += 1
                elif type(leaf.node.value) is not str or not leaf.node.value:
                    counts['quest_empty_nil_or_nontext'] += 1
    for category in ('gossip', 'item_text', 'object_text'):
        for record in dataset.records.get(category, {}).values():
            for path, leaf in record.fields.items():
                if category == 'gossip':
                    if type(record.key) is not int or len(path) != 1 or type(path[0]) is not int:
                        counts['gossip_common_code_or_unsupported_shape'] += 1
                    elif type(leaf.node.value) is not str or not leaf.node.value:
                        counts['gossip_empty_nil_or_nontext'] += 1
                elif not path or any(type(k) is not int or k <= 0 for k in path):
                    counts['readable_h1_or_metadata'] += 1
                elif len(path) not in ((1,) if category == 'item_text' else (1, 2)):
                    counts['readable_unsupported_depth'] += 1
                elif type(leaf.node.value) is not str or not leaf.node.value:
                    counts['readable_empty_nil_or_nontext'] += 1
    counts['zone_terminology_not_lore_records'] = len(dataset.records.get('zone', {}))
    counts['npc_terminology_not_boss_story_records'] = len(dataset.records.get('npc', {}))
    return dict(sorted(counts.items()))
