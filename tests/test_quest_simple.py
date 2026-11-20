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
from tools.quest_source_compatibility import LEGACY_REVISION, CURRENT_REVISION


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

    def test_390_choice_remains_ready_on_byte_identical_3101_corpus(self):
        state = self.state(texts=("Вітаю.", "Доброго дня."))
        state.inventory.revision = LEGACY_REVISION
        with TemporaryDirectory() as temp:
            db = Path(temp) / "choices.sqlite3"
            row = self.row(state, ("Вітаю.", "Доброго дня."))
            apply_choice("choose_quest", {
                "identity": self.target, "binding": row["review_binding"],
                "candidate": sha("Вітаю."), "confirm": True,
            }, row, state, db)
            with connection(db) as sql:
                original = sql.execute("""SELECT evidence, text, text_sha256, source
                    FROM quest_simple_choices WHERE moment=?""", (self.target,)).fetchone()
            state.inventory.revision = CURRENT_REVISION
            restored = resolved(state, db)[self.target]
            self.assertEqual(restored["text"], "Вітаю.")
            self.assertTrue(restored["selected"])
            with connection(db) as sql:
                self.assertEqual(sql.execute("""SELECT evidence, text, text_sha256, source
                    FROM quest_simple_choices WHERE moment=?""", (self.target,)).fetchone(), original)

            # Repeated explicit choice preserves its true provider rather than
            # making a ClassicUA candidate appear to be a new manual translation.
            updated = self.row(state, ("Вітаю.", "Доброго дня."))
            apply_choice("choose_quest", {
                "identity": self.target, "binding": updated["review_binding"],
                "candidate": sha("Вітаю."), "confirm": True,
            }, updated, state, db)
            with connection(db) as sql:
                actual = sql.execute("""SELECT evidence, text, text_sha256, source
                    FROM quest_simple_choices WHERE moment=?""", (self.target,)).fetchone()
            self.assertEqual(actual[0], updated["review_binding"])
            self.assertEqual(actual[3], "classicua")

    def test_migrated_choice_rejects_changed_original_context_and_classicua(self):
        state = self.state(originals=("Hello.", "Greetings."), texts=("Вітаю.",))
        state.inventory.revision = LEGACY_REVISION
        with TemporaryDirectory() as temp:
            db = Path(temp) / "choices.sqlite3"
            row = self.row(state, ("Вітаю.",))
            apply_choice("choose_quest", {
                "identity": self.target, "binding": row["review_binding"],
                "candidate": sha("Вітаю."), "confirm": True,
            }, row, state, db)
            state.inventory.revision = CURRENT_REVISION
            self.assertEqual(resolved(state, db)[self.target]["text"], "Вітаю.")
            state.source.revision = "c" * 40
            self.assertTrue(resolved(state, db)[self.target]["conflict"])
            state.source.revision = "b" * 40
            state.inventory.contexts[self.target][0]["wording_sha256"] = digest("Changed original.")
            # Missing/changed evidence is blocked, not silently migrated.
            self.assertNotIn(self.target, resolved(state, db))
            with connection(db) as sql:
                self.assertEqual(sql.execute(
                    "SELECT COUNT(*) FROM quest_simple_choices").fetchone()[0], 1)

    def test_save_raw_quest_text_without_language_or_placeholder_validation(self):
        state = self.state(originals=("Hello, $N.$BReturn.", "Greetings."), texts=())
        with TemporaryDirectory() as temp:
            db = Path(temp) / "test.sqlite3"
            row = self.row(state, ())
            payload = {"identity": self.target, "binding": row["review_binding"], "confirm": True}
            text = "Вітаю!$B$BЦе {нестандартний:код} і довільний переклад."
            apply_choice("save_quest", payload | {"text": text}, row, state, db)
            self.assertEqual(resolved(state, db)[self.target]["text"], text)
            self.assertTrue(resolved(state, db)[self.target]["selected"])

    def test_automatic_shared_translation_ignores_english_token_differences(self):
        state = self.state(originals=("Hello, $N.", "Greetings!"), texts=("Вітаю.",))
        self.assertEqual(resolved(state, None)[self.target]["text"], "Вітаю.")

    def test_displayed_candidate_can_be_chosen_without_old_review_approval(self):
        state = self.state(texts=())
        with TemporaryDirectory() as temp:
            db = Path(temp) / "test.sqlite3"
            row = self.row(state, ("Поза старим журналом.",))
            row["candidates"][0]["provider"] = "manual"
            apply_choice("choose_quest",
                {"identity": self.target, "binding": row["review_binding"],
                 "candidate": sha("Поза старим журналом."), "confirm": True},
                row, state, db)
            self.assertEqual(resolved(state, db)[self.target]["text"], "Поза старим журналом.")

    def test_empty_text_still_cannot_create_an_import(self):
        state = self.state(texts=())
        with TemporaryDirectory() as temp:
            db = Path(temp) / "test.sqlite3"
            row = self.row(state, ())
            with self.assertRaisesRegex(ValueError, "manager_invalid_translation_format"):
                apply_choice("save_quest", {"identity": self.target,
                    "binding": row["review_binding"], "text": " ",
                    "confirm": True}, row, state, db)
            with connection(db) as sql:
                self.assertEqual(sql.execute("SELECT COUNT(*) FROM quest_simple_choices").fetchone()[0], 0)

    def test_manager_fast_save_reuses_cached_quest_and_leaves_zip_unchanged(self):
        from unittest.mock import patch

        from tools import build_ukrainian as builder
        from tools import translation_manager as manager_module
        from tools.manager_inventory import ModuleInventory

        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "translation.sqlite3"
            archive = root / "old_quest.zip"
            gossip = root / "old_gossip.zip"
            archive.write_bytes(b"unchanged Quest ZIP")
            gossip.write_bytes(b"unchanged Gossip ZIP")
            with connection(db):
                pass
            state = self.state(texts=())
            state.revalidate_inputs = lambda: self.fail(
                "fast save must not repeat the complete ClassicUA audit")
            row = self.row(state, ())
            row.update({"label": "Synthetic Quest", "status": "missing",
                        "recorded": False, "built": None, "draft_available": True})
            view = ModuleInventory([row], None, {}, state=state)
            manager = manager_module.ManagerUI(root / "ClassicUA", root / "Spoken", db)
            self.addCleanup(manager.close)
            with patch.object(builder, "DIST", root), patch.object(
                    manager_module, "ARCHIVES", {builder.QUEST_MODULE: archive,
                                                 builder.GOSSIP_MODULE: gossip}), patch.object(
                    manager, "validate_checkouts", return_value=("pins",)), patch(
                    "tools.manager_inventory.load_inventory", return_value=view) as catalog, patch(
                    "tools.translation_manager.subprocess.run") as worker:
                manager.action("list", {"module": builder.QUEST_MODULE})
                result = manager.action("save_quest", {
                    "module": builder.QUEST_MODULE, "identity": self.target,
                    "binding": row["review_binding"], "text": "Мій переклад.",
                    "confirm": True})
                self.assertEqual(result, {"module": builder.QUEST_MODULE,
                                          "build": "review_saved"})
                self.assertEqual(catalog.call_count, 1)
                worker.assert_not_called()
            with connection(db) as conn:
                self.assertEqual(conn.execute(
                    "SELECT text, source FROM quest_simple_choices WHERE moment=?",
                    (self.target,)).fetchone(), ("Мій переклад.", "manual"))
            self.assertEqual(archive.read_bytes(), b"unchanged Quest ZIP")
            self.assertEqual(gossip.read_bytes(), b"unchanged Gossip ZIP")

    def test_fast_save_rolls_back_when_source_pin_changes_before_commit(self):
        from unittest.mock import patch

        from tools import build_ukrainian as builder
        from tools import translation_manager as manager_module
        from tools.manager_inventory import ModuleInventory

        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "translation.sqlite3"
            with connection(db):
                pass
            state = self.state(texts=())
            row = self.row(state, ())
            row.update({"label": "Synthetic Quest", "status": "missing",
                        "recorded": False, "built": None, "draft_available": True})
            manager = manager_module.ManagerUI(root / "ClassicUA", root / "Spoken", db)
            self.addCleanup(manager.close)
            with patch.object(builder, "DIST", root), patch.object(
                    manager_module, "ARCHIVES", {
                        builder.QUEST_MODULE: root / "not-built.zip"}), patch.object(
                    manager, "validate_checkouts", side_effect=[
                        ("pins",), ("pins",), ("pins",), ("changed",)]), patch(
                    "tools.manager_inventory.load_inventory",
                    return_value=ModuleInventory([row], None, {}, state=state)):
                manager.action("list", {"module": builder.QUEST_MODULE})
                with self.assertRaisesRegex(ValueError, "manager_source_configuration_changed"):
                    manager.action("save_quest", {
                        "module": builder.QUEST_MODULE, "identity": self.target,
                        "binding": row["review_binding"], "text": "Не зберігати.",
                        "confirm": True})
            with connection(db) as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM quest_simple_choices").fetchone()[0], 0)

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
