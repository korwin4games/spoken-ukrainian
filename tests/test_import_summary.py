"""Synthetic coverage/report regression tests; no real source text is copied."""
from contextlib import redirect_stdout
from dataclasses import dataclass
from hashlib import sha256
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import tempfile
import unittest

from adapters.import_summary import (
    format_import_table, import_summary, unique_one_to_one_hint_pairs)
from adapters.translation_approvals import ReviewCandidate, TranslationApprovals
from adapters.translation_sources import (
    CandidateState, SourcePolicy, TranslationCandidate)
from tools.review_ui_server import main as cli_main


def auto_policy():
    return SourcePolicy.from_mapping({"schema_version": 2, "sources": [
        {"name": "classicua", "save_translations": True,
         "auto_approve_one_to_one": True},
        {"name": "original_english", "save_translations": False}
    ]})


def sample():
    source_id = "quest:horde:42:accept"
    target_id = "q:42:accept"
    text = "Вигаданий переклад для тесту."
    candidate = TranslationCandidate(
        text, "classicua", "classic/invented.lua", "a" * 40, "b" * 64,
        sha256(text.encode("utf-8")).hexdigest(),
        "reviewed", CandidateState.NEEDS_REVIEW)
    observation = ReviewCandidate(target_id, source_id, "Invented English.",
                                  "c" * 64, "d" * 64, "e" * 64, candidate)
    inventory = SimpleNamespace(targets={target_id: object(), "b:100": object(),
                                         "zone:999": object()})
    source_units = {source_id: SimpleNamespace(ai=False)}
    hints = [{"source_id": source_id, "candidates": [target_id],
              "reason": "speaker_wording_eligibility_review_required"}]
    return observation, inventory, source_units, hints


class ImportSummaryTests(unittest.TestCase):
    def test_true_spoken_total_and_current_imports_are_distinct(self):
        ob, inventory, units, hints = sample()
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "build"
            approvals = TranslationApprovals(base / "translations.json", base)
            policy = auto_policy()
            pairs = unique_one_to_one_hint_pairs(hints, units, inventory)
            self.assertEqual(pairs, frozenset({(ob.source_id, ob.target_id)}))
            summary = import_summary(inventory, [ob], policy, approvals, hints, units)
            self.assertEqual(summary["total_spoken_records"], 3)
            self.assertEqual(summary["unreviewed_one_to_one_candidates"], 1)
            self.assertEqual(summary["imported_total"], 0)
            self.assertEqual(summary["untranslated_total"], 3)
            saved = approvals.observe([ob], policy, one_to_one_pairs=pairs)
            self.assertEqual(saved["auto_approved"], 1)
            self.assertEqual(approvals.import_approved([ob], policy)["imported"], 1)
            summary = import_summary(inventory, [ob], policy, approvals,
                                     hints, units, auto_approved=1)
            self.assertEqual(summary["imported_total"], 1)
            self.assertEqual(summary["untranslated_total"], 2)
            self.assertEqual(summary["coverage_percent"], 33.33)
            self.assertEqual(summary["by_source"][0], {
                "source": "classicua", "candidate_translations": 1,
                "imported_translations": 1})
            self.assertFalse(summary["saved_to_git"])
            self.assertFalse(summary["activated"])
            table = format_import_table(summary)
            self.assertIn("Записів Spoken усього: 3", table)
            self.assertIn("classicua", table)
            self.assertIn("Імпортовано: 1", table)
            self.assertIn("Без імпорту: 2", table)
            self.assertNotIn(ob.candidate.text_uk, table)

    def test_two_sources_to_one_target_are_not_automatically_one_to_one(self):
        ob, inventory, units, hints = sample()
        other = "quest:alliance:42:accept"
        units[other] = SimpleNamespace(ai=False)
        hints.append({"source_id": other, "candidates": [ob.target_id],
                      "reason": "speaker_wording_eligibility_review_required"})
        self.assertEqual(unique_one_to_one_hint_pairs(hints, units, inventory), frozenset())
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "build"
            approvals = TranslationApprovals(base / "translations.json", base)
            self.assertEqual(approvals.observe([ob], auto_policy(),
                one_to_one_pairs=frozenset())["auto_approved"], 0)
            self.assertEqual(approvals.import_approved([ob], auto_policy())["imported"], 0)

    def test_cli_bulk_flag_prints_table_and_selects_explicit_classicua(self):
        summary = {
            "total_spoken_records": 10, "unreviewed_one_to_one_candidates": 4,
            "verified_source_to_target_bindings": 2, "auto_approved_now": 1,
            "imported_total": 2, "untranslated_total": 8,
            "coverage_percent": 20.0,
            "by_source": [{"source": "classicua",
                           "candidate_translations": 2,
                           "imported_translations": 2}],
        }
        state = Mock()
        state.translation_action.return_value = {
            "report": summary, "imported": 2, "auto_approved": 1, "changed": True}
        with tempfile.TemporaryDirectory() as d, patch(
                "tools.review_ui_server.build_state", return_value=state):
            output = StringIO()
            with redirect_stdout(output):
                code = cli_main(["--classicua", str(Path(d) / "classicua"),
                                 "--spoken", str(Path(d) / "spoken"),
                                 "--auto-import-one-to-one"])
        self.assertEqual(code, 0)
        state.translation_action.assert_called_once_with(
            "auto_import_one_to_one", {"source": "classicua"})
        self.assertIn("Записів Spoken усього: 10", output.getvalue())
        self.assertIn("Імпортовано: 2", output.getvalue())
        self.assertIn("classicua", output.getvalue())


if __name__ == "__main__":
    unittest.main()
