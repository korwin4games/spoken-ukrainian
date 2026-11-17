"""Synthetic coverage/report regression tests; no real source text is copied."""
from contextlib import redirect_stdout, redirect_stderr
from hashlib import sha256
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import tempfile
import unittest

from adapters.auto_one_to_one import MachineOneToOneStore, machine_candidates
from adapters.mapping import candidates
from adapters.spoken.text_index import TextIndex
from test_stage3 import Fixture, synthetic_inventory
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
                "imported_translations": 1,
                "machine_provisional_imports": 0})
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

    def test_provisional_machine_import_survives_restart_and_blocks_upstream_changes(self):
        fixture = Fixture().add("quest_horde", "classic",
                                '{[42]={nil,"Вигаданий переклад."}}')
        inv = synthetic_inventory()
        english = TextIndex({"q:42:accept": "invented wording"}, (), {})
        source = fixture.inventory()
        hints = candidates(source.units, inv)
        rows = machine_candidates(fixture.dataset, source, inv, english, hints)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["decision"], "machine_1to1_provisional")
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "build"
            store = MachineOneToOneStore(base / "machine.json", base)
            result = store.run(rows)
            self.assertEqual(result["imported"], 1)
            self.assertEqual(result["new_machine_1to1"], 1)
            self.assertEqual(store.run(rows)["changed"], False)
            self.assertEqual(base.joinpath("machine.json").stat().st_mode & 0o777, 0o600)
            reopened = MachineOneToOneStore(base / "machine.json", base)
            self.assertEqual(reopened.current_import_targets(), {"q:42:accept"})
            human = TranslationApprovals(base / "reviews.json", base)
            report = import_summary(inv, [], auto_policy(), human, hints,
                                    source.units, machine_targets=reopened.current_import_targets())
            self.assertEqual(report["total_spoken_records"], 1)
            self.assertEqual(report["machine_one_to_one_imported"], 1)
            self.assertEqual(report["imported_total"], 1)
            self.assertEqual(report["untranslated_total"], 0)
            self.assertEqual(report["by_source"][0]["machine_provisional_imports"], 1)
            # New upstream wording is a pending version, never silently
            # overwritten or re-approved (existing auto import becomes stale).
            updated = Fixture().add("quest_horde", "classic",
                                    '{[42]={nil,"Новий вигаданий переклад."}}')
            newsource = updated.inventory()
            newrows = machine_candidates(updated.dataset, newsource, inv, english,
                                         candidates(newsource.units, inv))
            changed = reopened.run(newrows)
            self.assertEqual(changed["imported"], 0)
            self.assertEqual(len(reopened.file.data["versions"]), 2)
            self.assertEqual({r["decision"] for r in reopened.file.data["versions"]},
                             {"machine_1to1_provisional", "pending_update"})
            self.assertEqual(reopened.current_import_targets(), set())

    def test_machine_import_rejects_shared_faction_and_manual_override(self):
        f = Fixture().add("quest_both", "classic",
                          '{[42]={nil,"Вигаданий текст."}}')
        inv = synthetic_inventory()
        originals = TextIndex({"q:42:accept": "invented wording"}, (), {})
        self.assertEqual(machine_candidates(f.dataset, f.inventory(), inv, originals,
                                            candidates(f.inventory().units, inv)), [])
        unique = Fixture().add("quest_horde", "classic",
                               '{[42]={nil,"Вигаданий текст."}}')
        rows = machine_candidates(unique.dataset, unique.inventory(), inv, originals,
                                  candidates(unique.inventory().units, inv))
        self.assertEqual(len(rows), 1)
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "build"
            store = MachineOneToOneStore(base / "machine.json", base)
            self.assertEqual(store.run(rows, blocked_targets={"q:42:accept"})["imported"], 0)
            self.assertEqual(store.file.data["versions"], [])

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
            for name in ("classicua", "spoken"):
                (Path(d) / name / ".git").mkdir(parents=True)
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


    def test_cli_rejects_example_paths_with_actionable_hint(self):
        with tempfile.TemporaryDirectory() as d, patch(
                "tools.review_ui_server.build_state") as state:
            stderr = StringIO()
            with redirect_stderr(stderr):
                code = cli_main(["--classicua", str(Path(d) / "missing-classicua"),
                                 "--spoken", str(Path(d) / "missing-spoken"),
                                 "--auto-import-one-to-one"])
            self.assertEqual(code, 1)
            self.assertIn("classicua_checkout_path_missing", stderr.getvalue())
            self.assertIn("placeholders", stderr.getvalue())
            state.assert_not_called()

    def test_cli_explains_missing_spoken_checkout_git_directory(self):
        with tempfile.TemporaryDirectory() as d, patch(
                "tools.review_ui_server.build_state") as state:
            (Path(d) / "classicua" / ".git").mkdir(parents=True)
            (Path(d) / "spoken").mkdir()
            stderr = StringIO()
            with redirect_stderr(stderr):
                code = cli_main(["--classicua", str(Path(d) / "classicua"),
                                 "--spoken", str(Path(d) / "spoken"),
                                 "--auto-import-one-to-one"])
            self.assertEqual(code, 1)
            self.assertIn("spoken_checkout_root_missing", stderr.getvalue())
            self.assertIn("Spoken path must be a real Git repository root", stderr.getvalue())
            state.assert_not_called()

    def test_cli_explains_failed_spoken_git_read(self):
        with tempfile.TemporaryDirectory() as d, patch(
                "tools.review_ui_server.build_state",
                side_effect=ValueError("public_git_read_failed")):
            for name in ("classicua", "spoken"):
                (Path(d) / name / ".git").mkdir(parents=True)
            stderr = StringIO()
            with redirect_stderr(stderr):
                code = cli_main(["--classicua", str(Path(d) / "classicua"),
                                 "--spoken", str(Path(d) / "spoken"),
                                 "--auto-import-one-to-one"])
            self.assertEqual(code, 1)
            self.assertIn("public_git_read_failed", stderr.getvalue())
            self.assertIn("git -C /your/real/spoken-wow rev-parse HEAD", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
