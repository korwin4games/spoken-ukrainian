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
    "quest": re.compile(r"q:[1-9][0-9]*:(?:accept|progress|complete)(?::w[1-9][0-9]*)?(?::[mf])?(?:~[a-z0-9-]+)?\Z"),
    "gossip": re.compile(r"g:(?:[a-f0-9]{32}|b[1-9][0-9]*-[a-z0-9-]+|[a-z]{2}[A-Z]{2}-[a-f0-9]{32})(?::[mf])?(?:~[a-z0-9-]+)?\Z"),
    "places": re.compile(r"(?:z:[1-9][0-9]*|s:[1-9][0-9]*:[^\r\n:]+)\Z"),
    "bosses": re.compile(r"boss:[1-9][0-9]*:[^\r\n:]+\Z"),
    "readable": re.compile(r"b:(?:[1-9][0-9]*|n[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})\Z"),
}
SOURCE_PATTERNS = {
    "quest": re.compile(r"quest:(?:alliance|horde):[1-9][0-9]*:(?:accept|progress|complete)\Z"),
    **{family: re.compile(family + r":[a-f0-9]{64}\Z") for family in ("gossip", "readable")},
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
    context_sha256: str | None = None
    source_category: str = ""
    predecessors: tuple = ()

    def __post_init__(self):
        if self.family not in SOURCE_PATTERNS or not SOURCE_PATTERNS[self.family].fullmatch(self.source_id):
            raise ValueError("Invalid source mapping identity")
        for value in (self.effective_sha256, self.grammar_sha256, self.source_file_sha256):
            if not FULL_SHA.fullmatch(value):
                raise ValueError("Invalid SHA-256 evidence")
        if self.context_sha256 is not None and not FULL_SHA.fullmatch(self.context_sha256):
            raise ValueError("Invalid source context digest")
        if self.identity_evidence_sha256 is not None and not FULL_SHA.fullmatch(self.identity_evidence_sha256):
            raise ValueError("Invalid identity-evidence SHA-256")


def _make_unit(source_id, family, leaf, ai, evidence, record, context):
    # A stable identity must not depend on translation wording, origin line, or source revision.
    return EffectiveUnit(source_id, family,
                         hashlib.sha256(leaf.node.value.encode("utf-8")).hexdigest(),
                         digest([(x.category, x.status, x.detail, digest(x.syntax)) for x in leaf.grammar]),
                         bool(ai), leaf.origin.revision, leaf.origin.sha256,
                         leaf.origin.file, leaf.origin.layer, evidence.get(source_id),
                         digest(context), record.category,
                         tuple(sorted({(o.revision, o.file, o.layer, o.sha256)
                                       for o in leaf.predecessors + record.predecessors})))


def effective_units(dataset, identity_evidence=None, include_ai=True):
    """Summarize already resolved Stage 2A records without serializing their text.

    Quest identity uses faction + ID + event (shared fallback is resolved by Dataset).
    Other family/row/page identifiers are opaque hashes: object names and lookup
    strings may themselves be copyrighted content. Gossip hashes do not become g: IDs;
    ClassicUA owner IDs do not become b: page IDs. Raw declarations are never counted.
    Source AI rows remain present and marked rather than silently becoming approved.
    """
    evidence = identity_evidence or {}
    result = {}

    def insert(source_id, family, leaf, record, context):
        if source_id in result:
            raise ValueError("Duplicate effective source identity: " + source_id)
        result[source_id] = _make_unit(source_id, family, leaf, record.ai, evidence, record, context)

    views, _ = dataset.faction_views(include_ai=include_ai)
    for faction, rows in sorted(views.items()):
        for key, record in sorted(rows.items()):
            if type(key) is not int or key <= 0:
                continue
            for position, event in QUEST_EVENTS.items():
                leaf = record.fields.get((position,))
                if leaf and _nonempty_text(leaf):
                    insert(f"quest:{faction}:{key}:{event}", "quest", leaf, record, [record.category, key, event, faction,
                           digest(record.fields[("en",)].node.value) if ("en",) in record.fields else None])

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
                if category == "gossip" and (len(path) != 1 or type(path[0]) is not int):
                    continue
                if category == "item_text" and (len(path) != 1 or type(path[0]) is not int or path[0] <= 0):
                    continue
                if category == "object_text" and (len(path) not in (1, 2) or any(type(k) is not int or k <= 0 for k in path)):
                    continue
                source_id = family + ":" + digest([category, record.key, path])
                # Page positions and namesake h1 are identity context, never page IDs.
                chain = sorted([list(p) for p, f in record.fields.items()
                                if p and all(type(k) is int for k in p) and _nonempty_text(f)])
                h1 = sorted((digest(list(p)), digest(f.node.value)) for p, f in record.fields.items()
                            if p and p[-1] == "h1")
                insert(source_id, family, leaf, record,
                       [category, digest(record.key), list(path), chain if family == "readable" else [], h1])
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
class VerifiedJoin:
    """Reviewer-supplied evidence that *this* source unit matches *this* target.

    Verified source and target identities separately do not prove a join.
    The reference must point to independently inspected public identity evidence.
    """
    source_id: str
    target_id: str
    source_evidence_sha256: str
    target_evidence_sha256: str
    join_evidence_ref: str
    join_evidence_sha256: str

    def __post_init__(self):
        if not self.source_id or not self.target_id or not self.join_evidence_ref:
            raise ValueError("Explicit source-target join reference required")
        for sha in (self.source_evidence_sha256, self.target_evidence_sha256, self.join_evidence_sha256):
            if not FULL_SHA.fullmatch(sha):
                raise ValueError("Invalid reviewed join digest")


@dataclass(frozen=True)
class MappingDecision:
    source_id: str
    target_id: str
    source_evidence_sha256: str
    target_evidence_sha256: str
    join_evidence_sha256: str
    text_sha256: str
    source_revision: str
    source_file_sha256: str
    target_revision: str
    join_evidence_ref: str
    review_by: str
    mapping_status: str = "approved"
    content_status: str = "pending"
    grammar_status: str = "pending"
    ai_status: str = "pending"

    def __post_init__(self):
        for code in (self.source_evidence_sha256, self.target_evidence_sha256,
                     self.join_evidence_sha256, self.text_sha256, self.source_file_sha256):
            if not FULL_SHA.fullmatch(code):
                raise ValueError("Invalid SHA-256 mapping review input")
        if not self.source_revision or not self.target_revision or not self.join_evidence_ref:
            raise ValueError("Pinned provenance and join evidence reference required")
        if not self.review_by or self.mapping_status != "approved":
            raise ValueError("Mapping requires an explicit review attestation")
        for value in (self.content_status, self.grammar_status, self.ai_status):
            if value not in ("pending", "approved", "rejected"):
                raise ValueError("Review states must be independent and explicit")


def approve_mapping(unit, target_id, verified_targets, verified_joins, reviewer):
    """Approve only a reviewer-evidenced join to a pinned canonical inventory.

    Neither a source key, a canonical target's existence nor a similar title is
    sufficient. The independently inspected join reference is a human review
    gate: this function validates provenance consistency, not external truth.
    """
    target = verified_targets.get(target_id)
    if target is None or not isinstance(target, VerifiedTarget):
        raise ValueError("Unverified or missing canonical Spoken target")
    if unit.family != target.family:
        raise ValueError("Cross-family mapping forbidden")
    if unit.identity_evidence_sha256 is None:
        raise ValueError("Source identity evidence absent: cannot approve mapping")
    if unit.family == "quest":
        parts = unit.source_id.split(":")
        if len(parts) != 4 or parts[1] not in ("alliance", "horde") or target_id.split("~")[0].split(":")[:3] != ["q", parts[2], parts[3]]:
            raise ValueError("Quest ID/event must match canonical target")
    join = verified_joins.get((unit.source_id, target_id))
    if not isinstance(join, VerifiedJoin):
        raise ValueError("Verified source-target join evidence required")
    if ((join.source_id, join.target_id) != (unit.source_id, target_id)
            or join.source_evidence_sha256 != unit.identity_evidence_sha256
            or join.target_evidence_sha256 != target.evidence_sha256):
        raise ValueError("Stale or inconsistent source-target join evidence")
    if not reviewer or not reviewer.strip():
        raise ValueError("Reviewer is required")
    return MappingDecision(unit.source_id, target.canonical_id,
                           unit.identity_evidence_sha256, target.evidence_sha256,
                           join.join_evidence_sha256, unit.effective_sha256,
                           unit.source_revision, unit.source_file_sha256,
                           target.spoken_revision, join.join_evidence_ref, reviewer.strip())


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
        if old.context_sha256 != new.context_sha256:
            reasons.append("source_context_changed")
        identity = any(x in reasons for x in ("identity_evidence_changed", "source_context_changed"))
        content = any(x in reasons for x in ("text_changed", "grammar_changed", "origin_changed"))
        result.append({"source_id": key, "change": "modified" if reasons else "unchanged",
                       "reasons": reasons, "mapping": "revalidate" if identity else "retain_if_approved",
                       "content_review": "required" if content else "retain_if_approved",
                       "ai_review": "required" if "ai_status_changed" in reasons else "retain_if_approved",
                       "audio": "stale_if_present" if content or identity else "unchanged"})
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
