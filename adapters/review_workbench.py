"""Stage 4B metadata-only review queue over *audited* source and pinned target IDs.

No automatic join approvals: matching quest number/event is only a queue hint.
Manual reject/defer decisions never become a Stage 3 ReviewedMapping.
"""
from collections import Counter
from dataclasses import replace
from adapters.classicua.evidence import SourceInventory, source_reference
from adapters.crosswalk import SOURCE_PATTERNS
from adapters.mapping import assess_review, candidates, target_context

DECISIONS = frozenset(("rejected", "deferred"))
REASONS = frozenset(("insufficient_evidence", "wrong_speaker", "faction_conflict",
                     "wording_mismatch", "wrong_event", "ambiguous_variant",
                     "source_not_applicable", "other"))
FACTS = ("npc_id", "npc_type", "voice", "faction", "player_gender",
         "wording_sha256", "source", "quest_id")
SOURCE_FAMILY = "quest"


def empty_decisions():
    return {"schema_version": 1, "decisions": []}


def validate_decisions(data, hints):
    """Verify reviewer input against fresh candidate pairs; never trust a JSON ID."""
    if (type(data) is not dict or set(data) != {"schema_version", "decisions"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or type(data["decisions"]) is not list):
        raise ValueError("invalid_workbench_decisions_schema")
    pairs = {(r["source_id"], t) for r in hints for t in r["candidates"]}
    seen = set()
    rows = []
    for row in data["decisions"]:
        if type(row) is not dict or set(row) != {
                "source_id", "target_id", "decision", "reviewer", "reason"}:
            raise ValueError("invalid_workbench_decision_fields")
        key = (row["source_id"], row["target_id"])
        if (type(row["source_id"]) is not str or type(row["target_id"]) is not str
                or key not in pairs or key in seen
                or type(row["decision"]) is not str or row["decision"] not in DECISIONS
                or type(row["reason"]) is not str or row["reason"] not in REASONS
                or type(row["reviewer"]) is not str or not row["reviewer"].strip()
                or len(row["reviewer"]) > 120):
            raise ValueError("invalid_or_duplicate_workbench_decision")
        seen.add(key)
        rows.append(dict(row))
    return sorted(rows, key=lambda r: (r["source_id"], r["target_id"]))


def record_decision(data, hints, *, source_id, target_id, decision, reviewer, reason):
    """Create an explicit human reject/defer entry, never a mapping approval."""
    existing = validate_decisions(data, hints)
    new = {"source_id": source_id, "target_id": target_id, "decision": decision,
           "reviewer": reviewer, "reason": reason}
    return {"schema_version": 1,
            "decisions": validate_decisions({"schema_version": 1,
                                             "decisions": existing + [new]}, hints)}


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
    saved = validate_decisions(decisions if decisions is not None else empty_decisions(), hints)
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
