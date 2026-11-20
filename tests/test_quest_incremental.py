"""Verify unchanged Quest imports survive a ready-only ZIP rebuild."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from adapters.import_statistics import store_successful_build
from adapters.sqlite_translation_store import connection
from tools import build_ukrainian as builder
from tools.quest_incremental import merge_ready, previous_snapshot
from tools.quest_source_compatibility import LEGACY_REVISION, CURRENT_REVISION


class QuestIncrementalTests(TestCase):
    spoken_revision = "a" * 40
    classicua_revision = "b" * 40

    def baseline(self, root, *, revision=None):
        revision = self.spoken_revision if revision is None else revision
        archive = root / "Spoken_Quest_UA_Local_Test.zip"
        old = {42: {"title": "Назва", "accept": {
            "text": "Старий переклад.", "reviewed": False, "quick": True}},
            43: {"progress": {"text": "Недоторканий.", "reviewed": True}}}
        with patch.object(builder, "DIST", root):
            artifact, digest = builder.write_zip(
                {"Spoken_Quest_UA/Translations.lua": builder.render_quest_lua(
                    old, revision)}, archive)
        db = root / "translations.sqlite3"
        rows = [
            {"domain": "quests", "unit": "42:accept", "entity": "42",
             "source": "classicua", "route": "pinned_unique",
             "text_sha256": sha256(old[42]["accept"]["text"].encode()).hexdigest()},
            {"domain": "quests", "unit": "43:progress", "entity": "43",
             "source": "classicua", "route": "reviewed",
             "text_sha256": sha256(old[43]["progress"]["text"].encode()).hexdigest()},
        ]
        store_successful_build(db, module=builder.QUEST_MODULE,
            artifact_sha256=digest, spoken_revision=revision,
            classicua_revision=self.classicua_revision, rows=rows)
        return archive, db, old

    def test_retains_all_previous_moments_when_only_one_is_ready(self):
        with TemporaryDirectory() as temp:
            archive, db, old = self.baseline(Path(temp))
            previous, provenance = previous_snapshot(db, archive, self.spoken_revision,
                                                      self.classicua_revision)
            self.assertEqual(previous[43]["progress"]["text"], "Недоторканий.")
            self.assertEqual(previous[43]["progress"]["preserved_route"], "reviewed")
            generated = {42: {"accept": {
                "text": "Виправлений переклад.", "reviewed": False, "quick": True}},
                43: {"progress": {"text": "НЕ ПОВИНЕН З'ЯВИТИСЯ", "reviewed": False}},
                44: {"accept": {"text": "Новий непідтверджений.", "reviewed": False}}}
            result = merge_ready(previous, generated, {"q:42:accept"})
            self.assertEqual(result[42]["accept"]["text"], "Виправлений переклад.")
            self.assertEqual(result[42]["title"], "Назва")
            self.assertEqual(result[43]["progress"]["text"], old[43]["progress"]["text"])
            self.assertNotIn(44, result)
            self.assertEqual(provenance[("43:progress", "quests")][1], "reviewed")

    def test_only_adds_ready_moment(self):
        with TemporaryDirectory() as temp:
            archive, db, _ = self.baseline(Path(temp))
            previous, _ = previous_snapshot(db, archive, self.spoken_revision,
                                             self.classicua_revision)
            result = merge_ready(previous, {44: {"accept": {
                "text": "Доданий.", "reviewed": False, "quick": True}}},
                {"q:44:accept"})
            self.assertIn(42, result)
            self.assertIn(43, result)
            self.assertEqual(result[44]["accept"]["text"], "Доданий.")

    def test_rejects_changed_previous_zip_and_keeps_db_and_zip_untouched(self):
        with TemporaryDirectory() as temp:
            archive, db, _ = self.baseline(Path(temp))
            before = archive.read_bytes()
            with connection(db) as sql:
                original = list(sql.execute("SELECT snapshot_id FROM module_build_heads"))
            archive.write_bytes(before + b"tampered")
            with self.assertRaisesRegex(ValueError, "manager_quest_existing_zip_changed"):
                previous_snapshot(db, archive, self.spoken_revision,
                                  self.classicua_revision)
            with connection(db) as sql:
                self.assertEqual(list(sql.execute(
                    "SELECT snapshot_id FROM module_build_heads")), original)

    def test_390_quest_zip_is_reused_only_for_audited_upgrade(self):
        with TemporaryDirectory() as temp:
            archive, db, old = self.baseline(Path(temp), revision=LEGACY_REVISION)
            before = archive.read_bytes()
            with connection(db) as sql:
                original_snapshot = list(sql.execute(
                    "SELECT snapshot_id FROM module_build_heads"))
            recovered, provenance = previous_snapshot(
                db, archive, CURRENT_REVISION, self.classicua_revision)
            self.assertEqual(recovered[43]["progress"]["text"],
                             old[43]["progress"]["text"])
            self.assertEqual(provenance[("43:progress", "quests")][1], "reviewed")
            new = merge_ready(recovered, {44: {"accept": {
                "text": "Новий готовий.", "reviewed": False, "quick": True}}},
                {"q:44:accept"})
            self.assertEqual(new[42]["accept"]["text"], old[42]["accept"]["text"])
            self.assertEqual(new[43]["progress"]["text"], old[43]["progress"]["text"])
            self.assertEqual(new[44]["accept"]["text"], "Новий готовий.")

            # Incompatible target/source versions or tampered ZIPs still fail.
            with self.assertRaisesRegex(ValueError, "manager_quest_existing_zip_changed"):
                previous_snapshot(db, archive, "c" * 40, self.classicua_revision)
            with self.assertRaisesRegex(ValueError, "manager_quest_existing_zip_changed"):
                previous_snapshot(db, archive, CURRENT_REVISION, "d" * 40)
            archive.write_bytes(before + b"changed")
            with self.assertRaisesRegex(ValueError, "manager_quest_existing_zip_changed"):
                previous_snapshot(db, archive, CURRENT_REVISION, self.classicua_revision)
            with connection(db) as sql:
                self.assertEqual(list(sql.execute(
                    "SELECT snapshot_id FROM module_build_heads")), original_snapshot)

    def test_rejects_missing_ready_source(self):
        with self.assertRaisesRegex(ValueError, "manager_quest_ready_translation_missing"):
            merge_ready({42: {"accept": {
                "text": "Не змінювати.", "reviewed": False}}},
                {}, {"q:42:accept"})
