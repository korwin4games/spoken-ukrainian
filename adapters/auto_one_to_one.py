"""Opt-in local import of strictly unique *machine* Quest mappings.

This is separate from the Stage 3 human-reviewed identity ledger: a structural
1:1 match is not an independent JoinProof. Machine records stay in ignored build/
with explicit provisional status, never in Git, runtime packs or the approved
human-content import ledger.
"""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import re

from adapters.classicua.evidence import SourceInventory
from adapters.crosswalk import QUEST_EVENTS, digest
from adapters.import_summary import unique_one_to_one_hint_pairs
from adapters.local_review_store import LocalFile
from adapters.mapping import target_context
from adapters.translation_approvals import text_sha
from adapters.translation_sources import HEX64

EVENT_POSITION = {event: position for position, event in QUEST_EVENTS.items()}

FIELDS = frozenset({
    "id", "source_id", "target_id", "source_revision", "source_file",
    "source_layer", "source_file_sha256", "source_context_sha256",
    "target_context_sha256", "target_file_sha256", "original_sha256",
    "field_sha256", "text", "text_sha256", "decision",
})
DECISIONS = frozenset(("machine_1to1_provisional", "pending_update"))
EMPTY = {"schema_version": 1, "versions": [], "imports": []}
SOURCE_ID = re.compile(r"quest:(?:horde|alliance):[1-9][0-9]*:(?:accept|progress|complete)\Z")
TARGET_ID = re.compile(r"q:[1-9][0-9]*:(?:accept|progress|complete)(?::[a-z0-9_~-]+)?\Z")


def record_id(row):
    return digest({key: val for key, val in row.items() if key != "id"})


def validate_machine_ledger(data):
    if (type(data) is not dict or set(data) != set(EMPTY)
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or type(data["versions"]) is not list or type(data["imports"]) is not list):
        raise ValueError("invalid_machine_import_ledger_schema")
    seen, imported_targets = {}, set()
    for row in data["versions"]:
        if type(row) is not dict or set(row) != FIELDS:
            raise ValueError("invalid_machine_import_version")
        if (not SOURCE_ID.fullmatch(row["source_id"])
                or not TARGET_ID.fullmatch(row["target_id"])
                or row["decision"] not in DECISIONS
                or not re.fullmatch(r"[a-f0-9]{40}", row["source_revision"])
                or any(not isinstance(row[key], str) or not HEX64.fullmatch(row[key])
                       for key in ("source_file_sha256", "source_context_sha256",
                                   "target_context_sha256", "target_file_sha256",
                                   "original_sha256", "field_sha256", "text_sha256"))
                or type(row["source_file"]) is not str or not row["source_file"]
                or type(row["source_layer"]) is not str or not row["source_layer"]
                or type(row["text"]) is not str or not row["text"].strip()
                or len(row["text"]) > 60000
                or row["text_sha256"] != text_sha(row["text"])
                or row["text_sha256"] != row["field_sha256"]
                or row["id"] != record_id(row) or row["id"] in seen):
            raise ValueError("invalid_machine_import_provenance")
        seen[row["id"]] = row
    for ref in data["imports"]:
        if type(ref) is not dict or set(ref) != {"target_id", "version_id"}:
            raise ValueError("invalid_machine_import_reference")
        version = seen.get(ref["version_id"])
        if (version is None or version["target_id"] != ref["target_id"]
                or version["decision"] != "machine_1to1_provisional"
                or ref["target_id"] in imported_targets):
            raise ValueError("invalid_machine_import_reference")
        imported_targets.add(ref["target_id"])
    return deepcopy(data)


def machine_candidates(dataset, source, inventory, originals, hints):
    """Revalidate exact pinned source field, target context and original bytes.

    A unique numeric Quest ID/event only authorizes an explicitly marked
    *provisional machine import*. It is NEVER a Stage 3 reviewed mapping.
    """
    if not isinstance(source, SourceInventory):
        raise ValueError("audited_source_inventory_required")
    pairs = unique_one_to_one_hint_pairs(hints, source.units, inventory)
    views, _ = dataset.faction_views(include_ai=True)
    result = []
    for source_id, target_id in sorted(pairs):
        unit, target = source.units[source_id], inventory.targets[target_id]
        if (unit.family != "quest" or target.family != "quest"
                or unit.ai or not SOURCE_ID.fullmatch(source_id)
                or not TARGET_ID.fullmatch(target_id)):
            continue
        _, faction, quest_id, event = source_id.split(":")
        contexts = inventory.contexts.get(target_id, ())
        original = originals.original_english.get(target_id)
        if (len(contexts) != 1 or type(original) is not str or not original
                or not any(row.get("wording_sha256") == digest(original)
                           for row in contexts)):
            continue
        context = contexts[0]
        if (context.get("faction") not in (faction, "both", "neutral")
                or context.get("source") != event
                or context.get("quest_id") != int(quest_id)
                or not target_id.startswith(f"q:{quest_id}:{event}")):
            continue
        record = views[faction].get(int(quest_id))
        leaf = record.fields.get((EVENT_POSITION[event],)) if record else None
        if (leaf is None or type(leaf.node.value) is not str or not leaf.node.value.strip()
                or sha256(leaf.node.value.encode("utf-8")).hexdigest() != unit.effective_sha256
                or (leaf.origin.revision, leaf.origin.file, leaf.origin.layer,
                    leaf.origin.sha256) !=
                   (unit.source_revision, unit.origin_file, unit.origin_layer,
                    unit.source_file_sha256)
                or source.files.get(unit.origin_file) != unit.source_file_sha256):
            continue
        row = {
            "source_id": source_id, "target_id": target_id,
            "source_revision": unit.source_revision,
            "source_file": unit.origin_file, "source_layer": unit.origin_layer,
            "source_file_sha256": unit.source_file_sha256,
            "source_context_sha256": unit.context_sha256,
            "target_context_sha256": target_context(inventory, target_id),
            "target_file_sha256": target.evidence_sha256,
            "original_sha256": sha256(original.encode("utf-8")).hexdigest(),
            "field_sha256": unit.effective_sha256,
            "text": leaf.node.value, "text_sha256": text_sha(leaf.node.value),
            "decision": "machine_1to1_provisional",
        }
        row["id"] = record_id(row)
        result.append(row)
    return result


class MachineOneToOneStore:
    def __init__(self, path, allowed_directory):
        self.file = LocalFile(path, allowed_directory, EMPTY, validate_machine_ledger)

    def run(self, candidates, blocked_targets=()):
        """Only first-seen unique records auto-import; changed versions await review.

        History is never overwritten; old imports are invalidated when pinned
        evidence or source text changes. Existing human ledger always wins.
        """
        blocked_targets = set(blocked_targets)
        data = deepcopy(self.file.data)
        known = {row["id"]: row for row in data["versions"]}
        by_target = Counter(row["target_id"] for row in candidates)
        if len(known) != len(data["versions"]) or any(n > 1 for n in by_target.values()):
            raise ValueError("ambiguous_machine_one_to_one_candidates")
        imported = []
        new_count = 0
        for current in sorted(candidates, key=lambda item: (item["target_id"], item["id"])):
            if current["target_id"] in blocked_targets:
                continue
            existing = [r for r in data["versions"] if r["target_id"] == current["target_id"]]
            if current["id"] not in known:
                row = deepcopy(current)
                if existing:
                    row["decision"] = "pending_update"
                    row["id"] = record_id(row)
                else:
                    new_count += 1
                if row["id"] not in known:
                    data["versions"].append(row)
                    known[row["id"]] = row
            approved = known.get(current["id"])
            if (approved and approved["decision"] == "machine_1to1_provisional"
                    and len(existing) <= 1
                    and not any(r["decision"] == "pending_update" for r in existing)):
                imported.append({"target_id": current["target_id"],
                                 "version_id": current["id"]})
        data["versions"].sort(key=lambda row: (row["target_id"], row["id"]))
        data["imports"] = sorted(imported, key=lambda item: item["target_id"])
        validate_machine_ledger(data)
        changed = data != self.file.data
        self.file.save(data)
        return {"new_machine_1to1": new_count, "imported": len(imported),
                "changed": changed, "activated": False}

    def current_import_targets(self):
        return {entry["target_id"] for entry in self.file.data["imports"]}
