"""Stage 4B metadata-only review queue over *audited* source and pinned target IDs.

No automatic join approvals: matching quest number/event is only a queue hint.
Manual reject/defer decisions never become a Stage 3 ReviewedMapping.
"""
from collections import Counter
from dataclasses import replace
from adapters.classicua.evidence import SourceInventory, source_reference
from adapters.mapping import load_reviews, review_file
from adapters.spoken.evidence import JoinProof, approve_review, proof_digest
from adapters.mapping import assess_review, candidates, target_context

DECISIONS = frozenset(("rejected", "deferred"))
REASONS = frozenset(("insufficient_evidence", "wrong_speaker", "faction_conflict",
                     "wording_mismatch", "wrong_event", "ambiguous_variant",
                     "source_not_applicable", "other"))
FACTS = ("npc_id", "npc_type", "voice", "faction", "player_gender",
         "wording_sha256", "source", "quest_id")
SOURCE_FAMILY = "quest"


# Rejections/deferments are decisions about an *audited evidence state*, not
# permanent bans on a numerical ID pair. Never replay a decision on new context.
DECISION_CONTEXT = (
    "source_revision", "source_file_sha256", "source_context_sha256",
    "source_field_sha256", "target_revision", "target_blob_sha256",
    "target_context_sha256",
)


def empty_decisions():
    return {"schema_version": 2, "decisions": []}


def candidate_evidence(hints, source, inventory):
    """Attach trusted exact pinned evidence to each eligible source/target pair."""
    if not isinstance(source, SourceInventory):
        raise ValueError("audited_source_inventory_required")
    result = {}
    for hint in hints:
        unit = source.units[hint["source_id"]]
        for target_id in hint["candidates"]:
            target = inventory.targets[target_id]
            result[(unit.source_id, target_id)] = {
                "source_revision": unit.source_revision,
                "source_file_sha256": unit.source_file_sha256,
                "source_context_sha256": unit.context_sha256,
                "source_field_sha256": unit.effective_sha256,
                "target_revision": target.spoken_revision,
                "target_blob_sha256": target.evidence_sha256,
                "target_context_sha256": target_context(inventory, target_id),
            }
    return result


def validate_decisions(data, hints, source, inventory):
    """Require explicit human decisions tied to exact current pinned evidence."""
    if (type(data) is not dict or set(data) != {"schema_version", "decisions"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 2
            or type(data["decisions"]) is not list):
        raise ValueError("invalid_workbench_decisions_schema")
    pairs = candidate_evidence(hints, source, inventory)
    seen, rows = set(), []
    for row in data["decisions"]:
        if (type(row) is not dict
                or set(row) != {"source_id", "target_id", "decision", "reviewer", "reason",
                                *DECISION_CONTEXT}):
            raise ValueError("invalid_workbench_decision_fields")
        # Validate value types before trying to use values as hash/set keys.
        if (type(row["source_id"]) is not str or type(row["target_id"]) is not str
                or type(row["decision"]) is not str or row["decision"] not in DECISIONS
                or type(row["reason"]) is not str or row["reason"] not in REASONS
                or type(row["reviewer"]) is not str or not row["reviewer"].strip()
                or len(row["reviewer"]) > 120
                or any(type(row[k]) is not str or not row[k] for k in DECISION_CONTEXT)):
            raise ValueError("invalid_or_duplicate_workbench_decision")
        key = (row["source_id"], row["target_id"])
        if key not in pairs or key in seen:
            raise ValueError("invalid_or_duplicate_workbench_decision")
        if any(row[k] != pairs[key][k] for k in DECISION_CONTEXT):
            raise ValueError("stale_workbench_decision_evidence")
        seen.add(key)
        rows.append(dict(row))
    return sorted(rows, key=lambda r: (r["source_id"], r["target_id"]))


def record_decision(data, hints, source, inventory, *, source_id, target_id,
                    decision, reviewer, reason):
    """Persist reject/defer with current audited provenance, never approval."""
    existing = validate_decisions(data, hints, source, inventory)
    if type(source_id) is not str or type(target_id) is not str:
        raise ValueError("invalid_or_duplicate_workbench_decision")
    evidence = candidate_evidence(hints, source, inventory).get((source_id, target_id))
    if evidence is None:
        raise ValueError("invalid_or_duplicate_workbench_decision")
    new = {"source_id": source_id, "target_id": target_id, "decision": decision,
           "reviewer": reviewer, "reason": reason, **evidence}
    return {"schema_version": 2,
            "decisions": validate_decisions({"schema_version": 2,
                                             "decisions": existing + [new]},
                                            hints, source, inventory)}


def build_workbench(source: SourceInventory, inventory, *,
                    decisions=None, reviews=(), limit=50, offset=0, faction=None):
    """Build deterministic queue with complete target-context metadata, not text."""
    if not isinstance(source, SourceInventory):
        raise ValueError("audited_source_inventory_required")
    if (type(limit) is not int or not 1 <= limit <= 100
            or type(offset) is not int or offset < 0
            or faction not in (None, "alliance", "horde")):
        raise ValueError("invalid_workbench_pagination_or_faction")
    hints = candidates(source.units, inventory)
    saved = validate_decisions(decisions if decisions is not None else empty_decisions(),
                               hints, source, inventory)
    decision_by_pair = {(r["source_id"], r["target_id"]): r for r in saved}

    # Replay Stage 3 reviews with independent, audited historical provenance.
    # A reviewer-supplied hash is not sufficient to establish an approval.
    source_inventories = {source.revision: source}
    evidence = {r.decision.source_id: r.decision.source_evidence_sha256 for r in reviews}
    reviewed_units = {k: replace(u, identity_evidence_sha256=evidence.get(k))
                      for k, u in source.units.items()}
    assessed = [assess_review(r, reviewed_units, inventory,
                              source_inventories=source_inventories)
                for r in reviews]
    approved_ids = {r["source_id"] for r in assessed if r["mapping_status"] == "approved"}
    if len(approved_ids) != sum(r["mapping_status"] == "approved" for r in assessed):
        raise ValueError("duplicate_approved_source_join")
    if any((r["source_id"], r["target_id"]) in decision_by_pair
           for r in assessed if r["mapping_status"] == "approved"):
        raise ValueError("conflicting_approved_and_manual_decision")

    counts = Counter()
    entries = []
    for hint in hints:
        unit = source.units[hint["source_id"]]
        if unit.family != SOURCE_FAMILY:
            continue
        if faction and not unit.source_id.startswith("quest:" + faction + ":"):
            continue
        counts["quest_source_units"] += 1
        if hint["source_id"] in approved_ids:
            counts["approved_identities_excluded_from_queue"] += 1
            continue
        if unit.ai:
            counts["ai_marked_excluded_from_queue"] += 1
            continue
        if not hint["candidates"]:
            counts["no_canonical_candidate"] += 1
            continue
        if hint["reason"] == "faction_eligibility_conflict":
            counts["faction_conflicts_excluded_from_queue"] += 1
            continue

        options = []
        for target_id in hint["candidates"]:
            decision = decision_by_pair.get((unit.source_id, target_id))
            if decision and decision["decision"] == "rejected":
                counts["rejected_candidate_pairs"] += 1
                continue
            target = inventory.targets[target_id]
            contexts = inventory.contexts[target_id]
            options.append({
                "target_id": target_id,
                "target_reference": target.evidence_ref,
                "target_blob_sha256": target.evidence_sha256,
                "target_context_sha256": target_context(inventory, target_id),
                "variants": [{k: context[k] for k in FACTS if k in context}
                             for context in contexts],
                "manual_decision": decision["decision"] if decision else "pending",
                "manual_reason": decision["reason"] if decision else None,
            })
        if not options:
            counts["fully_rejected_source_units"] += 1
            continue
        counts["queued_source_units"] += 1
        entries.append({
            "source_id": unit.source_id,
            "source_revision": unit.source_revision,
            "source_reference": source_reference(unit),
            "source_blob_sha256": unit.source_file_sha256,
            "source_context_sha256": unit.context_sha256,
            "field_sha256": unit.effective_sha256,
            "grammar_sha256": unit.grammar_sha256,
            "origin_layer": unit.origin_layer,
            "candidate_reason": hint["reason"],
            "status": "identity_review_required",
            "target_options": options,
            "required_review": [
                "independently_verify_quest_event_and_faction",
                "inspect_one_complete_speaker_voice_gender_wording_variant",
                "independently_inspect_pinned_source_and_target_references",
                "two_distinct_reviewers_and_validated_Stage3_JoinProof",
                "content_grammar_AI_rights_review_remains_separate",
            ],
        })

    entries.sort(key=lambda row: row["source_id"])
    rows = entries[offset:offset + limit]
    return {
        "schema_version": 1,
        "scope": "Stage 4B metadata-only human review workbench; NO automatic mappings",
        "source_revision": source.revision,
        "spoken_revision": inventory.revision,
        "family": SOURCE_FAMILY,
        "faction_filter": faction,
        "total_source_units_all_families": len(source.units),
        "total_spoken_identities_all_families": len(inventory.targets),
        "summary": {
            **{k: counts[k] for k in ("quest_source_units", "approved_identities_excluded_from_queue",
                                     "ai_marked_excluded_from_queue", "no_canonical_candidate",
                                     "faction_conflicts_excluded_from_queue", "rejected_candidate_pairs",
                                     "fully_rejected_source_units", "queued_source_units")},
            "human_stage3_approved_joins": len(approved_ids),
            "reviewed_joins_needing_revalidation": len(assessed) - len(approved_ids),
            "manual_decision_entries": len(saved),
            "page_count": len(rows),
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < len(entries),
            "translation_content_approvals_created": 0,
            "new_identity_approvals_created": 0,
        },
        "queue": rows,
    }


def approve_explicit_join(source: SourceInventory, inventory, request, *,
                          existing_reviews=(), decisions=None):
    """Explicit two-reviewer Stage 3 join gate; never synthesize a proof/attestation.

    Input is a *human-supplied*, individually inspected JoinProof with all
    source/target facts and pinned references, not a metadata candidate.
    Only identity approval is possible; content, grammar and AI remain pending.
    """
    if (type(request) is not dict
            or set(request) != {"schema_version", "source_id", "target_id",
                                "mapping_reviewer", "proof"}
            or type(request["schema_version"]) is not int
            or request["schema_version"] != 1
            or type(request["source_id"]) is not str
            or type(request["target_id"]) is not str
            or type(request["mapping_reviewer"]) is not str
            or not request["mapping_reviewer"].strip()
            or type(request["proof"]) is not dict):
        raise ValueError("explicit_human_join_request_required")
    source_id, target_id = request["source_id"], request["target_id"]
    source_unit = source.units.get(source_id)
    if source_unit is None or source_unit.family != "quest":
        raise ValueError("reviewed_quest_source_required")
    hints = candidates(source.units, inventory)
    if target_id not in next((row["candidates"] for row in hints
                              if row["source_id"] == source_id), ()):
        raise ValueError("candidate_target_reference_required")
    manual = validate_decisions(decisions if decisions is not None
                                else empty_decisions(), hints, source, inventory)
    if any((r["source_id"], r["target_id"], r["decision"])
           == (source_id, target_id, "rejected") for r in manual):
        raise ValueError("rejected_candidate_cannot_be_approved")
    if any(r.decision.source_id == source_id for r in existing_reviews):
        raise ValueError("existing_source_review_must_be_revalidated_not_overwritten")
    try:
        proof = JoinProof(**request["proof"])
    except (TypeError, KeyError):
        raise ValueError("invalid_explicit_join_proof_schema") from None
    unit = replace(source_unit, identity_evidence_sha256=proof_digest(proof))
    reviewed = approve_review(unit, target_id, inventory, proof,
                              request["mapping_reviewer"], source_inventory=source)
    assembled = review_file([*existing_reviews, reviewed])
    loaded = load_reviews(assembled, source_inventories={source.revision: source})
    # Independently reassess all persisted joins, including the newly approved
    # one, before producing any file.
    bound = {k: replace(u, identity_evidence_sha256=next(
                (r.decision.source_evidence_sha256 for r in loaded
                 if r.decision.source_id == k), None))
             for k, u in source.units.items()}
    if any(assess_review(r, bound, inventory,
                         source_inventories={source.revision: source}
                         )["mapping_status"] != "approved" for r in loaded):
        raise ValueError("approved_join_revalidation_failed")
    return assembled
