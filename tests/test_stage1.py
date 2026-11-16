import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from zipfile import ZipFile

from lua_runtime import run_lua

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pack_build", ROOT / "tools/build.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
UPSTREAM = Path(os.environ.get("SPOKEN_SOURCE", ROOT.parent / "spoken-wow"))
LOCK = json.loads((ROOT / "sources.lock.json").read_text())


def git(*args):
    return subprocess.check_output(["git", "-C", str(UPSTREAM), *args])


def quote_lua(text):
    equals = "="
    while "]" + equals + "]" in text:
        equals += "="
    return "[" + equals + "[" + text + "]" + equals + "]"


def snapshot():
    paths = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")
    return {p: hashlib.sha256((UPSTREAM / p).read_bytes()).hexdigest()
            for p in paths if p and (UPSTREAM / p).is_file()}


class PackageTests(unittest.TestCase):
    def test_exact_structure_metadata_and_lua_files(self):
        source = ROOT / "addons" / builder.FOLDER
        self.assertEqual({p.name for p in source.iterdir()}, set(builder.FILES))
        metadata, files = builder.read_toc(source)
        self.assertEqual(metadata, builder.METADATA)
        self.assertEqual(files, ["Lore.lua"])
        for key in metadata:
            self.assertNotIn("Quests", key)
            self.assertNotIn("Readables", key)

    def test_archive_determinism_and_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            first, digest, size = builder.build(Path(temp) / "first.zip")
            second, other, _ = builder.build(Path(temp) / "second.zip")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(digest, other)
            self.assertEqual(size, len(first.read_bytes()))
            self.assertEqual(first.with_suffix(".zip.sha256").read_text().split()[0], digest)
            with ZipFile(first) as archive:
                names = [builder.FOLDER + "/" + n for n in sorted(builder.FILES)]
                self.assertEqual(archive.namelist(), names)
                self.assertIsNone(archive.testzip())
                for entry in archive.infolist():
                    self.assertEqual(entry.date_time, (1980, 1, 1, 0, 0, 0))
                    self.assertEqual(entry.compress_type, 0)
                    self.assertEqual(entry.external_attr >> 16, 0o100644)
                    self.assertEqual(archive.read(entry), (ROOT / "addons" / entry.filename).read_bytes())

    def test_rejects_unsafe_paths(self):
        for path in ["", "/tmp/file", "../file", builder.FOLDER + "/../file",
                     builder.FOLDER + "\\file", builder.FOLDER + "//file",
                     "Other/file", builder.FOLDER + "/C:file"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                builder.safe_path(path)

    def test_rejects_unexpected_assets_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / builder.FOLDER
            shutil.copytree(ROOT / "addons" / builder.FOLDER, source)
            extra = source / "unwanted.mp3"
            extra.write_bytes(b"")
            with self.assertRaises(ValueError):
                builder.build(Path(temp) / "out.zip", source)
            extra.unlink()
            lua = source / "Lore.lua"
            lua.unlink()
            lua.symlink_to(ROOT / "addons" / builder.FOLDER / "Lore.lua")
            with self.assertRaises(ValueError):
                builder.build(Path(temp) / "out.zip", source)

    def test_original_diagnostic_provenance(self):
        for path, digest in LOCK["diagnostic"]["files"].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)
        self.assertFalse(LOCK["diagnostic"]["audio"])
        self.assertEqual(LOCK["diagnostic"]["language"], "ukUA")

    def test_timestamp_independence(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / builder.FOLDER
            shutil.copytree(ROOT / "addons" / builder.FOLDER, source)
            first, _, _ = builder.build(Path(temp) / "first.zip", source)
            for item in source.iterdir():
                os.utime(item, (1700000000, 1700000000))
                item.chmod(0o600)
            second, _, _ = builder.build(Path(temp) / "second.zip", source)
            self.assertEqual(first.read_bytes(), second.read_bytes())


class PinnedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = snapshot()
        cls.sources = {}
        pin = LOCK["spoken"]["revision"]
        for path, expected in LOCK["spoken"]["files"].items():
            data = git("show", pin + ":" + path)
            if hashlib.sha256(data).hexdigest() != expected:
                raise AssertionError("Pinned source hash mismatch: " + path)
            cls.sources[path] = data.decode()
        meta, _ = builder.read_toc(ROOT / "addons" / builder.FOLDER)
        cls.script = "SOURCES = {}\n"
        for path, source in cls.sources.items():
            cls.script += "SOURCES[ " + quote_lua(path) + " ] = " + quote_lua(source) + "\n"
        cls.script += "META = {}\n"
        for key, value in meta.items():
            cls.script += "META[ " + quote_lua(key) + " ] = " + quote_lua(value) + "\n"
        cls.script += "FOLDER = " + quote_lua(builder.FOLDER) + "\n"
        cls.script += "PACK = " + quote_lua((ROOT / "addons" / builder.FOLDER / "Lore.lua").read_text()) + "\n"
        cls.script += (ROOT / "tests/contract.lua").read_text()

    @classmethod
    def tearDownClass(cls):
        if snapshot() != cls.before:
            raise AssertionError("Upstream checkout changed while tests ran")

    def test_pinned_map_identity_and_forever_interface(self):
        zones = json.loads(self.sources["pipelines/places/tools/seed/zones.json"])
        self.assertEqual(zones["1429"]["name"], "Elwynn Forest")
        forever = json.loads(self.sources["pipelines/places/tools/seed/forever-places.json"])
        self.assertIn("1429", forever["notOnForever"])
        self.assertIn("16001", self.sources["addons/Spoken_Places/Spoken_Places.toc"])
        self.assertIn("16001", self.sources["addons/Spoken/Spoken.toc"])

    def test_metadata_registration_menus_and_client_locale(self):
        run_lua(self.script + "\ncheck_registration()")

    def test_lore_registration_order_empty_subzones_and_text(self):
        run_lua(self.script + "\ncheck_registration_order()")

    def test_voice_text_separation_and_reload(self):
        run_lua(self.script + "\ncheck_separate_settings_and_reload()")

    def test_english_lore_ui_and_fallback_preserved(self):
        run_lua(self.script + "\ncheck_english_preserved()")

    def test_disabled_and_removed_pack(self):
        run_lua(self.script + "\ncheck_disabled_and_removed()")

    def test_missing_font_is_not_bypassed(self):
        run_lua(self.script + "\ncheck_font_guard()")

    def test_places_metadata_is_required(self):
        run_lua(self.script + "\ncheck_requires_places_declaration()")

    def test_no_audio_or_other_runtime_side_effects(self):
        run_lua(self.script + "\ncheck_no_audio()")

    def test_stage0_documents_preserved(self):
        for path, digest in LOCK["stage0_documents"].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
