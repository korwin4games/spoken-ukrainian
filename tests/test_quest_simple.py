"""Pinned Quest ID/event selections without reviewer forms."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

from adapters.crosswalk import digest
from adapters.source_revision_store import sha
from adapters.spoken.text_index import TextIndex
from adapters.sqlite_translation_store import connection
from tools.quest_simple import apply_choice, resolved


class SimpleQuestTests(TestCase):
    target = "q:42:accept"

    def state(self, originals=("Hello.", "Greetings."), texts=("Вітаю.",)):
        fields = {}
        units, hints, views = {}, [], {}
        for index, text in enumerate(texts):
            faction = ("horde", "alliance")[index]
            source = f"quest:{faction}:42:accept"
            units[source] = SimpleNamespace(effective_sha256=sha(text), ai=False)
            hints.append({"source_id": source, "candidates": [self.target], "status": "candidate"})
            node = lambda value: SimpleNamespace(node=SimpleNamespace(value=value))
            fields[faction] = {(2,): node(text), (1,): node("Demo")}
            views[faction] = {42: SimpleNamespace(fields=fields[faction])}
        return SimpleNamespace(
            _hints=hints,
            source=SimpleNamespace(revision="b" * 40, units=units),
            dataset=SimpleNamespace(faction_views=lambda **kwargs: (views, {})),
            inventory=SimpleNamespace(revision="a" * 40,
                targets={self.target: SimpleNamespace(family="quest")},
                contexts={self.target: [{"wording_sha256": digest(v)} for v in originals]}),
            original_index=TextIndex({}, (), {}, {self.target: originals}),
            policy=SimpleNamespace(allows_ai_transations=lambda provider: True),
            revalidate_inputs=None,
            blocked_quest_moments=lambda: set(),
        )

    def row(self, state, texts):
        from tools.quest_runtime_review import binding
        evidence, originals = binding(state, self.target, [self.target])
        return {"id": self.target, "type": "quest", "review_binding": digest(evidence),
                "original_variants": [{"target_id": self.target}], "originals": originals,
                "candidates": [{"text": text, "sha256": sha(text)} for text in texts]}

    def test_one_translation_is_automatic_for_two_originals(self):
        state = self.state()
        self.assertEqual(resolved(state, None)[self.target]["text"], "Вітаю.")
        self.assertFalse(resolved(state, None)[self.target]["selected"])

    def test_choose_between_two_translations_and_revalidate_evidence(self):
        state = self.state(texts=("Вітаю.", "Доброго дня."))
        with TemporaryDirectory() as temp:
            db = Path(temp) / "test.sqlite3"
            self.assertTrue(resolved(state, db)[self.target]["conflict"])
            row = self.row(state, ("Вітаю.", "Доброго дня."))
            result = apply_choice("choose_quest",
                {"identity": self.target, "binding": row["review_binding"],
                 "candidate": sha("Доброго дня."), "confirm": True}, row, state, db)
            self.assertEqual(result, sha("Доброго дня."))
            self.assertEqual(resolved(state, db)[self.target]["text"], "Доброго дня.")
            state.inventory.revision = "c" * 40
            self.assertTrue(resolved(state, db)[self.target]["conflict"])

    def test_manual_translation_without_reviews(self):
        state = self.state(texts=())
        with TemporaryDirectory() as temp:
            db = Path(temp) / "test.sqlite3"
            row = self.row(state, ())
            apply_choice("save_quest",
                {"identity": self.target, "binding": row["review_binding"],
                 "text": "Мій переклад.", "confirm": True}, row, state, db)
            self.assertEqual(resolved(state, db)[self.target]["text"], "Мій переклад.")
            with connection(db) as sql:
                self.assertEqual(sql.execute("SELECT COUNT(*) FROM quest_simple_choices").fetchone()[0], 1)
