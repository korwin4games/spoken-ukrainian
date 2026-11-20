"""No silent Quest evidence migration unless complete upstream source pins match."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from adapters.crosswalk import digest
from tools import quest_source_compatibility as compat


class QuestSourceCompatibilityTests(TestCase):
    def test_known_byte_identical_pins_allow_only_spoken_sha_difference(self):
        current = {"moment": "q:42:accept", "spoken": compat.CURRENT_REVISION,
                   "classicua": "b" * 40, "variants": [
                       {"target_id": "q:42:accept",
                        "contexts": [{"wording_sha256": "c" * 64}]}]}
        old = {**current, "spoken": compat.LEGACY_REVISION}
        self.assertEqual(compat._verified_upgrade(), compat.LEGACY_REVISION)
        self.assertTrue(compat.matching_evidence(old, current))
        self.assertTrue(compat.matching_selection(digest(old), current))
        self.assertTrue(compat.matching_snapshot_revision(
            compat.LEGACY_REVISION, compat.CURRENT_REVISION))
        self.assertFalse(compat.matching_snapshot_revision(
            compat.CURRENT_REVISION, compat.LEGACY_REVISION))
        self.assertFalse(compat.matching_snapshot_revision(
            compat.LEGACY_REVISION, "d" * 40))
        self.assertTrue(compat.matching_evidence(current, current))

        for changed in ({**old, "moment": "q:43:accept"},
                        {**old, "classicua": "d" * 40},
                        {**old, "variants": [{"target_id": "q:42:accept",
                                             "contexts": [{"wording_sha256": "e" * 64}]}]}):
            with self.subTest(changed=changed):
                self.assertFalse(compat.matching_evidence(changed, current))
                self.assertFalse(compat.matching_selection(digest(changed), current))
        self.assertFalse(compat.matching_evidence(
            {**old, "spoken": "f" * 40}, current))
        self.assertFalse(compat.matching_selection("not_a_sha256", current))

    def test_changed_corpus_or_pin_disables_upgrade(self):
        root = compat.ROOT
        current = json.loads((root / "tests/stage3_sources.json").read_text())
        historic = json.loads((root / "tests/stage3_390_sources.json").read_text())
        lock = json.loads((root / "sources.lock.json").read_text())
        with TemporaryDirectory() as temp:
            fake_root = Path(temp)
            (fake_root / "tests").mkdir()
            def write(current_data, historic_data, lock_data):
                (fake_root / "tests/stage3_sources.json").write_text(
                    json.dumps(current_data), encoding="utf-8")
                (fake_root / "tests/stage3_390_sources.json").write_text(
                    json.dumps(historic_data), encoding="utf-8")
                (fake_root / "sources.lock.json").write_text(
                    json.dumps(lock_data), encoding="utf-8")

            with patch.object(compat, "ROOT", fake_root):
                self.addCleanup(compat._verified_upgrade.cache_clear)
                write(current, historic, lock)
                compat._verified_upgrade.cache_clear()
                self.assertEqual(compat._verified_upgrade(), compat.LEGACY_REVISION)
                changed_corpus = json.loads(json.dumps(historic))
                changed_corpus["files"][compat.QUEST_CORPUS] = "0" * 64
                write(current, changed_corpus, lock)
                compat._verified_upgrade.cache_clear()
                self.assertIsNone(compat._verified_upgrade())
                changed_pin = json.loads(json.dumps(lock))
                changed_pin["spoken"]["revision"] = "c" * 40
                write(current, historic, changed_pin)
                compat._verified_upgrade.cache_clear()
                self.assertIsNone(compat._verified_upgrade())
                self.assertFalse(compat.matching_snapshot_revision(
                    compat.LEGACY_REVISION, compat.CURRENT_REVISION))
