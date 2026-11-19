from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from zipfile import ZipFile

from adapters.crosswalk import digest
from adapters.source_revision_store import CHECKS, sha
from adapters.spoken.text_index import TextIndex
from adapters.sqlite_translation_store import enable_sqlite
from tools.build_ukrainian import QUEST_MODULE, current_quest_texts, render_quest_lua
from tools.manager_review import apply_review
from tools.quest_runtime_review import approved, binding, history
from tools.translation_manager import verify_quest_zip


class QuestRuntimeReviewTests(TestCase):
    target = "q:42:accept"

    def state(self, originals, revision="a" * 40):
        return SimpleNamespace(
            original_index=TextIndex({}, (), {}, {self.target: originals}),
            inventory=SimpleNamespace(revision=revision,
                targets={self.target: SimpleNamespace(family="quest")},
                contexts={self.target: [{"wording_sha256": digest(text)} for text in originals]}),
            source=SimpleNamespace(revision="b" * 40),
            revalidate_inputs=None,
            blocked_quest_moments=lambda: set(),
            translation_observations=lambda: [],
            machine_imports=SimpleNamespace(file=SimpleNamespace(data={
                "schema_version": 1, "versions": [], "imports": []})),
            translations=SimpleNamespace(file=SimpleNamespace(data={
                "schema_version": 1, "versions": [], "imports": []})),
        )

    def row(self, state):
        evidence, originals = binding(state, self.target, [self.target])
        return {"id": self.target, "mapping_state": "mapping_pending", "originals": originals,
                "review_binding": digest(evidence), "original_variants": [{"target_id": self.target}],
                "candidates": []}

    def save_and_select(self, state, db, *texts):
        row = self.row(state)
        payload = {"identity": self.target, "binding": row["review_binding"],
                   "reviewer": "Fixture reviewer", "confirm": True}
        for text in texts:
            apply_review("save_translation", payload | {"candidate": "", "text": text},
                         QUEST_MODULE, row, state, None, db)
        for pending in history(db):
            if pending["decision"] == "pending":
                row["candidates"].append({"review_id": "runtime:" + pending["id"], "review_kind": "runtime",
                                          "text": pending["text"], "review": "pending"})
        return row, payload | {"checks": dict.fromkeys(CHECKS, True)}

    def test_two_drafts_selected_and_one_runtime_entry_for_two_originals(self):
        state = self.state(("Hello!", "Greetings!"))
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "reviews.sqlite3"
            row, payload = self.save_and_select(state, db, "Вітаю!", "Доброго дня!")
            selected = row["candidates"][1]
            fingerprint = apply_review("confirm_candidate", payload | {"candidate": selected["review_id"]},
                                       QUEST_MODULE, row, state, None, db)
            self.assertEqual(fingerprint, sha(selected["text"]))
            self.assertEqual(approved(state, db, [])[self.target]["text"], selected["text"])
            with enable_sqlite(db):
                preview, _, _ = current_quest_texts(state)
            self.assertEqual(list(preview[42]), ["accept"])
            archive = Path(tmp) / "quest.zip"
            with ZipFile(archive, "w") as zip_file:
                zip_file.writestr(f"{QUEST_MODULE}/Translations.lua", render_quest_lua(preview, "a" * 40))
            verify_quest_zip(archive, self.target, fingerprint)
            with self.assertRaisesRegex(ValueError, "manager_candidate_not_built"):
                verify_quest_zip(archive, self.target, sha("Вітаю!"))
            for changed in (self.state(("Hello!", "Greetings!", "Welcome!")),
                            self.state(("Hello!", "Welcome!")),
                            self.state(("Hello!", "Greetings!"), revision="c" * 40)):
                self.assertEqual(approved(changed, db, []), {})
            state.blocked_quest_moments = lambda: {self.target}
            self.assertEqual(approved(state, db, []), {})

    def test_incompatible_placeholders_and_conflicting_human_decisions(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "reviews.sqlite3"
            with self.assertRaisesRegex(ValueError, "manager_invalid_translation_format"):
                self.save_and_select(self.state(("Hello $N!", "Greetings!")), db, "Вітаю!")
            state = self.state(("Hello!", "Greetings!"))
            row, payload = self.save_and_select(state, db, "Вітаю!", "Доброго дня!")
            for selected in row["candidates"]:
                apply_review("confirm_candidate", payload | {"candidate": selected["review_id"]},
                             QUEST_MODULE, row, state, None, db)
            skipped = []
            self.assertEqual(approved(state, db, skipped), {self.target: None})
            self.assertIn((self.target, "conflicting_quest_runtime_variants"), skipped)
            del payload["checks"]
            apply_review("withdraw_quest_approval", payload | {"candidate": selected["review_id"]},
                         QUEST_MODULE, row, state, None, db)
            self.assertEqual(approved(state, db, [])[self.target]["text"], row["candidates"][0]["text"])
