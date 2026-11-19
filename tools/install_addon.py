#!/usr/bin/env python3
"""Safely install the private Spoken Ukrainian test ZIP into WoW Interface/AddOns.

The original Spoken/Spoken_Quests are never changed. Existing Ukrainian
folders are backed up before replacement. Dry-run performs validation only.
Requires a local build; never downloads or publishes translations.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from zipfile import ZipFile, BadZipFile, ZIP_STORED

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = ROOT / "dist" / "Spoken_Quest_UA_Local_Test.zip"
EXPECTED = {
    "Spoken_Ukrainian": {"Spoken_Ukrainian.toc", "Core.lua"},
    "Spoken_Quest_UA": {
        "Spoken_Quest_UA.toc", "Translations.lua", "Module.lua", "NativeQuestFrame.lua",
        "GossipQuestTitles.lua",
    },
    "Spoken_Gossip_UA": {"Spoken_Gossip_UA.toc", "GossipTranslations.lua", "GossipFrame.lua"},
}
MAX_TOTAL_BYTES = 96 * 1024 * 1024
MAX_FILE_BYTES = 80 * 1024 * 1024


class InstallError(ValueError):
    """Invalid/untrusted input or blocked installation."""


def validate_archive(archive: Path):
    """Return verified members only. Never extract a ZIP using extractall()."""
    archive = archive.expanduser().absolute()
    checksum = archive.with_suffix(".zip.sha256")
    if not archive.is_file() or archive.is_symlink():
        raise InstallError("missing_or_unsafe_zip: build using tools/build_ukrainian.py first")
    if not checksum.is_file() or checksum.is_symlink():
        raise InstallError("missing_sha256_sidecar: use the original local build output")

    checksum_text = checksum.read_text(encoding="ascii").strip()
    match = re.fullmatch(r"([0-9a-f]{64})  ([^/\\\\\r\n]+\.zip)", checksum_text)
    if not match or match.group(2) != archive.name:
        raise InstallError("invalid_sha256_sidecar")
    archive_bytes = archive.read_bytes()
    actual = sha256(archive_bytes).hexdigest()
    if actual != match.group(1):
        raise InstallError("archive_checksum_mismatch")

    with ZipFile(BytesIO(archive_bytes)) as z:
        entries = z.infolist()
        folders = {entry.filename.split("/")[0] for entry in entries}
        modules = folders - {"Spoken_Ukrainian"}
        if len(modules) != 1 or "Spoken_Ukrainian" not in folders or folders - EXPECTED.keys():
            raise InstallError("unexpected_zip_members_or_duplicates")
        module = next(iter(modules))
        expected = {folder + "/" + name for folder in folders for name in EXPECTED[folder]}
        if (len(entries) != len(expected)
                or {entry.filename for entry in entries} != expected):
            raise InstallError("unexpected_zip_members_or_duplicates")
        total = 0
        result = {}
        for entry in entries:
            name = entry.filename
            parts = name.split("/")
            if (len(parts) != 2 or parts[0] not in EXPECTED
                    or parts[1] not in EXPECTED[parts[0]]
                    or entry.is_dir() or entry.flag_bits & 1
                    or entry.compress_type != ZIP_STORED
                    or (entry.external_attr >> 16) & 0o170000 == 0o120000):
                raise InstallError("unsafe_or_unsupported_zip_member")
            if entry.file_size > MAX_FILE_BYTES:
                raise InstallError("archive_member_too_large")
            total += entry.file_size
            if total > MAX_TOTAL_BYTES:
                raise InstallError("archive_too_large")
            result[name] = z.read(entry)  # verifies CRC
    toc = result[f"{module}/{module}.toc"].decode("utf-8").replace("\r\n", "\n")
    base = result["Spoken_Ukrainian/Spoken_Ukrainian.toc"].decode("utf-8").replace("\r\n", "\n")
    if ("## Title: Spoken Ukrainian\n" not in base
            or "## Dependencies: Spoken\n" not in base
            or (module == "Spoken_Quest_UA" and (
                "## Dependencies: Spoken, Spoken_Quests, Spoken_Ukrainian\n" not in toc
                or "## X-SpokenQuests-Language: ukUA\n" not in toc))
            or (module == "Spoken_Gossip_UA" and "## Dependencies: Spoken_Ukrainian\n" not in toc)):
        raise InstallError("addon_manifest_mismatch")
    return result


def validate_addons_dir(addons: Path, modules=("Spoken_Quest_UA",)):
    """Refuse missing/wrong folder and links; never modify upstream addons."""
    addons = addons.expanduser().absolute()
    if addons.is_symlink() or not addons.is_dir() or addons.name.lower() != "addons":
        raise InstallError("addons_must_be_existing_Interface_AddOns_directory")
    legacy = addons / "Spoken_Quests_UA"
    if legacy.exists() or legacy.is_symlink():
        raise InstallError("Legacy Spoken_Quests_UA detected. Close WoW and move that folder "
                           "outside Interface/AddOns before installing either new module. "
                           "Your translation database is separate.")
    for folder in ("Spoken", "Spoken_Quests") if "Spoken_Quest_UA" in modules else ("Spoken",):
        dep = addons / folder
        if dep.is_symlink() or not dep.is_dir() or not (dep / (folder + ".toc")).is_file():
            raise InstallError("official_dependency_missing_" + folder)
    for folder in EXPECTED:
        dest = addons / folder
        if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
            raise InstallError("unsafe_existing_destination_" + folder)
    backup_root = addons / ".spoken-ukrainian-backups"
    if backup_root.is_symlink() or (backup_root.exists() and not backup_root.is_dir()):
        raise InstallError("unsafe_existing_backup_directory")
    return addons


def install(archive: Path, addons: Path, *, dry_run=False):
    entries = validate_archive(Path(archive))
    expected_names = tuple(dict.fromkeys(member.split("/")[0] for member in entries))
    addons = validate_addons_dir(Path(addons), expected_names)
    replaced = [name for name in expected_names if (addons / name).exists()]
    if dry_run:
        return {"dry_run": True, "installed": list(expected_names),
                "replaced": replaced, "backup": None}

    backup = None
    backups = []
    activated = []
    with tempfile.TemporaryDirectory(prefix=".spoken-ukrainian-stage-", dir=addons) as td:
        staged = Path(td) / "new"
        staged.mkdir()
        for name in expected_names:
            (staged / name).mkdir()
        for member, data in entries.items():
            folder, filename = member.split("/")
            with (staged / folder / filename).open("xb") as stream:
                stream.write(data)

        try:
            validate_addons_dir(addons, expected_names)
            if replaced:
                backup_root = addons / ".spoken-ukrainian-backups"
                backup_root.mkdir(exist_ok=True)
                backup = Path(tempfile.mkdtemp(
                    prefix=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-"),
                    dir=backup_root))
            for name in expected_names:
                dest = addons / name
                if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
                    raise InstallError("destination_changed_during_install_" + name)
                if dest.exists():
                    os.replace(dest, backup / name)
                    backups.append(name)
                os.replace(staged / name, dest)
                activated.append(name)
        except (OSError, InstallError) as exc:
            try:
                for name in reversed(activated):
                    dest = addons / name
                    if dest.is_symlink() or not dest.is_dir():
                        raise InstallError("rollback_destination_changed_" + name)
                    shutil.rmtree(dest)
                for name in reversed(backups):
                    if (addons / name).exists() or (addons / name).is_symlink():
                        raise InstallError("rollback_conflicting_destination_" + name)
                    os.replace(backup / name, addons / name)
            except (OSError, InstallError) as rollback_exc:
                raise InstallError("install_failed_rollback_incomplete: "
                                   + str(rollback_exc)) from exc
            if backup and backup.exists() and not any(backup.iterdir()):
                backup.rmdir()
            raise InstallError("install_failed_rolled_back: " + str(exc)) from exc

    return {"dry_run": False, "installed": list(expected_names),
            "replaced": replaced, "backup": backup if replaced else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--addons", required=True, type=Path,
                        help="Real WoW Forever Interface/AddOns folder; must contain Spoken and Spoken_Quests")
    parser.add_argument("--archive", default=DEFAULT_ARCHIVE, type=Path,
                        help="Local-test ZIP created by tools/build_ukrainian.py")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate archive/target and list planned changes, without modifying files")
    args = parser.parse_args(argv)
    try:
        result = install(args.archive, args.addons, dry_run=args.dry_run)
    except (InstallError, BadZipFile, OSError, UnicodeError) as exc:
        print("Spoken Ukrainian installer failed: " + str(exc), file=sys.stderr)
        return 1
    prefix = "DRY RUN — would install" if result["dry_run"] else "Installed"
    print(prefix + ": " + ", ".join(result["installed"]))
    print("Existing Ukrainian addons to replace: "
          + (", ".join(result["replaced"]) if result["replaced"] else "none"))
    if result["backup"]:
        print("Backup of previous Ukrainian folders:", result["backup"])
    print("Official Spoken and Spoken_Quests left unchanged.")
    if not result["dry_run"]:
        print("Restart WoW Forever to load the updated addons (disable ClassicUA to test native QuestFrame).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
