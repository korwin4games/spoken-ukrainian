#!/usr/bin/env python3
"""Compare frozen Gossip sources without loading runtime code or review state."""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import gzip
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.classicua.lua import Lexer, Parser, Table, parse_file, parse_value
from adapters.classicua.source import GitSource, audit_checkout
from tools.build_ukrainian import local_gossip_texts
from tools.gossip_coverage import CORPUS_PATH, audit_gossip_rows, classicua_hash
from tools.gossip_translation_review import normalized

ALIAS_PATH = "pipelines/quests/corpus/gossip_aliases.json"
TOC_PATH = "addons/Spoken/Spoken.toc"
COMMENT = re.compile(r"\s*-- ?(.*)")
LINE_ID = re.compile(r"g:[a-f0-9]{32}(?::[mf])?")
DIRECT = ("exact_npc", "exact_common")
CANDIDATES = ("verified_alias_wording", "dynamic_candidate", "corpus_alternate_candidate",
              "reply_only_candidate", "glossary_candidate", "other_family_candidate", "wrong_npc_scope")
UNRESOLVED = ("missing_verified_original", "hash_collision", "ambiguous_npc_type", "no_evidence")


def wording(text):
    return normalized(text).translate(str.maketrans("ЇЄІҐ", "їєіґ"))


def source_comments(text, path):
    """Bind contiguous generator comments to parsed hash declaration lines."""
    table, _ = parse_file(text, "gossip", path)
    lines = text.split("\n")
    for scope in table.value.entries:
        if not isinstance(scope.value.value, Table):
            continue
        for entry in scope.value.value.entries:
            key = entry.key.value
            if type(key) is not int or entry.positional:
                continue
            index = entry.key.line - 2
            parts = []
            while index >= 0 and (match := COMMENT.fullmatch(lines[index])):
                parts.append(match[1].removesuffix("\r"))
                index -= 1
            english = "\n".join(reversed(parts))
            if not parts or classicua_hash(english) != key:
                raise ValueError(f"{path}:{entry.key.line}: English comment hash mismatch")
            yield {
                "scope": scope.key.value, "hash": key, "file": path,
                "key_line": entry.key.line, "value_line": entry.value.line,
                "column": entry.value.column, "comment_first_line": index + 2,
                "comment_last_line": entry.key.line - 1, "english": english,
                "translation_sha256": sha256(entry.value.value.encode("utf-8")).hexdigest()
                if isinstance(entry.value.value, str) else None,
            }


def dynamic_code(text, substitutions):
    text = text.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                                        "abcdefghijklmnopqrstuvwxyz"))
    for original, compressed in substitutions:
        text = text.replace(original, compressed)
    return "".join(word[0] + word[-1] for word in
                   re.findall(r"[a-z0-9][a-z0-9'-]*[a-z0-9]", text))


def dynamic_match(code, pattern):
    # Lua '.-' is a non-greedy wildcard repetition.
    if not 1 <= len(pattern) <= 42 or not re.fullmatch(r"(?:[a-z0-9]|\.-?)+", pattern):
        raise ValueError("Unexpected ClassicUA dynamic code syntax")
    return re.fullmatch(pattern.replace(".-", ".*?") +
                        (".*" if len(pattern) == 42 else ""), code) is not None


def replies(text):
    """Replicate the pinned reply-only article and final-period alternatives."""
    lowered = wording(text)
    stem = lowered.removesuffix(".")
    for prefix in ("the ", "a ", "an "):
        if lowered.startswith(prefix):
            stem = lowered[len(prefix):]
            break
    return {article + stem + suffix for article in ("", "the ", "a ", "an ")
            for suffix in ("", ".")} - {lowered}


def spoken_baseline(path, pin):
    blobs = {}
    for name, digest in pin["files"].items():
        blobs[name] = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(path), "show",
             f"{pin['revision']}:{name}"], check=True, capture_output=True).stdout
        if sha256(blobs[name]).hexdigest() != digest:
            raise ValueError(f"Spoken audit pin mismatch for {name}")
    if f"## Version: {pin['version']}" not in blobs[TOC_PATH].decode().splitlines():
        raise ValueError("Spoken audit version mismatch")
    return json.loads(gzip.decompress(blobs[CORPUS_PATH]))["lines"], json.loads(blobs[ALIAS_PATH])


def zip_inventory(path, effective):
    """Measure an existing local build, leaving the ZIP and build database untouched."""
    data = path.read_bytes()
    checksum = sha256(data).hexdigest()
    if path.with_suffix(".zip.sha256").read_text(encoding="utf-8").split()[0] != checksum:
        raise ValueError("Gossip ZIP checksum mismatch")
    with ZipFile(BytesIO(data)) as archive:
        members = [entry for entry in archive.namelist() if entry.endswith("/GossipTranslations.lua")]
        if len(members) != 1:
            raise ValueError("Expected one Gossip payload")
        text = archive.read(members[0]).decode("utf-8")
    marker = "\nSpokenUkrainian.GossipTexts = "
    table = parse_value(text.split(marker, 1)[1]).value
    npc = {(npc_id, key): entry.value.value
           for npc_id, group in table.get("byNpc").value.effective().items()
           for key, entry in group.value.value.effective().items()}
    common = {("!common", key): entry.value.value
              for key, entry in table.get("common").value.effective().items()}
    return {"sha256": checksum, "npc_hash_entries": len(npc), "common_hash_entries": len(common),
            "exact_classicua_payload_entries": sum(
                sha256(value.encode("utf-8")).hexdigest() == effective[key]["translation_sha256"]
                for key, value in (npc | common).items() if key in effective)}


def term_table(text, family, path):
    if family != "spell" or "addonTable.spell = {" in text:
        return parse_file(text, family, path)[0]
    parser = Parser(text, path)
    for token in ("local", "_", ",", "addonTable", "=", "...", "local"):
        parser.take(token)
    name = parser.token.value
    parser.take(name)
    parser.take("=")
    table = parser.value()
    for token in list(Lexer(f"for k, v in pairs({name}) do addonTable.spell[k] = v end").tokens())[:-1]:
        parser.take(token.value)
    parser.expect_end()
    return table


def glossary_terms(reader, order):
    """Read the manifest's static ID-keyed item and spell dictionaries."""
    effective = {"item": {}, "spell": {}}
    for path in order:
        stem = Path(path).stem
        family = "spell" if stem.startswith("spell_") else stem
        if not path.startswith("entries/") or family not in effective:
            continue
        table = term_table(reader.read(path), family, path)
        for key, entry in table.value.effective().items():
            english = entry.value.value.get("en")
            if english and (clean := wording(english.value)):
                effective[family][key] = (clean, {"family": family, "field": ["en"], "origin": {
                    "revision": reader.revision, "file": path, "line": english.line,
                    "column": english.column, "sha256": reader.hashes[path], "source_key": key}})
            else:
                effective[family].pop(key, None)
    for family in effective.values():
        yield from family.values()


def source_inventory(path, pin):
    dataset, report = audit_checkout(path, pin["files"], pin["revision"])
    reader = GitSource(path, pin["revision"])
    declarations = {}
    for file in report["loading_order"]:
        if not file.endswith("/gossip.lua"):
            continue
        for record in source_comments(reader.read(file), file):
            record["revision"] = pin["revision"]
            record["file_sha256"] = pin["files"][file]
            record["effective"] = False
            key = (file, record["value_line"], record["column"], record["scope"], record["hash"])
            declarations[key] = record
    effective, dynamic, other, glossary = {}, defaultdict(list), defaultdict(list), defaultdict(list)
    for family, records in dataset.records.items():
        for scope, record in records.items():
            for slot, leaf in record.fields.items():
                origin = leaf.origin
                if family == "gossip":
                    if len(slot) == 1 and type(slot[0]) is int:
                        declaration = declarations[origin.file, origin.line, origin.column, scope, slot[0]]
                        declaration["effective"] = True
                        effective[scope, slot[0]] = declaration
                    elif len(slot) == 2 and slot[0] == "!code":
                        dynamic[scope].append({"pattern": slot[1], "hash": leaf.node.value,
                                               "origin": asdict(origin)})
                elif slot == ("en",) or (isinstance(scope, str) and slot == ()):
                    english = leaf.node.value if slot else scope
                    if clean := wording(english):
                        evidence = {"family": family, "field": slot, "origin": asdict(origin)}
                        other[clean].append(evidence)
                        if family in ("object", "zone", "npc") or family.startswith("quest_"):
                            glossary[clean].append(evidence)
                            if family in ("object", "zone"):
                                alias = clean[4:] if clean.startswith("the ") and len(clean) > 8 else "the " + clean
                                glossary[alias].append(evidence)
    misc = "entries/misc.lua"
    if misc in report["loading_order"]:
        table, _ = parse_file(reader.read(misc), "misc", misc)
        for key, entry in table.value.effective().items():
            clean = wording(key)
            if clean and isinstance(entry.value.value, str):
                context = {"family": "misc", "origin": {
                    "revision": pin["revision"], "file": misc, "line": entry.value.line,
                    "column": entry.value.column, "sha256": reader.hashes[misc], "source_key": key}}
                other[clean].append(context)
                glossary[clean].append(context)
                alias = clean[4:] if clean.startswith("the ") and len(clean) > 8 else "the " + clean
                glossary[alias].append(context)
    for file in report["loading_order"]:
        if not file.endswith("/chat.lua"):
            continue
        text = reader.read(file)
        # Chat uses the same generated per-hash merge wrapper as Gossip.
        parsed = re.sub(r"addonTable\.chat\b", "addonTable.gossip", text)
        try:
            entries = list(source_comments(parsed, file))
        except ValueError as error:
            raise ValueError(f"{file}: unable to verify chat English evidence") from error
        for entry in entries:
            other[wording(entry["english"])].append({
                "family": "chat", "revision": pin["revision"],
                "file_sha256": reader.hashes[file], **entry})
    for clean, context in glossary_terms(reader, report["loading_order"]):
        other[clean].append(context)
        glossary[clean].append(context)
    # Reuse the original coverage tool's source filtering, independent of ledgers.
    lookup = local_gossip_texts(SimpleNamespace(
        dataset=dataset, source=SimpleNamespace(files=pin["files"], revision=pin["revision"]),
        policy=SimpleNamespace(allows_ai_transations=lambda provider: True)))
    utils = reader.read("scripts/utils.lua")
    block = utils.split("local known_gossip_dynamic_seq_with_multiple_words_for_get_text_code = {", 1)[1]
    substitutions = re.findall(r'\{"([^"]+)", "([^"]+)"\}', block.split("\n}", 1)[0])
    return list(declarations.values()), effective, dynamic, other, glossary, lookup, substitutions


def audit(lines, aliases, effective, dynamic, other, glossary, lookup, substitutions):
    rows, groups, by_id, by_stem, wordings_by_hash = (
        [], defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(set))
    for index, row in enumerate(lines):
        if row["source"] != "gossip":
            continue
        line_id = row["lineId"]
        if not LINE_ID.fullmatch(line_id):
            raise ValueError(f"Unexpected canonical Gossip ID at corpus index {index}")
        npc, kind = row["npcId"], row["npcType"]
        clean = wording(row["originalText"])
        digest = classicua_hash(row["originalText"])
        historical_digest = digest if digest is not None else classicua_hash(row.get("text"))
        target = {"corpus_index": index, **row}
        rows.append(target)
        by_id[line_id].append(target)
        by_stem[line_id.split(":")[1]].append(target)
        if clean:
            wordings_by_hash[digest].add(clean)
        if kind in ("creature", "vehicle") and type(npc) is int and npc > 0 and historical_digest is not None:
            groups[npc, historical_digest].append(target)
        else:
            target["audit_exclusion"] = "unsupported_context" if kind not in ("creature", "vehicle") or type(npc) is not int or npc <= 0 else "no_english"
    for (_, digest), declaration in effective.items():
        wordings_by_hash[digest].add(wording(declaration["english"]))
    scoped_sources = defaultdict(list)
    for (_, digest), declaration in effective.items():
        scoped_sources[digest].append(declaration)

    mapping = []
    for (npc, digest), members in sorted(groups.items()):
        clean = wordings_by_hash[digest]
        scopes = (npc, "!common")
        sources = [effective[scope, digest] for scope in scopes if (scope, digest) in effective]
        wrong_scope = [entry for entry in scoped_sources[digest] if entry["scope"] not in scopes]
        original = next((wording(row["originalText"]) for row in members if wording(row["originalText"])), "")
        ids = sorted({row["lineId"] for row in members})
        alternative, codes, reply, overlaps, terms = [], [], [], [], []
        edited_text = []
        if not original or any(not wording(row["originalText"]) for row in members):
            category = "missing_verified_original"
        elif len(clean) > 1:
            category = "hash_collision"
        elif len({row["npcType"] for row in members}) > 1:
            category = "ambiguous_npc_type"
        elif sources:
            category = "exact_npc" if sources[0]["scope"] == npc else "exact_common"
        else:
            for row in members:
                alternate = row["text"]
                if wording(alternate) == original:
                    continue
                for scope in scopes:
                    source = effective.get((scope, classicua_hash(alternate)))
                    if source and wording(source["english"]) == wording(alternate):
                        edited_text.append({"canonical_id": row["lineId"], "source": source})
            for line_id in ids:
                for alias in aliases.get(line_id.split(":")[1], []):
                    for row in by_stem.get(alias, []):
                        if row["npcId"] != npc or row["npcType"] not in {r["npcType"] for r in members}:
                            continue
                        alt = row["originalText"]
                        for scope in scopes:
                            source = effective.get((scope, classicua_hash(alt)))
                            if source and wording(source["english"]) == wording(alt) and len(wordings_by_hash[source["hash"]]) == 1:
                                alternative.append({"from": line_id, "to": row["lineId"], "source": source})
            code = dynamic_code(original, substitutions)
            for scope in scopes:
                for alias in dynamic.get(scope, []):
                    if dynamic_match(code, alias["pattern"]):
                        codes.append({**alias, "source": effective.get((scope, alias["hash"]))})
                for variant in sorted(replies(original)):
                    source = effective.get((scope, classicua_hash(variant)))
                    if source and wording(source["english"]) == variant:
                        reply.append(source)
            overlaps, terms = other.get(original, []), glossary.get(original, [])
            category = next((name for name, evidence in (
                ("verified_alias_wording", alternative), ("dynamic_candidate", codes),
                ("corpus_alternate_candidate", edited_text),
                ("reply_only_candidate", reply), ("glossary_candidate", terms),
                ("other_family_candidate", overlaps), ("wrong_npc_scope", wrong_scope))
                if evidence), "no_evidence")
        historical_route = ("npc" if digest in lookup["byNpc"].get(npc, {}) else
                            "common" if digest in lookup["common"] else "unmatched")
        mapping.append({"npc_id": npc, "hash": digest, "canonical_ids": ids,
                        "corpus_indices": [row["corpus_index"] for row in members],
                        "historical_route": historical_route, "category": category,
                        "exact_hash_sources": sources, "alternatives": alternative,
                        "corpus_alternate": edited_text,
                        "wrong_npc_scope": wrong_scope,
                        "dynamic": codes, "reply_only": reply, "glossary": terms,
                        "other_families": overlaps})
    summary, _ = audit_gossip_rows(lines, lookup)
    direct = [entry for entry in mapping if entry["category"] in DIRECT]
    totals = Counter(entry["category"] for entry in mapping)
    missing = Counter(entry["category"] for entry in mapping if entry["historical_route"] == "unmatched")
    if len(mapping) != summary["total_distinct_npc_wordings"] or sum(missing.values()) != summary[
            "untranslated_distinct_npc_wordings"]:
        raise ValueError("Historical and evidence denominators diverged")
    measures = {
        "historical": summary,
        "categories": {name: totals[name] for name in DIRECT + CANDIDATES + UNRESOLVED},
        "historically_unmatched_categories": {name: missing[name] for name in DIRECT + CANDIDATES + UNRESOLVED},
        "exclusions": dict(Counter(row["audit_exclusion"] for row in rows if "audit_exclusion" in row)),
        "npc_types": dict(Counter(str(row["npcType"]) for row in rows)),
        "speaker_genders": dict(Counter(str(row["gender"]) for row in rows)),
        "player_genders": dict(Counter(str(row["playerGender"]) for row in rows)),
        "voice_variants": len({row["voice"] for row in rows}),
        "unique_normalized_english": len({wording(row["originalText"]) for row in rows} - {""}),
        "canonical_ids": len(by_id),
        "direct_candidate_canonical_ids": len({key for entry in direct for key in entry["canonical_ids"]}),
        "direct_candidate_source_records": len({(entry["exact_hash_sources"][0]["scope"],
                                                entry["hash"]) for entry in direct}),
        "classicua_lookup_serializable_entries": len(lookup["common"]) + sum(map(len, lookup["byNpc"].values())),
        "rows_with_alternate_text": sum(row["text"] != row["originalText"] for row in rows),
        "rows_with_broadcast_text_id": sum(row.get("broadcastTextId") is not None for row in rows),
        "alias_stems": len(aliases),
    }
    return measures, rows, mapping


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("classicua", "spoken-390", "spoken-3101"):
        parser.add_argument("--" + arg, required=True, type=Path)
    parser.add_argument("--zip", type=Path, help="Count payload entries in an existing checksummed local ZIP")
    args = parser.parse_args()
    classicua = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))["classicua"]
    pins = json.loads((ROOT / "config/gossip_audit_baselines.json").read_text(encoding="utf-8"))
    declarations, *source = source_inventory(args.classicua, classicua)
    summary = {"classicua_revision": classicua["revision"],
               "comment_hash_checks": len(declarations),
               "comment_hash_checks_by_file": dict(Counter(row["file"] for row in declarations)),
               "effective_hash_entries": len(source[0]),
               "effective_dynamic_aliases": sum(map(len, source[1].values())),
               "spoken": {}}
    evidence = {"classicua_hash_declarations": declarations,
                "classicua_dynamic_aliases": list(source[1].items()), "spoken": {}}
    for version, path in (("3.9.0", args.spoken_390), ("3.10.1", args.spoken_3101)):
        lines, aliases = spoken_baseline(path, pins[version])
        counts, rows, mapping = audit(lines, aliases, *source)
        summary["spoken"][version] = {"revision": pins[version]["revision"], **counts}
        evidence["spoken"][version] = {"revision": pins[version]["revision"],
                                       "aliases": aliases, "rows": rows, "mapping": mapping}
    earlier, later = (evidence["spoken"][version] for version in ("3.9.0", "3.10.1"))
    summary["comparison"] = {
        "gossip_rows_identical": earlier["rows"] == later["rows"],
        "gossip_aliases_identical": earlier["aliases"] == later["aliases"],
    }
    if args.zip:
        summary["local_zip"] = zip_inventory(args.zip, source[0])
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    for filename, data in (("gossip-mapping-summary.json", summary),
                           ("gossip-mapping-evidence.json", evidence)):
        (build / filename).write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)
                                      + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
