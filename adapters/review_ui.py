"""Local-only Quest review presentation over existing audited Stage 4B evidence.

Mapping approvals require an independently supplied Stage 3 JoinProof.
Content reviews and inert imports use a separate private, ignored local ledger;
no text bodies enter tracked files, metadata reports, logs, or runtime packs.
"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock

from adapters.classicua.evidence import SourceInventory
from adapters.crosswalk import QUEST_EVENTS, digest
from adapters.mapping import candidates, load_reviews, review_file, target_context
from adapters.review_workbench import (approve_explicit_join, build_workbench,
                                       empty_decisions, record_decision, validate_decisions)
from adapters.spoken.text_index import TextIndex
from adapters.local_review_store import LocalFile, strict_json
from adapters.import_summary import import_summary, unique_one_to_one_hint_pairs
from adapters.reviewed_bridge import approved_quest_bindings
from adapters.translation_approvals import ReviewCandidate, TranslationApprovals
from adapters.translation_sources import (AlternativeSourceStub, ClassicUAProvider,
    OwnTranslatorMock, SourcePolicy, TranslationRequest, discover_review_candidates)


EVENT_POSITION = {event: position for position, event in QUEST_EVENTS.items()}
FACTIONS = frozenset(("horde", "alliance"))


def guarded_decisions_path(path, allowed_directory):
    """No out-of-build or symlink redirects to repository or pinned inputs."""
    path = Path(path)
    allowed = Path(allowed_directory).resolve()
    resolved = path.resolve()
    if (resolved == allowed or not resolved.is_relative_to(allowed)
            or not path.absolute().is_relative_to(allowed)
            or any(p.is_symlink() for p in (path.absolute(), *path.absolute().parents))):
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
    reviews_file: Path | None = None
    translations_file: Path | None = None
    policy: SourcePolicy = SourcePolicy(("classicua", "another", "own_translator", "original_english"))
    reviews_input_file: Path | None = None
    revalidate_inputs: object = None

    def __post_init__(self):
        if not isinstance(self.source, SourceInventory):
            raise ValueError("audited_source_inventory_required")
        if not isinstance(self.original_index, TextIndex):
            raise ValueError("verified_spoken_original_index_required")
        self.decisions_file = guarded_decisions_path(
            self.decisions_file, self.allowed_directory)
        # Defense-in-depth: the caller may only display text whose digest
        # belongs to the exact pinned canonical Spoken target context.
        for identity, text in self.original_index.original_english.items():
            if (type(identity) is not str or type(text) is not str
                    or identity not in self.inventory.targets
                    or not any(row.get("wording_sha256") == digest(text)
                               for row in self.inventory.contexts.get(identity, ()))):
                raise ValueError("unverified_spoken_original_text")
        self._views, _ = self.dataset.faction_views(include_ai=True)
        self._hints = candidates(self.source.units, self.inventory)
        self._lock = RLock()
        self._decisions_store = LocalFile(
            self.decisions_file, self.allowed_directory, empty_decisions(),
            lambda data: {"schema_version": 2, "decisions": validate_decisions(
                data, self._hints, self.source, self.inventory)})
        self.decisions = self._decisions_store.data
        self.reviews_file = self.reviews_file or self.decisions_file.with_name("stage3-ui-reviews.json")
        self.translations_file = self.translations_file or self.decisions_file.with_name("translation-reviews.json")
        paths = [Path(p).resolve() for p in (self.decisions_file, self.reviews_file, self.translations_file)]
        if (len(set(paths)) != len(paths)
                or any(p.with_name(p.name + ".lock") in paths for p in paths)
                or self.reviews_input_file is not None and Path(self.reviews_input_file).resolve() in paths):
            raise ValueError("conflicting_review_storage_paths")
        self._reviews_store = LocalFile(
            self.reviews_file, self.allowed_directory, review_file([]),
            lambda data: review_file(load_reviews(data, source_inventories={self.source.revision: self.source})))
        self._input_review_bytes = None
        if self.reviews_input_file is not None:
            self.reviews_input_file = Path(self.reviews_input_file)
            self._input_review_bytes = self.reviews_input_file.read_bytes()
            loaded_input = load_reviews(strict_json(self._input_review_bytes),
                                       source_inventories={self.source.revision: self.source})
            if review_file(loaded_input) != review_file(self.reviews):
                raise ValueError("stage3_input_changed_during_startup")
        local = load_reviews(self._reviews_store.data, source_inventories={self.source.revision: self.source})
        # Imported Stage 3 reviews are read-only inputs, never overwritten.
        combined = review_file([*self.reviews, *local])
        self.reviews = tuple(load_reviews(combined, source_inventories={self.source.revision: self.source}))
        self._input_reviews = tuple(r for r in self.reviews if r not in local)
        self.translations = TranslationApprovals(self.translations_file, self.allowed_directory)
        build_workbench(self.source, self.inventory, reviews=self.reviews, decisions=self.decisions)

    def _check_mapping_files(self):
        self._reviews_store.check_unchanged()
        self._decisions_store.check_unchanged()
        if (self.reviews_input_file is not None
                and self.reviews_input_file.read_bytes() != self._input_review_bytes):
            raise ValueError("stage3_input_changed_restart_required")

    def approve_mapping(self, request):
        with self._lock:
            self._check_mapping_files()
            if self.revalidate_inputs is not None:
                self.revalidate_inputs()
            assembled = approve_explicit_join(
                self.source, self.inventory, request, existing_reviews=self.reviews,
                decisions=self.decisions)
            loaded = load_reviews(assembled, source_inventories={self.source.revision: self.source})
            # A rejection blocks promotion; prior defer metadata stays intact.
            approved_quest_bindings(self.dataset, self.source, self.inventory, loaded)
            build_workbench(self.source, self.inventory, reviews=loaded, decisions=self.decisions)
            local = [r for r in loaded if r not in self._input_reviews]
            self._reviews_store.save(review_file(local))
            self.reviews = tuple(loaded)
            return {"identity_approved": True, "translation_approved": False}

    def translation_observations(self):
        # Re-run all Stage 3 proof, field-byte and target-context gates on each
        # action, including import. No candidate IDs are inferred from numbers.
        self._check_mapping_files()
        self.translations.file.check_unchanged()
        bindings = approved_quest_bindings(self.dataset, self.source, self.inventory, self.reviews)
        registry = {"classicua": ClassicUAProvider({source: field for source, field in bindings.values()}),
                    "another": AlternativeSourceStub(), "own_translator": OwnTranslatorMock()}
        observations = []
        for target, (source_id, _) in sorted(bindings.items()):
            original = self.original_index.original_english.get(target)
            if original is None:
                raise ValueError("approved_identity_lacks_verified_original")
            if not any(row.get("wording_sha256") == digest(original)
                       for row in self.inventory.contexts.get(target, ())):
                raise ValueError("unverified_spoken_original_text")
            # Empty policy must make no provider calls; there is no WoW client
            # locale in the standalone UI and hence no offline text selection.
            if not self.policy.sources:
                continue
            for candidate in discover_review_candidates(
                    TranslationRequest(source_id, original, target), self.policy, registry):
                unit = self.source.units[source_id]
                observations.append(ReviewCandidate(target, source_id, original,
                    unit.context_sha256, target_context(self.inventory, target),
                    unit.grammar_sha256, candidate))
        return observations

    def translation_page(self):
        with self._lock:
            observations = self.translation_observations()
            return self.translations.page(observations, self.policy) | {
                "source_policy": list(self.policy.sources),
                "auto_approve_one_to_one": sorted(self.policy.auto_approve_sources),
                "current_candidates": [o.row() | {"stored_locally": self.policy.stores(o.candidate.provider),
                                                   "english_original": o.original} for o in observations]}

    def translation_action(self, action, payload):
        with self._lock:
            if self.revalidate_inputs is not None:
                self.revalidate_inputs()
            observations = self.translation_observations()
            if action == "refresh" and payload == {}:
                result = self.translations.observe(observations, self.policy,
                    one_to_one_pairs=unique_one_to_one_hint_pairs(
                        self._hints, self.source.units, self.inventory))
                return result | {"activated": False}
            elif action == "edit" and set(payload) == {"identity", "text", "reviewer"}:
                return {"version_id": self.translations.edit(**payload, observations=observations, policy=self.policy)}
            elif action == "decide" and set(payload) == {"identity", "decision", "reviewer", "checks"}:
                self.translations.decide(**payload, observations=observations, policy=self.policy)
            elif action == "import" and payload == {}:
                result = self.translations.import_approved(observations, self.policy)
                return result | {"report": import_summary(
                    self.inventory, observations, self.policy, self.translations,
                    self._hints, self.source.units, changed=result["changed"])}
            elif action == "auto_import_one_to_one" and payload == {"source": "classicua"}:
                # This action is intentionally limited to an already explicitly
                # opted-in, audited source; it cannot auto-approve ID mappings.
                if not self.policy.auto_approves_one_to_one("classicua"):
                    raise ValueError("one_to_one_auto_import_not_enabled_for_source")
                if any(o.candidate.provider != "classicua" for o in observations):
                    raise ValueError("multi_source_auto_import_not_supported")
                saved = self.translations.observe(observations, self.policy,
                    one_to_one_pairs=unique_one_to_one_hint_pairs(
                        self._hints, self.source.units, self.inventory))
                result = self.translations.import_approved(observations, self.policy)
                summary = import_summary(
                    self.inventory, observations, self.policy, self.translations,
                    self._hints, self.source.units,
                    auto_approved=saved["auto_approved"], changed=result["changed"])
                return {"imported": result["imported"], "changed": result["changed"],
                        "auto_approved": saved["auto_approved"],
                        "activated": False, "report": summary}
            else:
                raise ValueError("invalid_translation_action")
            return {"saved": True, "activated": False}

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
                "approved_mappings": [
                    {"source_id": review.decision.source_id,
                     "target_id": review.decision.target_id,
                     "mapping_status": "approved"}
                    for review in self.reviews
                    if review.decision.source_id.startswith("quest:" + faction + ":")
                ],
            }

    def decide(self, source_id, target_id, decision, reason, reviewer):
        with self._lock:
            self._check_mapping_files()
            updated = record_decision(
                self.decisions, self._hints, self.source, self.inventory,
                source_id=source_id, target_id=target_id,
                decision=decision, reason=reason, reviewer=reviewer)
            build_workbench(self.source, self.inventory, reviews=self.reviews, decisions=updated)
            self._decisions_store.save(updated)
            self.decisions = updated
            return {
                "source_id": source_id, "target_id": target_id,
                "decision": decision, "reason": reason,
                "saved": True, "identity_approved": False,
                "translation_approved": False,
            }
