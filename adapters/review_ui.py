"""Local-only Quest review presentation over existing audited Stage 4B evidence.

Uncommitted text bodies stay in memory and in local HTTP responses; they are
never placed in tracked files, metadata reports, logs or approval decisions.
The UI may *reject* or *defer* source/target candidate pairs; it cannot approve
an identity or translated content. Real identity approval is the separate
two-reviewer Stage 3 JoinProof workflow.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
import tempfile

from adapters.classicua.evidence import SourceInventory
from adapters.crosswalk import QUEST_EVENTS
from adapters.mapping import candidates
from adapters.review_workbench import (build_workbench, empty_decisions,
                                       record_decision, validate_decisions)
from adapters.spoken.text_index import TextIndex


EVENT_POSITION = {event: position for position, event in QUEST_EVENTS.items()}
FACTIONS = frozenset(("horde", "alliance"))


def guarded_decisions_path(path, allowed_directory):
    """No out-of-build or symlink redirects to repository or pinned inputs."""
    path = Path(path)
    allowed = Path(allowed_directory).resolve()
    resolved = path.resolve()
    if (resolved == allowed or not resolved.is_relative_to(allowed)
            or not path.absolute().is_relative_to(allowed)):
        raise ValueError("review_ui_decisions_must_be_under_build")
    return resolved


@dataclass
class LocalReviewState:
    dataset: object
    source: SourceInventory
    inventory: object
    original_index: TextIndex
    decisions_file: Path
    allowed_directory: Path
    reviews: tuple = ()

    def __post_init__(self):
        if not isinstance(self.source, SourceInventory):
            raise ValueError("audited_source_inventory_required")
        if not isinstance(self.original_index, TextIndex):
            raise ValueError("verified_spoken_original_index_required")
        self.decisions_file = guarded_decisions_path(
            self.decisions_file, self.allowed_directory)
        self._views, _ = self.dataset.faction_views(include_ai=True)
        self._hints = candidates(self.source.units, self.inventory)
        self._lock = RLock()
        if self.decisions_file.is_file():
            saved = json.loads(self.decisions_file.read_text(encoding="utf-8"))
        else:
            saved = empty_decisions()
        self.decisions = {"schema_version": 2, "decisions": validate_decisions(
            saved, self._hints, self.source, self.inventory)}

    def _ukrainian_text(self, identity):
        """Read only the already-audited effective faction/event text."""
        unit = self.source.units.get(identity)
        if unit is None or unit.family != "quest" or unit.ai:
            raise ValueError("valid_non_ai_quest_required")
        prefix, faction, quest_id, event = identity.split(":")
        if prefix != "quest" or faction not in FACTIONS or event not in EVENT_POSITION:
            raise ValueError("invalid_review_source_identity")
        record = self._views[faction].get(int(quest_id))
        field = record.fields.get((EVENT_POSITION[event],)) if record else None
        if field is None or type(field.node.value) is not str:
            raise ValueError("effective_quest_text_unavailable")
        if (sha256(field.node.value.encode("utf-8")).hexdigest() != unit.effective_sha256
                or (field.origin.revision, field.origin.file, field.origin.layer,
                    field.origin.sha256) !=
                (unit.source_revision, unit.origin_file, unit.origin_layer,
                 unit.source_file_sha256)):
            raise ValueError("effective_quest_source_fingerprint_mismatch")
        return field.node.value

    def page(self, faction="horde", offset=0, limit=12):
        if (faction not in FACTIONS or type(offset) is not int or offset < 0
                or type(limit) is not int or limit < 1 or limit > 40):
            raise ValueError("invalid_review_ui_page")
        with self._lock:
            report = build_workbench(
                self.source, self.inventory, decisions=self.decisions,
                reviews=self.reviews, faction=faction, offset=offset, limit=limit)
            items = []
            for item in report["queue"]:
                variants = []
                for option in item["target_options"]:
                    original = self.original_index.original_english.get(option["target_id"])
                    variants.append({
                        **option,
                        # None means no verified unique English original. Never
                        # substitute text from a different variant or locale.
                        "english_original": original,
                        "english_verified": original is not None,
                    })
                items.append({
                    **item,
                    "ukrainian_text": self._ukrainian_text(item["source_id"]),
                    "target_options": variants,
                })
            return {
                "schema_version": 1,
                "scope": "local_review_only_no_approval",
                "faction": faction,
                "offset": offset,
                "limit": limit,
                "summary": report["summary"],
                "source_revision": self.source.revision,
                "spoken_revision": self.inventory.revision,
                "items": items,
            }

    def decide(self, source_id, target_id, decision, reason, reviewer):
        with self._lock:
            updated = record_decision(
                self.decisions, self._hints, self.source, self.inventory,
                source_id=source_id, target_id=target_id,
                decision=decision, reason=reason, reviewer=reviewer)
            content = json.dumps(updated, ensure_ascii=False,
                                 sort_keys=True, indent=2) + "\n"
            self.decisions_file.parent.mkdir(parents=True, exist_ok=True)
            # Never write source/target text to disk. Atomic replace protects
            # the review ledger against partial writes.
            name = None
            try:
                with tempfile.NamedTemporaryFile(
                    "w", encoding="utf-8", dir=self.decisions_file.parent,
                    prefix=".stage4b-decision-", delete=False
                ) as handle:
                    name = handle.name
                    os.chmod(name, 0o600)
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(name, self.decisions_file)
            finally:
                if name and os.path.exists(name):
                    os.unlink(name)
            self.decisions = updated
            return {
                "source_id": source_id, "target_id": target_id,
                "decision": decision, "reason": reason,
                "saved": True, "identity_approved": False,
                "translation_approved": False,
            }
