"""Stage 3 foundation: metadata-only effective units and reviewable ID decisions.

No translation is exported. A ClassicUA source key is NEVER a canonical Spoken ID.
Callers must supply independently verified canonical target evidence to map anything.
"""
from dataclasses import dataclass
import hashlib
import json
import re

QUEST_EVENTS = {2: "accept", 4: "progress", 5: "complete"}
TARGET_PATTERNS = {
    "quest": re.compile(r"q:[1-9][0-9]*:(?:accept|progress|complete)\Z"),
    "gossip": re.compile(r"g:[^\s]+\Z"),
    "readable": re.compile(r"b:[1-9][0-9]*\Z"),
}
FULL_SHA = re.compile(r"[a-f0-9]{64}\Z")


def digest(value):
    """Stable fingerprint, never a truncated/locale-dependent Python hash."""
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _nonempty_text(leaf):
    return type(leaf.node.value) is str and bool(leaf.node.value)


@dataclass(frozen=True)
class EffectiveUnit:
    source_id: str
    family: str
    effective_sha256: str
    grammar_sha256: str
    ai: bool
    source_revision: str
    source_file_sha256: str
    origin_file: str
    origin_layer: str
    identity_evidence_sha256: str | None = None

    def __post_init__(self):
        if self.family not in TARGET_PATTERNS:
            raise ValueError("Unsupported mapping family")
        for value in (self.effective_sha256, self.grammar_sha256, self.source_file_sha256):
            if not FULL_SHA.fullmatch(value):
                raise ValueError("Invalid SHA-256 evidence")
        if self.identity_evidence_sha256 is not None and not FULL_SHA.fullmatch(self.identity_evidence_sha256):
            raise ValueError("Invalid identity-evidence SHA-256")


def _make_unit(source_id, family, leaf, ai, evidence):
    # A stable identity must not depend on translation wording, origin line, or source revision.
    return EffectiveUnit(source_id, family,
                         hashlib.sha256(leaf.node.value.encode("utf-8")).hexdigest(),
                         digest([(x.category, x.status, x.detail, digest(x.syntax)) for x in leaf.grammar]),
                         bool(ai), leaf.origin.revision, leaf.origin.sha256,
                         leaf.origin.file, leaf.origin.layer, evidence.get(source_id))


def effective_units(dataset, identity_evidence=None):
    """Summarize already resolved Stage 2A records without serializing their text.

    Quest identity uses faction + ID + event (shared fallback is resolved by Dataset).
    Other family/row/page identifiers are opaque hashes: object names and lookup
    strings may themselves be copyrighted content. Gossip hashes do not become g: IDs;
    ClassicUA owner IDs do not become b: page IDs. Raw declarations are never counted.
    Source AI rows remain present and marked rather than silently becoming approved.
    """
    evidence = identity_evidence or {}
    result = {}

    def insert(source_id, family, leaf, ai):
        if source_id in result:
            raise ValueError("Duplicate effective source identity: " + source_id)
        result[source_id] = _make_unit(source_id, family, leaf, ai, evidence)

    views, _ = dataset.faction_views(include_ai=True)
    for faction, rows in sorted(views.items()):
        for key, record in sorted(rows.items()):
            if type(key) is not int or key <= 0:
                continue
            for position, event in QUEST_EVENTS.items():
                leaf = record.fields.get((position,))
                if leaf and _nonempty_text(leaf):
                    insert(f"quest:{faction}:{key}:{event}", "quest", leaf, record.ai)

    for category, family in (("gossip", "gossip"),
                             ("item_text", "readable"),
                             ("object_text", "readable")):
        for record in dataset.records.get(category, {}).values():
            if category == "gossip" and type(record.key) is not int:
                # !common is shared terminology, not an identified Spoken moment.
                continue
            for path, leaf in record.fields.items():
                if not _nonempty_text(leaf):
                    continue
                # Exclude !code metadata and non-page/nonnarratable shape fields.
                if category == "gossip" and (not path or type(path[0]) is not int):
                    continue
                if category == "item_text" and (not path or type(path[-1]) is not int):
                    continue
                if category == "object_text" and (not path or type(path[-1]) is not int):
                    continue
                source_id = family + ":" + digest([category, record.key, path])
                insert(source_id, family, leaf, record.ai)
    return dict(sorted(result.items()))


@dataclass(frozen=True)
class VerifiedTarget:
    canonical_id: str
    family: str
    spoken_revision: str
    evidence_ref: str
    evidence_sha256: str

    def __post_init__(self):
        pattern = TARGET_PATTERNS.get(self.family)
        if not pattern or not pattern.fullmatch(self.canonical_id):
            raise ValueError("Invalid canonical identity for family")
        if not self.spoken_revision or not self.evidence_ref or not FULL_SHA.fullmatch(self.evidence_sha256):
            raise ValueError("Pinned public target reference and evidence digest required")


@dataclass(frozen=True)
class MappingDecision:
    source_id: str
    target_id: str
    source_evidence_sha256: str
    target_evidence_sha256: str
    text_sha256: str
    review_by: str
    mapping_status: str = "approved"
    content_status: str = "pending"
    grammar_status: str = "pending"
    ai_status: str = "pending"

    def __post_init__(self):
        for code in (self.source_evidence_sha256, self.target_evidence_sha256, self.text_sha256):
            if not FULL_SHA.fullmatch(code):
                raise ValueError("Invalid SHA-256 mapping review input")
        if not self.review_by or self.mapping_status != "approved":
            raise ValueError("Mapping requires an explicit review attestation")
        for value in (self.content_status, self.grammar_status, self.ai_status):
            if value not in ("pending", "approved", "rejected"):
                raise ValueError("Review states must be independent and explicit")


def approve_mapping(unit, target_id, verified_targets, reviewer):
    """Approve a hand-evidenced crosswalk; never guess or mint a Spoken ID.

    verified_targets must be an independently authenticated canonical inventory
    from the pinned *public* Spoken source. This function cannot prove the
    inventory was collected correctly; that is a separate evidence review gate.
    """
    target = verified_targets.get(target_id)
    if target is None or not isinstance(target, VerifiedTarget):
        raise ValueError("Unverified or missing canonical Spoken target")
    if unit.family != target.family:
        raise ValueError("Cross-family mapping forbidden")
    if unit.identity_evidence_sha256 is None:
        raise ValueError("Source identity evidence absent: cannot approve mapping")
    if not reviewer or not reviewer.strip():
        raise ValueError("Reviewer is required")
    return MappingDecision(unit.source_id, target.canonical_id,
                           unit.identity_evidence_sha256, target.evidence_sha256,
                           unit.effective_sha256, reviewer.strip())


def compare_effective(old_units, new_units):
    """Deterministic effective diffs; file-only drift does not invalidate content."""
    result = []
    for key in sorted(set(old_units) | set(new_units)):
        old, new = old_units.get(key), new_units.get(key)
        if old is None:
            result.append({"source_id": key, "change": "added", "reasons": ["new_effective_unit"],
                           "mapping": "unresolved", "content_review": "required", "audio": "not_assessed"})
            continue
        if new is None:
            result.append({"source_id": key, "change": "removed", "reasons": ["effective_unit_removed"],
                           "mapping": "revalidate", "content_review": "required", "audio": "stale_if_present"})
            continue
        if old.family != new.family:
            raise ValueError("Same source identity changed family")
        reasons = []
        if old.effective_sha256 != new.effective_sha256:
            reasons.append("text_changed")
        if old.grammar_sha256 != new.grammar_sha256:
            reasons.append("grammar_changed")
        if (old.origin_file, old.origin_layer) != (new.origin_file, new.origin_layer):
            reasons.append("origin_changed")
        if old.ai != new.ai:
            reasons.append("ai_status_changed")
        if old.identity_evidence_sha256 != new.identity_evidence_sha256:
            reasons.append("identity_evidence_changed")
        identity = "identity_evidence_changed" in reasons
        content = any(x in reasons for x in ("text_changed", "grammar_changed", "origin_changed"))
        result.append({"source_id": key, "change": "modified" if reasons else "unchanged",
                       "reasons": reasons, "mapping": "revalidate" if identity else "retain_if_approved",
                       "content_review": "required" if content else "retain_if_approved",
                       "ai_review": "required" if "ai_status_changed" in reasons else "retain_if_approved",
                       "audio": "stale_if_present" if content else "unchanged"})
    return result


def metadata_report(old_units, new_units):
    """No translated bodies, raw gossip strings or object-name keys in JSON output."""
    diff = compare_effective(old_units, new_units)
    from collections import Counter
    return {"schema_version": 1, "scope": "effective source units only; not Spoken coverage or pack eligibility",
            "counts": dict(sorted(Counter(item["change"] for item in diff).items())),
            "units_old": len(old_units), "units_new": len(new_units),
            "diff": diff}


def metadata_json(report):
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
