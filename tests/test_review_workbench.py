"""Synthetic tests for the Stage 4B reviewer workbench (no real source text)."""
from dataclasses import replace
import json
import unittest

from adapters.classicua.evidence import SourceInventory, source_reference
from adapters.crosswalk import EffectiveUnit, VerifiedTarget, digest
from adapters.mapping import review_file, load_reviews, target_context
from adapters.review_workbench import (build_workbench, empty_decisions, record_decision,
                                       validate_decisions)
from adapters.spoken import Inventory
from adapters.spoken.evidence import JoinProof, approve_review, proof_digest


REV = "1" * 40
SOURCE_SHA = "2" * 64
TARGET_SHA = "3" * 64
FILE = "entries/classic/quest_horde.lua"


def make_unit(identity, ai=False):
    return EffectiveUnit(
        identity, "quest", "4" * 64, "5" * 64, ai, REV, SOURCE_SHA,
        FILE, "classic", None, "6" * 64, "quest_horde"
    )


def context(qid, event, faction="horde", voice="invented-voice"):
    return {
        "npc_id": 99, "npc_type": "creature", "voice": voice, "faction": faction,
        "player_gender": None, "wording_sha256": digest("Invented English"),
        "source": event, "quest_id": qid, "generatable": True
    }


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.units = {identity: make_unit(identity, ai=ai) for identity, ai in (
            ("quest:horde:42:accept", False),
            ("quest:horde:43:progress", False),
            ("quest:horde:44:accept", True),
            ("quest:horde:45:complete", False),
            ("quest:horde:46:accept", False),
            ("quest:alliance:42:accept", False),
        )}
        self.source = SourceInventory(REV, {FILE: SOURCE_SHA}, self.units)
        self.contexts = {
            "q:42:accept": [context(42, "accept", faction="both")],
            "q:43:progress:w1": [context(43, "progress", voice="voice-1")],
            "q:43:progress:w2": [context(43, "progress", voice="voice-2")],
            "q:44:accept": [context(44, "accept")],
            "q:46:accept": [context(46, "accept", faction="alliance")],
        }
        self.targets = {
            key: VerifiedTarget(key, "quest", "a" * 40, "invented-public-ref", TARGET_SHA)
            for key in self.contexts
        }
        self.inv = Inventory(self.targets, self.contexts, {}, "a" * 40, {})

    def queue(self, decisions=None, reviews=(), limit=50, offset=0, faction="horde"):
        return build_workbench(self.source, self.inv, decisions=decisions, reviews=reviews,
                               limit=limit, offset=offset, faction=faction)

    def test_actionable_quest_queue_is_metadata_only_and_not_approved(self):
        report = self.queue()
        self.assertEqual(report["summary"]["quest_source_units"], 5)
        self.assertEqual(report["summary"]["ai_marked_excluded_from_queue"], 1)
        self.assertEqual(report["summary"]["no_canonical_candidate"], 1)
        self.assertEqual(report["summary"]["faction_conflicts_excluded_from_queue"], 1)
        self.assertEqual(report["summary"]["queued_source_units"], 2)
        self.assertEqual(report["summary"]["new_identity_approvals_created"], 0)
        self.assertEqual(report["summary"]["translation_content_approvals_created"], 0)
        ids = [r["source_id"] for r in report["queue"]]
        self.assertEqual(ids, ["quest:horde:42:accept", "quest:horde:43:progress"])
        entry = report["queue"][0]
        self.assertEqual(entry["source_reference"],
                         source_reference(self.source.units[entry["source_id"]]))
        self.assertEqual(entry["source_context_sha256"], "6" * 64)
        self.assertEqual(entry["target_options"][0]["target_id"], "q:42:accept")
        self.assertEqual(entry["status"], "identity_review_required")
        self.assertNotIn("Invented English", json.dumps(report))

    def test_variants_are_separate_target_options_not_merged_evidence(self):
        entry = self.queue()["queue"][1]
        self.assertEqual(entry["candidate_reason"], "multiple_wording_or_voice_variants")
        self.assertEqual([o["target_id"] for o in entry["target_options"]],
                         ["q:43:progress:w1", "q:43:progress:w2"])
        self.assertEqual([o["variants"][0]["voice"] for o in entry["target_options"]],
                         ["voice-1", "voice-2"])
        self.assertEqual(len(entry["required_review"]), 5)

    def test_page_offset_and_limit_are_deterministic(self):
        q1 = self.queue(limit=1, offset=0)
        q2 = self.queue(limit=1, offset=1)
        self.assertTrue(q1["summary"]["has_more"])
        self.assertFalse(q2["summary"]["has_more"])
        self.assertNotEqual(q1["queue"][0]["source_id"], q2["queue"][0]["source_id"])
        self.assertEqual(q1["summary"]["queued_source_units"], 2)
        self.assertEqual(q2["summary"]["queued_source_units"], 2)
        self.assertEqual(json.dumps(q1, sort_keys=True), json.dumps(self.queue(limit=1), sort_keys=True))

    def test_faction_filter_is_explicit(self):
        x = self.queue(faction="alliance")
        self.assertEqual(x["summary"]["quest_source_units"], 1)
        self.assertEqual(x["summary"]["faction_conflicts_excluded_from_queue"], 0)
        # Exact target context for this synthetic fixture belongs to Horde.
        self.assertEqual(len(x["queue"]), 1)

    def test_reject_one_variant_but_keep_other_variant_eligible(self):
        from adapters.mapping import candidates
        hints = candidates(self.source.units, self.inv)
        d = record_decision(empty_decisions(), hints, self.source, self.inv, source_id="quest:horde:43:progress",
                            target_id="q:43:progress:w1", decision="rejected",
                            reviewer="Invented reviewer", reason="wrong_speaker")
        q = self.queue(decisions=d)
        item = next(r for r in q["queue"] if r["source_id"] == "quest:horde:43:progress")
        self.assertEqual([o["target_id"] for o in item["target_options"]], ["q:43:progress:w2"])
        self.assertEqual(q["summary"]["rejected_candidate_pairs"], 1)
        self.assertEqual(q["summary"]["new_identity_approvals_created"], 0)

    def test_reject_all_candidates_removes_only_source_from_queue(self):
        from adapters.mapping import candidates
        hints = candidates(self.source.units, self.inv)
        d = empty_decisions()
        for target in ("q:43:progress:w1", "q:43:progress:w2"):
            d = record_decision(d, hints, self.source, self.inv, source_id="quest:horde:43:progress",
                                target_id=target, decision="rejected",
                                reviewer="Invented reviewer", reason="wrong_speaker")
        q = self.queue(decisions=d)
        self.assertEqual(q["summary"]["fully_rejected_source_units"], 1)
        self.assertEqual(q["summary"]["queued_source_units"], 1)

    def test_defer_is_visible_but_never_approval(self):
        from adapters.mapping import candidates
        d = record_decision(empty_decisions(), candidates(self.source.units, self.inv),
                            self.source, self.inv,
                            source_id="quest:horde:42:accept", target_id="q:42:accept",
                            decision="deferred", reviewer="Invented reviewer",
                            reason="insufficient_evidence")
        opt = self.queue(decisions=d)["queue"][0]["target_options"][0]
        self.assertEqual(opt["manual_decision"], "deferred")
        self.assertEqual(opt["manual_reason"], "insufficient_evidence")
        self.assertEqual(self.queue(decisions=d)["summary"]["human_stage3_approved_joins"], 0)

    def test_invalid_manually_claimed_approval_and_unknown_pair_fail_closed(self):
        from adapters.mapping import candidates
        hints = candidates(self.source.units, self.inv)
        data = record_decision(empty_decisions(), hints, self.source, self.inv,
                               source_id="quest:horde:42:accept",
                               target_id="q:42:accept", decision="rejected",
                               reviewer="Person", reason="other")
        data["decisions"][0]["decision"] = "approved"
        with self.assertRaisesRegex(ValueError, "invalid_or_duplicate"):
            validate_decisions(data, hints, self.source, self.inv)
        data["decisions"][0]["decision"] = "rejected"
        data["decisions"][0]["target_id"] = "q:44:accept"
        with self.assertRaisesRegex(ValueError, "invalid_or_duplicate"):
            validate_decisions(data, hints, self.source, self.inv)
        data["decisions"][0]["target_id"] = "q:42:accept"
        with self.assertRaisesRegex(ValueError, "invalid_or_duplicate"):
            validate_decisions({"schema_version": 2, "decisions": data["decisions"] * 2},
                               hints, self.source, self.inv)

    def test_strict_decision_schema_and_no_source_bodies(self):
        from adapters.mapping import candidates
        hints = candidates(self.source.units, self.inv)
        for data in ({}, {"schema_version": True, "decisions": []},
                     {"schema_version": 1, "decisions": [], "text": "Invented English"},
                     {"schema_version": 1, "decisions": {}}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_decisions(data, hints, self.source, self.inv)
        d = record_decision(empty_decisions(), hints, self.source, self.inv,
                            source_id="quest:horde:42:accept", target_id="q:42:accept",
                            decision="rejected", reviewer="Invented reviewer", reason="other")
        self.assertNotIn("Invented English", json.dumps(d))
        self.assertEqual(len(validate_decisions(d, hints, self.source, self.inv)), 1)

    def test_manual_rejection_rejects_changed_source_and_target_evidence(self):
        from adapters.mapping import candidates
        hints = candidates(self.source.units, self.inv)
        record = record_decision(empty_decisions(), hints, self.source, self.inv,
                                 source_id="quest:horde:42:accept",
                                 target_id="q:42:accept", decision="rejected",
                                 reviewer="Invented human", reason="wrong_speaker")
        self.assertEqual(record["schema_version"], 2)
        self.assertEqual(record["decisions"][0]["source_revision"], REV)
        self.assertEqual(record["decisions"][0]["target_context_sha256"],
                         target_context(self.inv, "q:42:accept"))
        changed_units = dict(self.units)
        changed_units["quest:horde:42:accept"] = replace(
            changed_units["quest:horde:42:accept"], context_sha256="f" * 64)
        changed_source = SourceInventory(REV, {FILE: SOURCE_SHA}, changed_units)
        with self.assertRaisesRegex(ValueError, "stale_workbench_decision_evidence"):
            build_workbench(changed_source, self.inv, decisions=record, faction="horde")
        with self.assertRaisesRegex(ValueError, "stale_workbench_decision_evidence"):
            build_workbench(self.source, replace(
                self.inv, contexts=self.contexts | {"q:42:accept": [
                    context(42, "accept", faction="both", voice="new-voice")]}),
                decisions=record, faction="horde")
        changed_file = {k: replace(u, source_revision="b" * 40,
                                   source_file_sha256="d" * 64) for k, u in self.units.items()}
        moved_source = SourceInventory("b" * 40, {FILE: "d" * 64}, changed_file)
        with self.assertRaisesRegex(ValueError, "stale_workbench_decision_evidence"):
            build_workbench(moved_source, self.inv, decisions=record, faction="horde")

    def test_malformed_decision_ids_raise_value_error_not_type_error(self):
        from adapters.mapping import candidates
        valid = record_decision(empty_decisions(), candidates(self.source.units, self.inv),
                                self.source, self.inv, source_id="quest:horde:42:accept",
                                target_id="q:42:accept", decision="deferred",
                                reviewer="Invented human", reason="other")
        valid["decisions"][0]["target_id"] = ["q:42:accept"]
        with self.assertRaisesRegex(ValueError, "invalid_or_duplicate"):
            validate_decisions(valid, candidates(self.source.units, self.inv),
                               self.source, self.inv)

    def test_v1_manual_decisions_require_explicit_migration(self):
        with self.assertRaisesRegex(ValueError, "invalid_workbench_decisions_schema"):
            self.queue(decisions={"schema_version": 1, "decisions": []})

    def test_pure_function_requires_trusted_source_inventory(self):
        with self.assertRaisesRegex(ValueError, "audited_source_inventory_required"):
            build_workbench({"units": self.units}, self.inv)
        with self.assertRaisesRegex(ValueError, "invalid_workbench"):
            self.queue(limit=0)
        with self.assertRaisesRegex(ValueError, "invalid_workbench"):
            self.queue(offset=-1)
        with self.assertRaisesRegex(ValueError, "invalid_workbench"):
            self.queue(faction="both")

    def approved_review(self):
        source_id = "quest:horde:42:accept"
        unit = self.units[source_id]
        target_id = "q:42:accept"
        facts = {k: v for k, v in self.contexts[target_id][0].items()
                 if k != "generatable"}
        p = JoinProof(
            unit.context_sha256, target_context(self.inv, target_id), facts,
            source_reference(unit), unit.source_file_sha256,
            self.targets[target_id].evidence_ref, self.targets[target_id].evidence_sha256,
            "Invented independent evidence reviewer"
        )
        bound = replace(unit, identity_evidence_sha256=proof_digest(p))
        return approve_review(bound, target_id, self.inv, p,
                              "Invented distinct mapping reviewer",
                              source_inventory=self.source)

    def test_only_stage3_proven_review_is_an_identity_approval(self):
        review = self.approved_review()
        # Stage 3 serializes metadata/proof and strictly verifies the audited baseline.
        parsed = load_reviews(json.loads(json.dumps(review_file([review]))),
                              source_inventories={REV: self.source})
        q = self.queue(reviews=parsed)
        self.assertEqual(q["summary"]["human_stage3_approved_joins"], 1)
        self.assertEqual(q["summary"]["approved_identities_excluded_from_queue"], 1)
        self.assertEqual(q["summary"]["queued_source_units"], 1)
        self.assertEqual(q["summary"]["new_identity_approvals_created"], 0)
        self.assertEqual(q["summary"]["translation_content_approvals_created"], 0)

    def test_approved_join_conflicts_with_manual_rejection(self):
        from adapters.mapping import candidates
        review = self.approved_review()
        d = record_decision(empty_decisions(), candidates(self.source.units, self.inv),
                            self.source, self.inv,
                            source_id="quest:horde:42:accept", target_id="q:42:accept",
                            decision="rejected", reviewer="Invented reviewer", reason="wrong_speaker")
        with self.assertRaisesRegex(ValueError, "conflicting_approved"):
            self.queue(decisions=d, reviews=(review,))


if __name__ == "__main__":
    unittest.main()
