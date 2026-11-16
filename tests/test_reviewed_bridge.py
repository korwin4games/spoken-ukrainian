"""Stage 4C synthetic-only review-bound Quest translation candidate tests."""
from dataclasses import replace
from hashlib import sha256
import json
import unittest

from test_stage3 import Fixture, reviewed
from adapters.reviewed_bridge import approved_quest_bindings, reviewed_quest_batch
from adapters.translation_sources import SourcePolicy


class ReviewedQuestBridgeTests(unittest.TestCase):
    def setUp(self):
        self.inventory, self.unit, self.review, _, self.source = reviewed()
        self.fixture = Fixture().add("quest_both", "classic",
                                     '{[42]={nil,"invented wording"}}')
        self.originals = {"q:42:accept": "invented wording"}
        self.assertEqual(self.fixture.inventory().files, self.source.files)

    def batch(self, reviews, sources=("classicua", "original_english"),
              dataset=None, inventory=None):
        return reviewed_quest_batch(self.originals,
                                    dataset or self.fixture.dataset,
                                    self.source,
                                    inventory or self.inventory,
                                    reviews, SourcePolicy(tuple(sources)))

    def test_approved_identity_yields_pending_ukrainian_candidate_not_approved_text(self):
        bound = approved_quest_bindings(self.fixture.dataset, self.source,
                                        self.inventory, [self.review])
        self.assertEqual(set(bound), {"q:42:accept"})
        source_id, field = bound["q:42:accept"]
        self.assertEqual(source_id, "quest:horde:42:accept")
        self.assertEqual(field.text, "invented wording")
        self.assertEqual(field.source_file_sha256, self.unit.source_file_sha256)
        report = self.batch([self.review]).metadata()
        self.assertEqual(report["translation_candidates_pending_review"], 1)
        self.assertEqual(report["approved_translations"], 0)
        self.assertEqual(report["without_approved_translation"], 1)
        self.assertEqual(report["records"][0]["status"], "candidate_pending_review")
        self.assertEqual(report["records"][0]["source"], "classicua")
        self.assertEqual(report["records"][0]["field_sha256"],
                         sha256(b"invented wording").hexdigest())
        self.assertNotIn("invented wording", json.dumps(report))

    def test_without_reviews_never_guesses_matching_quest_id(self):
        self.assertEqual(approved_quest_bindings(
            self.fixture.dataset, self.source, self.inventory, []), {})
        report = self.batch([]).metadata()
        self.assertEqual(report["translation_candidates_pending_review"], 0)
        self.assertEqual(report["original_english_fallback"], 1)
        self.assertEqual(report["records"][0]["status"], "original_english")

    def test_explicit_english_first_overrides_even_a_reviewed_identity(self):
        report = self.batch([self.review], sources=("original_english", "classicua")).metadata()
        self.assertEqual(report["translation_candidates_pending_review"], 0)
        self.assertEqual([s["source"] for s in report["by_source"]], ["original_english"])
        self.assertEqual(report["original_english_fallback"], 1)

    def test_mock_then_reviewed_candidate_respects_source_order(self):
        report = self.batch([self.review],
                            sources=("own_translator", "classicua", "original_english")).metadata()
        self.assertEqual(report["by_source"][0]["mock_skipped"], 1)
        self.assertEqual(report["by_source"][1]["candidate_translations"], 1)
        self.assertEqual(report["by_source"][1]["remaining_for_next_source"], 0)

    def test_review_without_pinned_context_or_source_evidence_is_rejected(self):
        bad = replace(self.review, decision=replace(
            self.review.decision, source_evidence_sha256="f" * 64))
        with self.assertRaises(ValueError):
            self.batch([bad])
        changed_context = self.inventory.contexts["q:42:accept"][0] | {"voice": "changed"}
        inv = replace(self.inventory, contexts={"q:42:accept": [changed_context]})
        with self.assertRaisesRegex(ValueError, "stale_or_unapproved"):
            self.batch([self.review], inventory=inv)

    def test_tampered_unaudited_effective_text_is_rejected(self):
        modified = Fixture().add("quest_both", "classic",
                                  '{[42]={nil,"changed invented wording"}}')
        with self.assertRaisesRegex(ValueError, "reviewed_quest_effective_field_mismatch"):
            self.batch([self.review], dataset=modified.dataset)

    def test_mapping_without_verified_english_original_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "approved_identity_lacks_verified_original"):
            reviewed_quest_batch({}, self.fixture.dataset, self.source,
                                 self.inventory, [self.review],
                                 SourcePolicy(("classicua", "original_english")))

    def test_all_requests_require_verified_canonical_originals(self):
        for bad in ({"q:999:accept": "invented"}, {"q:42:accept": ""},
                    {"q:42:accept": None}):
            with self.subTest(bad=bad), self.assertRaisesRegex(
                    ValueError, "verified_original_index_required"):
                reviewed_quest_batch(bad, self.fixture.dataset, self.source,
                                     self.inventory, (), SourcePolicy(("classicua",)))

    def test_all_source_content_remains_in_memory_only(self):
        result = self.batch([self.review])
        for row in result.metadata()["records"]:
            self.assertNotIn("text", row)
            self.assertNotIn("original_english", row)
            self.assertFalse(row["translated"])


if __name__ == "__main__":
    unittest.main()
