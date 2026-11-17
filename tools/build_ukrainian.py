#!/usr/bin/env python3
"""Build a *local-test-only* Spoken Ukrainian + Spoken_Quests_UA ZIP.

ALWAYS re-audits pinned ClassicUA/Spoken and runs the explicit ClassicUA 1:1
import action before packaging. Generated Ukrainian translations are in ignored
dist/ only. Provisional text is for an opt-in, independent quest preview panel,
NOT the official audio-gated Spoken narrator/captions and NOT a release pack.
"""
import argparse
from collections import defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from zipfile import ZipFile, ZipInfo, ZIP_STORED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.auto_one_to_one import validate_machine_ledger
from adapters.translation_approvals import _validate_ledger
from adapters.spoken import PublicSource
from adapters.classicua.source import GitSource
from adapters.classicua.lua import Parser, Table
from tools.review_ui_server import build_state, validate_source_paths, _reason
from adapters.import_summary import format_import_table

DIST = ROOT / "dist"
ARCHIVE = DIST / "Spoken_Ukrainian_Quest_Local_Test.zip"
ADDON_FOLDERS = ("Spoken_Ukrainian", "Spoken_Quests_UA")
TEMPLATE_FILES = {
    "Spoken_Ukrainian": ("Spoken_Ukrainian.toc", "Core.lua"),
    "Spoken_Quests_UA": ("Spoken_Quests_UA.toc", "Module.lua"),
}
QUEST_TARGET = re.compile(r"q:([1-9][0-9]*):(accept|progress|complete)(?::.*)?\Z")
MAX_TEXT = 60000
UKRAINIAN_CASES = ("н", "р", "д", "з", "о", "м", "к")


def lua_quote(value):
    """Quote UTF-8 text as a Lua 5.1 literal, never as JSON/Python source."""
    if type(value) is not str or not value.strip() or len(value) > MAX_TEXT:
        raise ValueError("invalid_quest_translation_body")
    out = ['"']
    for char in value:
        code = ord(char)
        if char == "\\":
            out.append("\\\\")
        elif char == '"':
            out.append('\\"')
        elif char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        elif char == "\t":
            out.append("\\t")
        elif code < 32 or code == 127:
            out.append("\\%03d" % code)
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def current_quest_texts(state):
    """Only currently imported references after real full-source revalidation."""
    machine = validate_machine_ledger(state.machine_imports.file.data)
    reviewed = _validate_ledger(state.translations.file.data)
    version_by_id = {v["id"]: v for v in reviewed["versions"]}
    machine_by_id = {v["id"]: v for v in machine["versions"]}
    texts = {}
    for imports, versions, human in (
            (machine["imports"], machine_by_id, False),
            (reviewed["imports"], version_by_id, True)):
        for ref in imports:
            target_id = ref["target_id"]
            if target_id in texts:
                raise ValueError("duplicate_canonical_quest_import")
            if target_id not in state.inventory.targets:
                raise ValueError("unrecognized_canonical_quest_import")
            if state.inventory.targets[target_id].family != "quest":
                raise ValueError("unexpected_nonquest_import")
            if not QUEST_TARGET.fullmatch(target_id):
                raise ValueError("invalid_canonical_quest_id")
            row = versions[ref["version_id"]]
            if row["target_id"] != target_id:
                raise ValueError("quest_import_target_mismatch")
            if not human and row["decision"] != "machine_1to1_provisional":
                raise ValueError("machine_translation_not_provisional")
            if human and row["kind"] not in ("manual", "provider"):
                raise ValueError("invalid_human_import_version")
            if not row["text"].strip():
                raise ValueError("blank_quest_import")
            texts[target_id] = {"text": row["text"], "reviewed": human}

    # The preview only has QuestID and event from public WoW functions.
    # It cannot choose between different NPC voice / wording variants;
    # skip the whole moment when their texts conflict.
    moments = defaultdict(list)
    for target, data in texts.items():
        quest, event = QUEST_TARGET.fullmatch(target).groups()
        moments[(int(quest), event)].append(data)
    result = {}
    skipped = 0
    for (quest, event), rows in sorted(moments.items()):
        unique_texts = {row["text"] for row in rows}
        if len(unique_texts) != 1:
            skipped += len(rows)
            continue
        result.setdefault(quest, {})[event] = {
            "text": rows[0]["text"],
            "reviewed": all(row["reviewed"] for row in rows),
        }
    return result, len(texts), skipped


def read_classicua_inflections(classicua_path, source_files):
    """Read exact audited ClassicUA grammatical forms for a local preview.

    These are embedded only in the user's private ZIP. No ClassicUA Lua
    executes: the pinned data files are parsed as literal tables.
    """
    reader = GitSource(classicua_path)
    result = {}
    for kind in ("race", "class"):
        path = "entries/" + kind + ".lua"
        text = reader.read(path)
        if reader.hashes[path] != source_files.get(path):
            raise ValueError("classicua_grammar_source_hash_changed")
        # Grammar source files append executable compatibility loops and aliases
        # after their literal tables. Parse ONLY the pinned literal constructor,
        # never execute or attempt to interpret the trailing Lua statements.
        match = re.search(r"^addonTable\\." + kind + r"\\s*=\\s*(?=\\{)", text, re.MULTILINE)
        if match is None:
            raise ValueError("invalid_classicua_grammar_table")
        node = Parser(text[match.end():], path).value()
        if not isinstance(node.value, Table):
            raise ValueError("invalid_classicua_grammar_table")
        groups = {}
        for key, record in node.value.effective().items():
            if (type(key) is not str or not key
                    or not isinstance(record.value.value, Table)):
                raise ValueError("invalid_classicua_grammar_entry")
            forms = {}
            for case, values in record.value.value.effective().items():
                if case not in UKRAINIAN_CASES or not isinstance(values.value.value, Table):
                    continue
                seq = values.value.value.effective()
                male, female = seq.get(1), seq.get(2)
                if (male is None or female is None or
                        any(type(item.value.value) is not str or not item.value.value.strip()
                            or len(item.value.value) > 128 for item in (male, female))):
                    raise ValueError("invalid_classicua_gender_forms")
                forms[case] = (male.value.value, female.value.value)
            if "н" not in forms:
                raise ValueError("missing_classicua_nominative")
            groups[key] = forms
        if not groups:
            raise ValueError("missing_classicua_grammar_entries")
        result[kind] = groups
    return result


def render_quest_lua(preview, pinned_spoken_sha, inflections=None):
    if not re.fullmatch(r"[a-f0-9]{40}", pinned_spoken_sha):
        raise ValueError("invalid_spoken_pin")
    lines = [
        "-- GENERATED local test from pinned, audited Quest imports. Never edit.",
        "-- NOT RELEASE-READY. machine 1:1 entries lack human Stage 3 mapping review.",
        "-- No recordings, synthetic sound lengths or playback metadata.",
        "SpokenUkrainian = SpokenUkrainian or {}",
    ]
    # Private test build: embed ClassicUA declined race/class names.
    lines.append("SpokenUkrainian.Inflections = {")
    for kind, groups in sorted((inflections or {}).items()):
        if kind not in ("class", "race") or type(groups) is not dict:
            raise ValueError("invalid_build_inflection_group")
        lines.append("    [" + lua_quote(kind) + "] = {")
        for key, forms in sorted(groups.items()):
            lines.append("        [" + lua_quote(key) + "] = {")
            for case, pair in sorted(forms.items()):
                if case not in UKRAINIAN_CASES or len(pair) != 2:
                    raise ValueError("invalid_build_inflection_case")
                lines.append("            [" + lua_quote(case) + "] = {"
                             + lua_quote(pair[0]) + ", " + lua_quote(pair[1]) + "},")
            lines.append("        },")
        lines.append("    },")
    lines.append("}")
    lines.append("SpokenUkrainian.QuestTranslations = {")
    for quest, events in sorted(preview.items()):
        if type(quest) is not int or quest < 1:
            raise ValueError("invalid_quest_id")
        lines.append("    [%d] = {" % quest)
        for event in ("accept", "progress", "complete"):
            if event in events:
                row = events[event]
                lines.append("        %s = { text = %s, reviewed = %s }," % (
                    event, lua_quote(row["text"]),
                    "true" if row["reviewed"] else "false"))
        lines.append("    },")
    lines.append("}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def template_entries(preview_lua):
    entries = {}
    for folder in ADDON_FOLDERS:
        directory = ROOT / "addons" / folder
        expected = set(TEMPLATE_FILES[folder])
        if directory.is_symlink() or not directory.is_dir() or {
                p.name for p in directory.iterdir()} != expected:
            raise ValueError("unexpected_ukrainian_addon_template")
        for name in TEMPLATE_FILES[folder]:
            path = directory / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("unsafe_ukrainian_addon_template")
            entries[folder + "/" + name] = path.read_bytes()
    base_toc = entries["Spoken_Ukrainian/Spoken_Ukrainian.toc"].decode("utf-8")
    quest_toc = entries["Spoken_Quests_UA/Spoken_Quests_UA.toc"].decode("utf-8")
    for required in (
            "## Title: Spoken Ukrainian\n",
            "## Dependencies: Spoken\n",
            "Core.lua\n"):
        if required not in base_toc:
            raise ValueError("missing_base_ukrainian_toc_contract")
    for required in (
            "## Title: Spoken Ukrainian: Quests\n",
            "## Dependencies: Spoken, Spoken_Quests, Spoken_Ukrainian\n",
            "## LoadOnDemand: 1\n",
            "## X-SpokenQuests-DataModule-Version: 1\n",
            "## X-SpokenQuests-Language: ukUA\n",
            "Translations.lua\nModule.lua\n"):
        if required not in quest_toc:
            raise ValueError("missing_quest_ukrainian_toc_contract")
    # Module must never invent sound files or call AddOn playback.
    module = entries["Spoken_Quests_UA/Module.lua"].decode("utf-8")
    if not ('quests:Register("Spoken_Quests_UA"' in module
            and "SoundLengthLookupByFileName = {}" in module
            and "QUEST_DETAIL" in module):
        raise ValueError("missing_quest_pack_registration")
    entries["Spoken_Quests_UA/Translations.lua"] = preview_lua
    return entries


def write_zip(entries, destination=ARCHIVE):
    """Deterministic, fail-closed and atomic private local-test ZIP."""
    destination = Path(destination).resolve()
    if destination.parent != DIST.resolve() or destination.suffix != ".zip":
        raise ValueError("zip_output_must_be_under_ignored_dist")
    if any(part in ("..", "") for part in destination.parts):
        raise ValueError("unsafe_output_path")
    if DIST.is_symlink() or destination.is_symlink():
        raise ValueError("unsafe_dist_symlink")
    DIST.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")
    if temp.exists() or temp.is_symlink():
        raise ValueError("old_temporary_build_file")
    try:
        with ZipFile(temp, "w", compression=ZIP_STORED) as archive:
            for name, content in sorted(entries.items()):
                if (name.startswith("/") or "\\" in name or ".." in name.split("/")
                        or name.split("/")[0] not in ADDON_FOLDERS):
                    raise ValueError("unsafe_ukrainian_archive_name")
                item = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                item.create_system = 3
                item.external_attr = 0o100644 << 16
                archive.writestr(item, content)
        os.replace(temp, destination)
    finally:
        if temp.exists():
            temp.unlink()
    sha = sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(
        sha + "  " + destination.name + "\n", encoding="ascii")
    return destination, sha


def build(classicua, spoken):
    """Auto-import is mandatory; there is no build-without-import switch."""
    classicua, spoken = Path(classicua), Path(spoken)
    validate_source_paths(classicua, spoken)
    state = build_state(
        classicua, spoken,
        ROOT / "build/stage4b-decisions.json",
        None,
        ROOT / "build/stage3-ui-reviews.json",
        ROOT / "build/translation-reviews.json",
        ROOT / "config/translation_sources.json")
    # Explicitly call the *same* guarded UI/CLI action. Re-check current
    # canonical mappings, source bytes, rights policy and source versions.
    report_action = state.translation_action(
        "auto_import_one_to_one", {"source": "classicua"})
    report = report_action["report"]
    preview, imported, ambiguous = current_quest_texts(state)
    preview_count = sum(map(len, preview.values()))
    if not preview_count:
        raise ValueError("no_unambiguous_quest_imports_for_local_test_pack")
    forms = read_classicua_inflections(classicua, state.source.files)
    entries = template_entries(render_quest_lua(preview, state.inventory.revision, forms))
    artifact, digest = write_zip(entries)
    return {
        "artifact": artifact, "sha256": digest,
        "reported_total_spoken": report["total_spoken_records"],
        "imported_quest_records": imported,
        "previewable_quest_moments": preview_count,
        "skipped_ambiguous_preview_variants": ambiguous,
        "machine_provisional": report["machine_one_to_one_imported"],
        "human_reviewed": report["human_reviewed_imported_total"],
        "report": report,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classicua", type=Path, required=True,
                        help="Local CLEAN Git checkout at sources.lock.json pinned ClassicUA commit")
    parser.add_argument("--spoken", type=Path, required=True,
                        help="Local CLEAN Git checkout at sources.lock.json pinned Spoken commit")
    args = parser.parse_args(argv)
    print("Spoken Ukrainian local TEST build: running mandatory ClassicUA 1:1 auto-import...",
          flush=True)
    try:
        result = build(args.classicua, args.spoken)
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print("Quest build failed reason=" + _reason(exc), file=sys.stderr)
        return 1
    print(format_import_table(result["report"]))
    print("Quest records imported:", result["imported_quest_records"])
    print("Quest moments safe to preview:", result["previewable_quest_moments"])
    print("Skipped ambiguous voice/wording variants:",
          result["skipped_ambiguous_preview_variants"])
    print("Local test ZIP:", result["artifact"])
    print("SHA-256:", result["sha256"])
    print("NOT a release: no recorded audio and NO replacement of Spoken narrator captions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
