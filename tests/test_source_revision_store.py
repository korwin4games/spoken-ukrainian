"""Synthetic source revision, conflict and active selection safety tests."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from adapters.source_revision_store import (
    SourceReviewStore, CHECKS, digest, exact,
)
from tools.source_revision_review import gossip_contexts
from tools.gossip_coverage import classicua_hash
from adapters.sqlite_translation_store import connection

A = "a" * 40
B = "b" * 40
C = "c" * 40
EN = "Hello traveler."
ORIGINAL = [{"source": "gossip", "npcType": "creature", "npcId": 42,
             "originalText": EN, "npcName": "Synthetic NPC"}]


class SourceRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "data" / "translations.sqlite3"
        self.store = SourceReviewStore(self.db)
        self.trusted = gossip_contexts(ORIGINAL)
        self.assertEqual(len(self.trusted), 1)
        self.key = list(self.trusted)[0]
        self.proof = self.trusted[self.key]

    def snapshot(self, provider, revision, text, source_ref=None, proof=None):
        p = proof or self.proof
        return {"provider": provider, "revision": revision,
                "records": [{
                    "domain": self.key[0], "target_id": self.key[1],
                    "english_sha256": p["english_sha256"],
                    "context_sha256": p["context_sha256"],
                    "ukrainian_text": text,
                    "source_ref": source_ref or f"{provider}:synthetic"
                }]}

    def approved(self, candidate_id):
        return self.store.decide(
            candidate_id, "approved", "human-reviewer",
            {k: True for k in CHECKS}, self.trusted)

    def test_import_is_immutable_and_old_snapshot_survives(self):
        old = self.snapshot("classicua", A, "Ласкаво просимо!")
        new = self.snapshot("classicua", B, "Вітаємо!")
        self.assertFalse(self.store.ingest(old, self.trusted)["unchanged"])
        self.assertTrue(self.store.ingest(old, self.trusted)["unchanged"])
        with self.assertRaisesRegex(ValueError, "source_snapshot_revision_is_immutable"):
            self.store.ingest(self.snapshot("classicua", A, "Зовсім інший текст"),
                              self.trusted)
        self.store.ingest(new, self.trusted)
        diff = self.store.compare("classicua", A, B)
        self.assertEqual(diff["counts"]["changed"], 1)
        self.assertEqual(diff["changes"][0]["before"]["ukrainian_text"], "Ласкаво просимо!")
        self.assertEqual(diff["changes"][0]["after"]["ukrainian_text"], "Вітаємо!")
        self.assertEqual(len(self.store.revisions()), 2)

    def test_second_provider_diff_never_auto_selects(self):
        self.store.ingest(self.snapshot("classicua", A, "Ласкаво просимо!"),
                          self.trusted)
        self.store.ingest(self.snapshot("another", B, "Вітаємо!"), self.trusted)
        conflict = self.store.conflicts(["classicua", "another"])
        self.assertEqual(conflict["conflicts"], 1)
        self.assertEqual([c["provider"] for c in conflict["items"][0]["candidates"]],
                         ["classicua", "another"])
        self.assertIsNone(conflict["items"][0]["selected_candidate_id"])
        self.assertIsNone(conflict["items"][0]["recommended_candidate_id"])
        self.assertEqual(self.store.active(self.trusted), [])
        candidate = conflict["items"][0]["candidates"][1]["id"]
        with self.assertRaisesRegex(ValueError, "source_selection_requires_human_approval"):
            self.store.activate(candidate, "human-reviewer", self.trusted)
        with self.assertRaisesRegex(ValueError, "source_review_requires_explicit_attestations"):
            self.store.decide(candidate, "approved", "human-reviewer",
                              {k: k != "rights" for k in CHECKS}, self.trusted)
        self.approved(candidate)
        self.assertEqual(self.store.active(self.trusted), [])
        self.store.activate(candidate, "human-reviewer", self.trusted)
        active = self.store.active(self.trusted)
        self.assertEqual(active[0]["ukrainian_text"], "Вітаємо!")
        self.assertEqual(conflict["conflicts"], 1)

    def test_old_manual_choice_persists_when_provider_updated(self):
        self.store.ingest(self.snapshot("classicua", A, "Ласкаво просимо!"),
                          self.trusted)
        first = self.store.candidates("classicua", A)[0]
        self.approved(first["id"])
        self.store.activate(first["id"], "human-reviewer", self.trusted)
        self.store.ingest(self.snapshot("classicua", B, "Новий текст"),
                          self.trusted)
        actual = self.store.active(self.trusted)
        self.assertEqual(actual[0]["id"], first["id"])
        self.assertEqual(actual[0]["revision"], A)
        self.assertEqual(self.store.compare("classicua", A, B)["counts"]["changed"], 1)
        # Revoking old approval clears its selection, never deletes text.
        self.store.decide(first["id"], "rejected", "human-reviewer",
                          {k: False for k in CHECKS}, self.trusted)
        self.assertEqual(self.store.active(self.trusted), [])
        self.assertEqual(len(self.store.candidates("classicua", A)), 1)

    def test_modified_original_fails_closed_and_does_not_rewrite(self):
        self.store.ingest(self.snapshot("classicua", A, "Текст"), self.trusted)
        first = self.store.candidates()[0]
        self.approved(first["id"])
        self.store.activate(first["id"], "reviewer", self.trusted)
        changed = {self.key: dict(self.proof, english_sha256="f" * 64)}
        with self.assertRaisesRegex(ValueError, "source_candidate_pinned_context_mismatch"):
            self.store.active(changed)
        with self.assertRaisesRegex(ValueError, "source_candidate_pinned_context_mismatch"):
            self.store.ingest(self.snapshot("another", C, "Інший текст"), changed)
        with self.assertRaisesRegex(ValueError, "source_candidate_pinned_context_mismatch"):
            self.store.activate(first["id"], "reviewer", changed)
        self.assertEqual(len(self.store.revisions()), 1)

    def test_agreement_not_conflict_priority_is_advisory(self):
        self.store.ingest(self.snapshot("classicua", A, "Той самий текст"), self.trusted)
        self.store.ingest(self.snapshot("another", B, "Той самий текст"), self.trusted)
        first = self.store.candidates("classicua", A)[0]
        self.approved(first["id"])
        view = self.store.conflicts(["another", "classicua"])
        self.assertEqual(view["conflicts"], 0)
        self.assertEqual(view["items"][0]["recommended_candidate_id"], first["id"])
        self.assertIsNone(view["items"][0]["selected_candidate_id"])
        self.assertEqual(self.store.active(self.trusted), [])

    def test_duplicate_target_and_missing_rights_are_rejected(self):
        value = self.snapshot("another", A, "Текст")
        value["records"] = value["records"] * 2
        with self.assertRaisesRegex(ValueError, "duplicate_source_candidate_context"):
            self.store.ingest(value, self.trusted)
        good = self.snapshot("another", A, "Текст")
        good["records"][0]["context_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "source_candidate_pinned_context_mismatch"):
            self.store.ingest(good, self.trusted)
        self.assertEqual(len(self.store.revisions()), 0)

    def test_sqlite_migrations_include_source_tables(self):
        with connection(self.db) as db:
            versions = [x[0] for x in db.execute("SELECT version FROM schema_migrations")]
            self.assertIn(2, versions)
            for table in ("source_snapshots", "source_candidates",
                          "source_candidate_decisions", "source_active_selections"):
                self.assertEqual(db.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?",
                    (table,)).fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
