"""Private parameter tables for the residual cohort of the pinned Gossip audit."""
import csv
from collections import Counter, defaultdict
from hashlib import sha256
import json
import re
import sqlite3
import subprocess

from tools.gossip_translation_review import normalized

NPC_DB = "dev/database/classicua.db"
PLACEHOLDERS = {"n": "<name>", "c": "<class>", "r": "<race>"}


def npc_catalog(checkout, revision):
    data = subprocess.check_output(["git", "--no-replace-objects", "-C", str(checkout),
                                    "show", f"{revision}:{NPC_DB}"])
    names = defaultdict(list)
    conn = sqlite3.connect(":memory:")
    try:
        conn.deserialize(data)
        conn.execute("PRAGMA trusted_schema=OFF")
        conn.execute("PRAGMA query_only=ON")
        for npc, layer, name in conn.execute(
                "SELECT id, expansion, name FROM npcs WHERE expansion IN ('classic','sod','forever') "
                "ORDER BY id, expansion, name"):
            names[npc].append({"expansion": layer, "name": name})
    finally:
        conn.close()
    return names, sha256(data).hexdigest()


def template(text):
    """Compare player slots without expanding any player's attributes."""
    text = normalized(text).replace("$b", " ")
    text = re.sub(r"\$([ncr])", lambda m: PLACEHOLDERS[m[1]], text)
    return " ".join(text.split())


def tokens(template_text):
    """Looser comparison for review. Retain token order, player slots and numbers."""
    return tuple(re.findall(r"<[^<>\n]{1,40}>|\{\d+\}|\$[a-z]|\w+(?:['’]\w+)*", template_text))


def one_edit(a, b):
    """One insertion, deletion or substitution between two token sequences."""
    if min(len(a), len(b)) < 6 or abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    for i, (left, right) in enumerate(zip(a, b)):
        if left != right:
            if len(a) == len(b):
                return a[i + 1:] == b[i + 1:]
            return a[i:] == b[i + 1:]
    return len(a) != len(b)


def write_csv(path, fields, records):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict))
                             else v for k, v in row.items()})


def candidate_tables(directory, version, revision, rows, mapping, sources, dynamic, names):
    """Keep all original corpus rows and all scoped leads, including competing matches."""
    directory.mkdir(parents=True, exist_ok=True)
    by_length = defaultdict(list)
    catalog = []
    for key, source in sources.items():
        scope, digest = key
        source_template = template(source["english"])
        words = tokens(source_template)
        by_length[scope, len(words)].append((source_template, words, source))
        codes = [code for code in dynamic.get(scope, ()) if code["hash"] == digest]
        catalog.append({**source, "npc_catalog": names.get(scope, []), "dynamic_codes": codes})
    if catalog:
        write_csv(directory / "classicua.csv", list(catalog[0]), catalog)

    by_index = {row["corpus_index"]: row for row in rows}
    targets, links, pairs = [], [], []
    counts = Counter()
    speakers, scoped_speakers = set(), set()
    scopes = {scope for scope, _ in sources}
    for pair in mapping:
        if pair["category"] != "no_evidence":
            continue
        npc = pair["npc_id"]
        members = [by_index[i] for i in pair["corpus_indices"]]
        speaker_names = {normalized(row["npcName"]) for row in members}
        records = names.get(npc, [])
        known_names = {normalized(record["name"]) for record in records} - {""}
        if records:
            counts["pairs_with_catalog_id"] += 1
        if speaker_names & known_names:
            speakers.add(npc)
            counts["pairs_with_catalog_id_and_name"] += 1
        if npc in scopes:
            scoped_speakers.add(npc)
            counts["pairs_with_scoped_gossip"] += 1
        english = members[0]["originalText"]
        target_template = template(english)
        words = tokens(target_template)
        candidates = []
        for scope in (npc, "!common"):
            for size in (len(words) - 1, len(words), len(words) + 1):
                for source_template, other, source in by_length.get((scope, size), ()):
                    if target_template and target_template == source_template:
                        route = "same_template"
                    elif words and words == other:
                        route = "same_tokens"
                    elif one_edit(words, other):
                        route = "one_token_edit"
                    else:
                        continue
                    candidates.append((source, route))
        counts["residual_pairs"] += 1
        counts["pairs_with_text_lead"] += bool(candidates)
        counts["pairs_with_competing_text_leads"] += len(candidates) > 1
        for route in {route for _, route in candidates}:
            counts["pairs_" + route] += 1
        for row in members:
            targets.append({**row, "classicua_hash_of_original": pair["hash"], "revision": revision,
                            "classicua_npc_catalog": records, "has_scoped_gossip": npc in scopes,
                            "text_leads": len(candidates)})
        pairs.append({"npc_id": npc, "npc_names": sorted({r["npcName"] for r in members}),
                      "canonical_ids": pair["canonical_ids"], "corpus_indices": pair["corpus_indices"],
                      "spoken_original": english, "spoken_hash_of_original": pair["hash"],
                      "classicua_npc_catalog": records, "catalog_name_matches": bool(speaker_names & known_names),
                      "has_scoped_gossip": npc in scopes, "text_leads": len(candidates),
                      "classicua_candidates": [{"scope": s["scope"], "hash": s["hash"],
                                                "english": s["english"], "file": s["file"],
                                                "key_line": s["key_line"], "test": route}
                                               for s, route in candidates]})
        for source, route in candidates:
            links.append({"npc_id": npc, "spoken_hash_of_original": pair["hash"],
                          "canonical_ids": pair["canonical_ids"], "corpus_indices": pair["corpus_indices"],
                          "spoken_original": english, "test": route, "source_scope": source["scope"],
                          "source_hash": source["hash"], "source_original": source["english"],
                          "source_file": source["file"], "source_line": source["key_line"]})
    target_fields = sorted(set().union(*(r.keys() for r in rows)) | {
        "classicua_hash_of_original", "revision", "classicua_npc_catalog", "has_scoped_gossip", "text_leads"})
    write_csv(directory / f"spoken-{version}.csv", target_fields, targets)
    write_csv(directory / f"pairs-{version}.csv",
              ["npc_id", "npc_names", "canonical_ids", "corpus_indices", "spoken_original",
               "spoken_hash_of_original", "classicua_npc_catalog", "catalog_name_matches",
               "has_scoped_gossip", "text_leads", "classicua_candidates"], pairs)
    write_csv(directory / f"links-{version}.csv",
              ["npc_id", "spoken_hash_of_original", "canonical_ids", "corpus_indices", "spoken_original",
               "test", "source_scope", "source_hash", "source_original", "source_file", "source_line"], links)
    return {**counts, "corpus_rows": len(targets), "candidate_edges": len(links),
            "distinct_catalog_speakers_with_matching_name": len(speakers),
            "distinct_residual_speakers_with_scoped_gossip": len(scoped_speakers)}
