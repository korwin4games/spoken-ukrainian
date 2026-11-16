"""Stage 4C foundation: audited Quest fields bound to *reviewed* canonical joins.

This module performs no automatic identity matching. Caller supplies:
- the exact Stage 2A audited Dataset plus its independently audited SourceInventory;
- the existing Stage 3 ReviewedMapping decisions, with independent JoinProof;
- the exact pinned public Spoken Inventory;
- a verified original-English text index from Stage 4A, in memory only.

Returned batch metadata NEVER treats discovered Ukrainian text as approved content.
"""
from dataclasses import replace
from hashlib import sha256

from adapters.classicua.evidence import SourceInventory, validate_source_unit
from adapters.crosswalk import QUEST_EVENTS
from adapters.mapping import assess_review, load_reviews, review_file
from adapters.translation_sources import (
    AlternativeSourceStub, ClassicUAProvider, EffectiveClassicUAField,
    OwnTranslatorMock, TranslationRequest, resolve_spoken_batch,
)


EVENT_POSITIONS = {event: position for position, event in QUEST_EVENTS.items()}


def _audited_quest_leaf(dataset, unit):
    parts = unit.source_id.split(":")
    if (len(parts) != 4 or parts[0] != "quest" or parts[1] not in ("horde", "alliance")
            or parts[3] not in EVENT_POSITIONS or not parts[2].isdecimal()):
        raise ValueError("reviewed_quest_identity_required")
    views, _ = dataset.faction_views(include_ai=True)
    row = views[parts[1]].get(int(parts[2]))
    leaf = row.fields.get((EVENT_POSITIONS[parts[3]],)) if row else None
    if (leaf is None or type(leaf.node.value) is not str or not leaf.node.value
            or sha256(leaf.node.value.encode("utf-8")).hexdigest() != unit.effective_sha256
            or (leaf.origin.revision, leaf.origin.file, leaf.origin.layer,
                leaf.origin.sha256) != (unit.source_revision, unit.origin_file,
                                        unit.origin_layer, unit.source_file_sha256)):
        raise ValueError("reviewed_quest_effective_field_mismatch")
    return leaf


def approved_quest_bindings(dataset, source: SourceInventory, inventory, reviews):
    """Bind only independently reviewed *identity* joins, never unsourced IDs."""
    if not isinstance(source, SourceInventory):
        raise ValueError("audited_classicua_source_inventory_required")
    if type(reviews) not in (list, tuple):
        raise ValueError("explicit_stage3_reviews_required")
    # This rejects forged review JSON and mismatched historical provenance.
    verified = load_reviews(review_file(reviews),
                            source_inventories={source.revision: source})
    evidence = {r.decision.source_id: r.decision.source_evidence_sha256
                for r in verified}
    bound_units = {k: replace(u, identity_evidence_sha256=evidence.get(k))
                   for k, u in source.units.items()}
    result = {}
    for review in verified:
        decision = review.decision
        unit = bound_units.get(decision.source_id)
        target = inventory.targets.get(decision.target_id)
        if unit is None or target is None or unit.family != "quest" or target.family != "quest":
            raise ValueError("reviewed_quest_target_required")
        validate_source_unit(unit, source) if unit.identity_evidence_sha256 is None else (
            validate_source_unit(replace(unit, identity_evidence_sha256=None), source))
        assessment = assess_review(review, bound_units, inventory,
                                   source_inventories={source.revision: source})
        if assessment["mapping_status"] != "approved":
            raise ValueError("stale_or_unapproved_canonical_identity_join")
        if decision.target_id in result:
            # Distinct Horde/Alliance source texts for one target require a
            # separate, explicit faction choice. Never choose arbitrarily.
            raise ValueError("multiple_reviewed_sources_for_one_target")
        leaf = _audited_quest_leaf(dataset, unit)
        result[decision.target_id] = (
            unit.source_id,
            EffectiveClassicUAField(leaf.node.value, unit.origin_file,
                                    unit.source_revision, unit.source_file_sha256,
                                    ai_marked=unit.ai),
        )
    return result


def reviewed_quest_batch(originals, dataset, source, inventory, reviews,
                         policy, client_locale=None):
    """Apply policy to verified original-English records, with reviewed ID joins.

    A found Ukrainian field is still only candidate_pending_review; no pack is
    generated, no source text is included in returned metadata and no approval
    is granted by finding a candidate.
    """
    if type(originals) is not dict or any(
            type(k) is not str or k not in inventory.targets
            or type(v) is not str or not v for k, v in originals.items()):
        raise ValueError("verified_original_index_required")
    bindings = approved_quest_bindings(dataset, source, inventory, reviews)
    if set(bindings) - set(originals):
        raise ValueError("approved_identity_lacks_verified_original")
    fields = {source_id: field for source_id, field in bindings.values()}
    if len(fields) != len(bindings):
        raise ValueError("ambiguous_reviewed_source_binding")
    targets_to_sources = {target_id: source_id
                          for target_id, (source_id, _) in bindings.items()}
    requests = [
        TranslationRequest(targets_to_sources.get(target_id), text,
                           target_id, client_locale)
        for target_id, text in sorted(originals.items())
    ]
    registry = {
        "classicua": ClassicUAProvider(fields),
        "another": AlternativeSourceStub(),
        "own_translator": OwnTranslatorMock(),
    }
    return resolve_spoken_batch(requests, policy, registry, inventory.targets)
