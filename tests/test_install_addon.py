"""Local installer tests use synthetic private translations, never real corpora."""
from hashlib import sha256
from pathlib import Path
import os
import tempfile
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile, ZIP_STORED

from tools import build_ukrainian as builder
from tools import install_addon


class InstallAddonTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.addons = self.root / "Interface" / "AddOns"
        for name in ("Spoken", "Spoken_Quests"):
            folder = self.addons / name
            folder.mkdir(parents=True)
            (folder / (name + ".toc")).write_text("original official", encoding="utf-8")
        self.archive = self.root / "Spoken_Ukrainian_Quest_Local_Test.zip"
        self.files = builder.template_entries(builder.render_quest_lua({
            42: {"title": "Вигадана назва",
                 "accept": {"text": "Вигаданий текст", "reviewed": False}}},
            "a" * 40))
        self.write_archive()

    def write_archive(self):
        with ZipFile(self.archive, "w", compression=ZIP_STORED) as z:
            for name, data in sorted(self.files.items()):
                z.writestr(name, data)
        digest = sha256(self.archive.read_bytes()).hexdigest()
        self.archive.with_suffix(".zip.sha256").write_text(
            digest + "  " + self.archive.name + "\n", encoding="ascii")

    def test_install_updates_only_ukrainian_directories_and_preserves_official(self):
        result = install_addon.install(self.archive, self.addons)
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["replaced"], [])
        self.assertIsNone(result["backup"])
        for full_name, data in self.files.items():
            self.assertEqual((self.addons / full_name).read_bytes(), data)
        for name in ("Spoken", "Spoken_Quests"):
            self.assertEqual((self.addons / name / (name + ".toc")).read_text(),
                             "original official")
        self.assertFalse(any(p.name.startswith(".spoken-ukrainian-stage-")
                             for p in self.addons.iterdir()))

    def test_dry_run_checks_archive_without_writing_any_files(self):
        result = install_addon.install(self.archive, self.addons, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["replaced"], [])
        self.assertFalse((self.addons / "Spoken_Ukrainian").exists())
        self.assertFalse((self.addons / "Spoken_Quest_UA").exists())
        self.assertFalse((self.addons / ".spoken-ukrainian-backups").exists())

    def test_existing_ukrainian_folders_are_backed_up_before_replacing(self):
        for name in ("Spoken_Ukrainian", builder.QUEST_MODULE):
            folder = self.addons / name
            folder.mkdir()
            (folder / "old.txt").write_text("user original")
        result = install_addon.install(self.archive, self.addons)
        self.assertEqual(set(result["replaced"]), {"Spoken_Ukrainian", builder.QUEST_MODULE})
        self.assertTrue(result["backup"].is_dir())
        for name in ("Spoken_Ukrainian", builder.QUEST_MODULE):
            self.assertFalse((self.addons / name / "old.txt").exists())
            self.assertEqual((result["backup"] / name / "old.txt").read_text(),
                             "user original")
        for name in ("Spoken", "Spoken_Quests"):
            self.assertEqual((self.addons / name / (name + ".toc")).read_text(),
                             "original official")

    def test_legacy_addon_blocks_install_without_deletion(self):
        legacy = self.addons / "Spoken_Quests_UA"
        legacy.mkdir()
        marker = legacy / "user.lua"
        marker.write_bytes(b"user file")
        with self.assertRaisesRegex(install_addon.InstallError, "Legacy Spoken_Quests_UA"):
            install_addon.install(self.archive, self.addons)
        self.assertEqual(marker.read_bytes(), b"user file")
        self.assertFalse((self.addons / builder.QUEST_MODULE).exists())

    def test_gossip_installs_without_the_official_quest_module(self):
        self.files = builder.template_entries(gossip_lua=builder.render_gossip_lua(
            {"common": {}, "byNpc": {}}), module=builder.GOSSIP_MODULE)
        self.write_archive()
        (self.addons / "Spoken_Quests" / "Spoken_Quests.toc").unlink()
        result = install_addon.install(self.archive, self.addons)
        self.assertEqual(set(result["installed"]), {"Spoken_Ukrainian", builder.GOSSIP_MODULE})
        self.assertFalse((self.addons / builder.QUEST_MODULE).exists())

    def test_selected_module_must_match_archive_before_installation(self):
        with self.assertRaisesRegex(install_addon.InstallError, "archive_module_mismatch"):
            install_addon.install(self.archive, self.addons,
                                  expected_module=builder.GOSSIP_MODULE)
        self.assertFalse((self.addons / "Spoken_Ukrainian").exists())
        self.assertFalse((self.addons / "Spoken_Gossip_UA").exists())

    def test_corrupt_checksum_refuses_write(self):
        with self.archive.open("ab") as stream:
            stream.write(b"corrupted after build")
        with self.assertRaisesRegex(install_addon.InstallError,
                                    "archive_checksum_mismatch"):
            install_addon.install(self.archive, self.addons)
        self.assertFalse((self.addons / "Spoken_Ukrainian").exists())

    def test_unexpected_zip_member_and_traversal_refused_even_with_good_checksum(self):
        for bad in ("../Spoken/Spoken.toc", "Spoken_Quest_UA/evil.lua",
                    "Spoken_Quest_UA/Module.lua/extra"):
            with self.subTest(bad=bad):
                self.files[bad] = b"do not extract"
                self.write_archive()
                with self.assertRaisesRegex(install_addon.InstallError,
                                            "unexpected_zip_members"):
                    install_addon.install(self.archive, self.addons)
                self.assertFalse((self.addons / "Spoken_Ukrainian").exists())
                del self.files[bad]

    def test_rejects_wrong_destination_and_missing_official_module(self):
        with self.assertRaisesRegex(install_addon.InstallError, "AddOns_directory"):
            install_addon.install(self.archive, self.root)
        (self.addons / "Spoken_Quests" / "Spoken_Quests.toc").unlink()
        with self.assertRaisesRegex(install_addon.InstallError,
                                    "official_dependency_missing_Spoken_Quests"):
            install_addon.install(self.archive, self.addons)
        self.assertFalse((self.addons / "Spoken_Ukrainian").exists())

    def test_symlink_existing_addon_refused(self):
        fake = self.root / "outside"
        fake.mkdir()
        (self.addons / "Spoken_Quest_UA").symlink_to(fake, target_is_directory=True)
        with self.assertRaisesRegex(install_addon.InstallError,
                                    "unsafe_existing_destination"):
            install_addon.install(self.archive, self.addons)
        self.assertEqual(list(fake.iterdir()), [])

    def test_partial_failure_restores_original_without_touching_official(self):
        for name in ("Spoken_Ukrainian", builder.QUEST_MODULE):
            folder = self.addons / name
            folder.mkdir()
            (folder / "old.txt").write_text("old")
        actual_replace = os.replace
        count = 0

        def fail_third_move(source, dest):
            nonlocal count
            count += 1
            if count == 3:
                raise OSError("simulated second addon failure")
            return actual_replace(source, dest)

        with patch.object(install_addon.os, "replace", side_effect=fail_third_move):
            with self.assertRaisesRegex(install_addon.InstallError,
                                        "install_failed_rolled_back"):
                install_addon.install(self.archive, self.addons)
        for name in ("Spoken_Ukrainian", builder.QUEST_MODULE):
            self.assertEqual((self.addons / name / "old.txt").read_text(), "old")
            self.assertFalse((self.addons / name / (name + ".toc")).exists())
        for name in ("Spoken", "Spoken_Quests"):
            self.assertEqual((self.addons / name / (name + ".toc")).read_text(),
                             "original official")

    def test_installer_never_creates_or_modifies_addons_on_missing_zip(self):
        with self.assertRaisesRegex(install_addon.InstallError, "missing_or_unsafe_zip"):
            install_addon.install(self.root / "missing.zip", self.addons)
        self.assertEqual(sorted(p.name for p in self.addons.iterdir()),
                         ["Spoken", "Spoken_Quests"])


if __name__ == "__main__":
    import unittest
    unittest.main()
