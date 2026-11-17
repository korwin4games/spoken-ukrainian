"""Synthetic-only tests for configurable source policy and batch coverage."""
import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.translation_sources import (
    SourcePolicy, load_source_policy, TranslationRequest, EffectiveClassicUAField,
    ClassicUAProvider, AlternativeSourceStub, OwnTranslatorMock, CandidateState,
    TranslationCandidate,
    resolve_translation, resolve_spoken_batch,
)


class Counting:
    def __init__(self, target):
        self.target = target
        self.calls = []

    def lookup(self, request):
        self.calls.append(request.canonical_spoken_id)
        return self.target.lookup(request)


class TranslationSourceTests(unittest.TestCase):
    def setUp(self):
        self.ids = ["q:41:accept", "q:42:progress", "b:123", "g:" + "a" * 32]
        self.records = [TranslationRequest("verified:source:" + str(i),
                                           "Invented English " + str(i), key, "deDE")
                        for i, key in enumerate(self.ids)]
        fields = {
            "verified:source:0": EffectiveClassicUAField(
                "Вигаданий український текст", "classic.lua", "a" * 40, "b" * 64),
            "verified:source:2": EffectiveClassicUAField(
                "Другий вигаданий текст", "classic.lua", "a" * 40, "b" * 64),
        }
        self.classic = Counting(ClassicUAProvider(fields))
        self.another = Counting(AlternativeSourceStub())
        self.mock = Counting(OwnTranslatorMock())
        self.providers = {"classicua": self.classic, "another": self.another,
                          "own_translator": self.mock}

    def run_batch(self, sources, records=None):
        return resolve_spoken_batch(self.records if records is None else records,
                                    SourcePolicy(tuple(sources)), self.providers, self.ids)

    def test_config_default_and_examples(self):
        actual = load_source_policy(ROOT / "config/translation_sources.json")
        self.assertEqual(actual.sources, ("classicua", "another", "own_translator", "original_english"))
        self.assertEqual(actual.saved_sources, frozenset({"classicua", "own_translator"}))
        self.assertTrue(actual.should_save("classicua"))
        self.assertTrue(actual.should_save("own_translator"))
        self.assertFalse(actual.should_save("another"))
        self.assertFalse(actual.should_save("original_english"))
        self.assertEqual(load_source_policy(ROOT / "config/examples/english-only.json").sources,
                         ("original_english",))
        self.assertEqual(load_source_policy(ROOT / "config/examples/client-language.json").sources, ())
        self.assertEqual(SourcePolicy.from_mapping({}).sources, ())
        self.assertEqual(SourcePolicy.from_mapping({}).saved_sources, frozenset())
        self.assertEqual(SourcePolicy.from_mapping({
            "schema_version": 1, "sources": ["classicua"]
        }).saved_sources, frozenset())
        self.assertEqual(SourcePolicy.from_mapping({
            "schema_version": 2, "sources": []
        }).sources, ())

    def test_v2_save_flag_validation_and_legacy_backwards_compatibility(self):
        p = SourcePolicy.from_mapping({
            "schema_version": 2,
            "sources": [
                {"name": "classicua", "save_translations": True},
                {"name": "another", "save_translations": False},
            ],
        })
        self.assertEqual(p.sources, ("classicua", "another"))
        self.assertEqual(p.saved_sources, frozenset({"classicua"}))
        self.assertTrue(p.stores("classicua"))
        self.assertFalse(p.stores("another"))
        self.assertTrue(SourcePolicy.from_mapping({"schema_version": 1, "sources": ["classicua"]}).stores("classicua"))
        self.assertFalse(SourcePolicy.from_mapping({"schema_version": 1, "sources": ["classicua"], "store_locally": {"classicua": False}}).stores("classicua"))
        self.assertEqual(SourcePolicy(("classicua",)).saved_sources, frozenset())
        bad_settings = [
            {"name": "classicua"},
            {"name": "classicua", "save_translations": "true"},
            {"name": "classicua", "save_translations": 1},
            {"name": "classicua", "save_translations": False, "extra": 1},
            "classicua",
            {"name": "original_english", "save_translations": True},
        ]
        for value in bad_settings:
            with self.subTest(value=value), self.assertRaises(ValueError):
                SourcePolicy.from_mapping({"schema_version": 2, "sources": [value]})
        with self.assertRaisesRegex(ValueError, "duplicate"):
            SourcePolicy.from_mapping({
                "schema_version": 2, "sources": [
                    {"name": "classicua", "save_translations": True},
                    {"name": "classicua", "save_translations": False},
                ],
            })
        with self.assertRaisesRegex(ValueError, "invalid_translation_save_policy"):
            SourcePolicy(("classicua",), (), frozenset({"another"}))
        with self.assertRaisesRegex(ValueError, "invalid_translation_save_policy"):
            SourcePolicy(("original_english",), (), frozenset({"original_english"}))

    def test_one_to_one_auto_approval_policy_is_explicit_and_classicua_only(self):
        config = {"schema_version": 2, "sources": [
            {"name": "classicua", "save_translations": True,
             "auto_approve_one_to_one": True},
            {"name": "another", "save_translations": False},
        ]}
        policy = SourcePolicy.from_mapping(config)
        self.assertEqual(policy.auto_approve_sources, frozenset({"classicua"}))
        self.assertTrue(policy.auto_approves_one_to_one("classicua"))
        self.assertFalse(policy.auto_approves_one_to_one("another"))
        self.assertFalse(load_source_policy(
            ROOT / "config/translation_sources.json").auto_approves_one_to_one("classicua"))
        self.assertEqual(SourcePolicy.from_mapping({"schema_version": 1,
                         "sources": ["classicua"]}).auto_approve_sources, frozenset())
        self.assertEqual(SourcePolicy.from_mapping({"schema_version": 2,
                         "sources": [{"name": "classicua", "save_translations": True}]}
                         ).auto_approve_sources, frozenset())
        for source, save in (("another", True), ("own_translator", True),
                             ("original_english", False), ("classicua", False)):
            with self.subTest(source=source), self.assertRaises(ValueError):
                SourcePolicy.from_mapping({"schema_version": 2, "sources": [
                    {"name": source, "save_translations": save,
                     "auto_approve_one_to_one": True}]})
        for invalid in ("true", 1, None, [], {}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                SourcePolicy.from_mapping({"schema_version": 2, "sources": [
                    {"name": "classicua", "save_translations": True,
                     "auto_approve_one_to_one": invalid}]})
        with self.assertRaises(ValueError):
            SourcePolicy.from_mapping({"schema_version": 1, "sources": ["classicua"],
                                       "auto_approve_one_to_one": True})

    def test_config_bad_duplicate_unknown_version_and_shape(self):
        invalid = [
            {"schema_version": 1, "sources": ["classicua", "classicua"]},
            {"schema_version": 1, "sources": ["invalid"]},
            {"schema_version": 3, "sources": []},
            {"schema_version": True, "sources": []},
            {"schema_version": 1, "sources": "classicua"},
            {"schema_version": 1, "sources": [False]},
            {"schema_version": 1, "sources": [], "eval": "bad"},
        ]
        for bad in invalid:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                SourcePolicy.from_mapping(bad)

    def test_missing_and_blank_json_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sources.json"
            with self.assertRaises(ValueError):
                load_source_policy(p)
            p.write_text(" ")
            with self.assertRaises(ValueError):
                load_source_policy(p)

    def test_batch_sources_only_receive_remaining_records(self):
        report = self.run_batch(["classicua", "another", "own_translator", "original_english"])
        # Lookup remains read-only even with per-source opt-in settings.
        self.assertFalse(hasattr(report, "saved_translations"))
        self.assertEqual(len(self.classic.calls), 4)
        self.assertEqual(len(self.another.calls), 2)
        self.assertEqual(len(self.mock.calls), 2)
        self.assertEqual([(s.source, s.candidate_translations, s.remaining_for_next_source)
                          for s in report.stages],
                         [("classicua", 2, 2), ("another", 0, 2),
                          ("own_translator", 0, 2), ("original_english", 0, 0)])
        self.assertEqual(report.metadata()["total"], 4)
        self.assertEqual(report.metadata()["translation_candidates_pending_review"], 2)
        self.assertEqual(report.metadata()["approved_translations"], 0)
        self.assertEqual(report.metadata()["original_english_fallback"], 2)
        self.assertEqual(report.metadata()["without_approved_translation"], 4)

    def test_batch_assignment_has_exactly_one_row_per_canonical_id(self):
        report = self.run_batch(["classicua", "original_english"])
        self.assertEqual({r.canonical_spoken_id for r in report.assignments}, set(self.ids))
        self.assertEqual(len(report.assignments), len(self.ids))
        self.assertEqual([r.source for r in report.assignments].count("classicua"), 2)

    def test_input_order_does_not_change_report_bytes(self):
        normal = self.run_batch(["classicua", "original_english"]).metadata()
        reversed_batch = self.run_batch(["classicua", "original_english"],
                                        list(reversed(self.records))).metadata()
        self.assertEqual(json.dumps(normal, sort_keys=True), json.dumps(reversed_batch, sort_keys=True))

    def test_first_english_source_short_circuits_everything(self):
        report = self.run_batch(["original_english", "classicua", "another"])
        self.assertEqual([s.source for s in report.stages], ["original_english"])
        self.assertEqual(report.metadata()["original_english_fallback"], 4)
        self.assertEqual(self.classic.calls, [])
        self.assertEqual(self.another.calls, [])

    def test_only_english_is_handled_but_not_translated(self):
        report = self.run_batch(["original_english"])
        self.assertEqual(report.stages[0].candidate_translations, 0)
        self.assertEqual(report.stages[0].remaining_for_next_source, 0)
        self.assertEqual(report.stages[0].without_ukrainian_candidate, 4)

    def test_own_mock_first_cannot_prevent_later_translation(self):
        r = self.run_batch(["own_translator", "classicua", "original_english"])
        self.assertEqual(r.stages[0].mock_skipped, 4)
        self.assertEqual(len(self.classic.calls), 4)
        self.assertEqual(r.stages[1].candidate_translations, 2)
        self.assertEqual(r.metadata()["approved_translations"], 0)

    def test_only_mock_is_not_a_translation(self):
        r = self.run_batch(["own_translator"])
        self.assertEqual(r.metadata()["untranslated_no_source"], 4)
        self.assertEqual(r.metadata()["translation_candidates_pending_review"], 0)
        self.assertEqual(r.stages[0].mock_skipped, 4)

    def test_no_english_does_not_silently_append_english(self):
        r = self.run_batch(["another"])
        self.assertEqual(r.metadata()["untranslated_no_source"], 4)
        self.assertEqual(r.metadata()["original_english_fallback"], 0)

    def test_empty_policy_uses_client_language_without_provider_calls(self):
        r = self.run_batch([])
        self.assertEqual(r.stages, ())
        self.assertEqual(r.metadata()["client_language"], 4)
        self.assertEqual({a.client_locale for a in r.assignments}, {"deDE"})
        self.assertEqual(len(self.classic.calls), 0)

    def test_empty_policy_requires_supplied_actual_locale(self):
        with self.assertRaisesRegex(ValueError, "client_locale_required"):
            self.run_batch([], [TranslationRequest("source", "English", self.ids[0])])
        with self.assertRaisesRegex(ValueError, "invalid_client_locale"):
            TranslationRequest("source", "English", self.ids[0], "bad")

    def test_unverified_or_duplicate_spoken_ids_rejected(self):
        with self.assertRaisesRegex(ValueError, "unverified_or_duplicate"):
            self.run_batch(["classicua"], [
                TranslationRequest("source", "English", "q:999:accept", "enUS")])
        with self.assertRaisesRegex(ValueError, "unverified_or_duplicate"):
            self.run_batch(["classicua"], self.records + self.records[:1])

    def test_reports_exclude_original_and_translated_text_bodies(self):
        data = json.dumps(self.run_batch(["classicua", "original_english"]).metadata(), ensure_ascii=False)
        self.assertNotIn("Invented English", data)
        self.assertNotIn("Вигаданий український текст", data)
        self.assertNotIn("НЕ ПУБЛІКУВАТИ", data)

    def test_zero_items_and_totals(self):
        result = self.run_batch(["classicua", "original_english"], [])
        self.assertEqual(result.total, 0)
        self.assertEqual(result.metadata()["approved_translations"], 0)

    def test_single_request_skips_mock_then_selects_classicua_and_stops(self):
        r = resolve_translation(self.records[0],
                                SourcePolicy(("own_translator", "classicua", "original_english")),
                                self.providers)
        self.assertEqual([c.provider for c in r.candidates], ["own_translator", "classicua"])
        self.assertEqual(r.selected_source, "classicua")
        self.assertFalse(r.english_fallback_required)
        self.assertEqual(r.candidate.provider, "classicua")
        self.assertEqual(r.attempted_providers, ("own_translator", "classicua"))
        self.assertTrue(all(not c.publishable for c in r.candidates))
        self.assertEqual(r.candidates[0].state, CandidateState.MOCK_ONLY)

    def test_single_request_classicua_first_never_invokes_later_english_or_mock(self):
        r = resolve_translation(self.records[0],
                                SourcePolicy(("classicua", "own_translator", "original_english")),
                                self.providers)
        self.assertEqual(r.selected_source, "classicua")
        self.assertEqual(r.attempted_providers, ("classicua",))
        self.assertFalse(self.mock.calls)

    def test_single_request_missing_translation_selects_english_only_when_configured(self):
        r = resolve_translation(self.records[1],
                                SourcePolicy(("classicua", "original_english")),
                                self.providers)
        self.assertEqual(r.selected_source, "original_english")
        self.assertTrue(r.english_fallback_required)
        self.assertIsNone(r.candidate)
        without_english = resolve_translation(
            self.records[1], SourcePolicy(("classicua",)), self.providers)
        self.assertIsNone(without_english.selected_source)
        self.assertIsNone(without_english.candidate)

    def test_single_request_mock_only_never_selects_mock_as_translation(self):
        r = resolve_translation(self.records[0],
                                SourcePolicy(("own_translator",)), self.providers)
        self.assertIsNone(r.selected_source)
        self.assertIsNone(r.candidate)
        self.assertFalse(r.needs_review)
        self.assertEqual(r.candidates[0].state, CandidateState.MOCK_ONLY)

    def test_candidate_rejects_arbitrary_or_stale_text_digest(self):
        valid = self.classic.target.lookup(self.records[0])
        self.assertEqual(valid.field_sha256, sha256(valid.text_uk.encode("utf-8")).hexdigest())
        with self.assertRaisesRegex(ValueError, "field_digest_mismatch"):
            replace(valid, field_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "field_digest_mismatch"):
            replace(valid, text_uk="Інший вигаданий текст")
        with self.assertRaisesRegex(ValueError, "translation_candidate_requires_provenance"):
            replace(valid, text_uk=None)

    def test_bad_provider_digest_cannot_enter_single_or_batch_reports(self):
        class CorruptProvider:
            def lookup(self, request):
                return TranslationCandidate("Вигаданий текст", "another", "synthetic",
                                            "synthetic-revision", "a" * 64, "f" * 64,
                                            "pending", CandidateState.NEEDS_REVIEW)

        with self.assertRaisesRegex(ValueError, "field_digest_mismatch"):
            resolve_translation(self.records[1], SourcePolicy(("another",)), {"another": CorruptProvider()})
        with self.assertRaisesRegex(ValueError, "field_digest_mismatch"):
            resolve_spoken_batch(self.records, SourcePolicy(("another",)), {"another": CorruptProvider()}, self.ids)

    def test_no_hidden_default_when_no_source(self):
        r = resolve_translation(self.records[1], SourcePolicy(()), self.providers)
        self.assertEqual(r.selected_source, "client_language")
        self.assertEqual(r.selected_language, "deDE")
        self.assertEqual(r.attempted_providers, ())

    def test_provenance_has_distinct_source_file_and_field_digests(self):
        r = resolve_translation(self.records[0], SourcePolicy(("classicua",)), self.providers)
        c = r.candidate
        self.assertEqual(c.source_file_sha256, "b" * 64)
        self.assertNotEqual(c.field_sha256, c.source_file_sha256)
        self.assertFalse(c.publishable)

    def test_removed_provider_is_not_called(self):
        self.run_batch(["classicua", "original_english"])
        self.assertFalse(self.another.calls)
        self.assertFalse(self.mock.calls)

    def test_enabled_provider_requires_registration(self):
        with self.assertRaisesRegex(ValueError, "not_registered"):
            resolve_spoken_batch(self.records, SourcePolicy(("classicua",)), {}, self.ids)


if __name__ == "__main__":
    unittest.main()
