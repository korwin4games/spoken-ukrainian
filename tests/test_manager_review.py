"""Exercise inline mutation gates with an actual private SQLite review store."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adapters.source_revision_store import CHECKS, SourceReviewStore
from tools.build_ukrainian import GOSSIP_MODULE, QUEST_MODULE
from tools.manager_review import apply_review
from tools.source_revision_review import gossip_contexts


class ManagerReviewTests(unittest.TestCase):
    def test_source_candidate_confirmation_is_explicit_scoped_and_idempotent(self):
        lines = [{"source": "gossip", "npcType": "creature", "npcId": 42,
                  "originalText": "Welcome, $N!"}]
        trusted = gossip_contexts(lines)
        (_, target), proof = next(iter(trusted.items()))
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "reviews.sqlite3"
            store = SourceReviewStore(db)
            text = "Вітаю, {ім'я}!"
            store.ingest({"provider": "another", "revision": "a" * 40, "records": [{
                "domain": "gossip", "target_id": target, "english_sha256": proof["english_sha256"],
                "context_sha256": proof["context_sha256"], "ukrainian_text": text, "source_ref": "fixture",
            }]}, trusted)
            candidate = store.candidates()[0]
            self.assertEqual(store.active(trusted), [])
            choice = {"review_id": candidate["id"], "review_kind": "source", "review": "pending", "text": text}
            row = {"id": target, "originals": ["Welcome, $N!"], "mapping_state": "mapping_pending",
                   "npc_id": 42, "english_hash": proof["english_hash"], "candidates": [choice]}
            payload = {"identity": target, "candidate": candidate["id"], "reviewer": "Fixture reviewer",
                       "checks": dict.fromkeys(CHECKS, True), "confirm": True}
            state = SimpleNamespace(inventory=SimpleNamespace(revision="b" * 40),
                                    source=SimpleNamespace(revision="c" * 40))
            with patch("tools.manager_review.read_pinned_corpus", return_value=lines):
                for changed, reason in (
                        ({"confirm": False}, "manager_invalid_review_request"),
                        ({"checks": dict.fromkeys(CHECKS, False)}, "manager_review_checks_required"),
                        ({"candidate": "unknown"}, "manager_candidate_unavailable")):
                    with self.assertRaisesRegex(ValueError, reason):
                        apply_review("confirm_candidate", payload | changed, GOSSIP_MODULE, row, state, None, db)
                with self.assertRaisesRegex(ValueError, "manager_candidate_unavailable"):
                    apply_review("confirm_candidate", payload, QUEST_MODULE, row, state, None, db)
                with self.assertRaisesRegex(ValueError, "manager_review_context_blocked"):
                    apply_review("confirm_candidate", payload, GOSSIP_MODULE,
                                 row | {"originals": ["One", "Two"]}, state, None, db)
                for status, translation, error in (
                        ("rejected", text, "manager_candidate_unavailable"),
                        ("pending", "Вітаю!", "manager_invalid_translation_format")):
                    with self.assertRaisesRegex(ValueError, error):
                        apply_review("confirm_candidate", payload, GOSSIP_MODULE,
                                     row | {"candidates": [choice | {"review": status, "text": translation}]},
                                     state, None, db)
                self.assertEqual(store.active(trusted), [])
                self.assertEqual(apply_review("confirm_candidate", payload, GOSSIP_MODULE,
                                             row, state, None, db), candidate["text_sha256"])
                self.assertEqual(store.active(trusted)[0]["id"], candidate["id"])
                apply_review("confirm_candidate", payload, GOSSIP_MODULE,
                             row | {"candidates": [choice | {"review": "source_selected"}]}, state, None, db)
                self.assertEqual(len(store.selection_history("gossip", target)), 1)
