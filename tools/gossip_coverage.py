#!/usr/bin/env python3
"""Read-only NPC Gossip coverage against pinned Spoken and ClassicUA.

The numbers represent exact NPC-ID/English-hash lookup opportunities, not
approved Spoken mappings, translations visible in the game, or audio coverage.
Only metadata (NPC IDs/names/counts) is written to private ignored build/.
"""
import argparse
import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.build_ukrainian import local_gossip_texts
from tools.review_ui_server import build_state

CORPUS_PATH = "pipelines/quests/corpus/corpus.json.gz"
MODULUS = 4294967291
ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                            "abcdefghijklmnopqrstuvwxyz")


def classicua_hash(value):
    """Match ClassicUA get_text_hash and the in-game GossipFrame Lua code."""
    if not isinstance(value, str):
        return None
    value = re.sub(" +", " ", value.replace("\u00a0", " ")).strip(
        " \t\n\r\f\v").translate(ASCII_LOWER)
    value = value.translate(str.maketrans("ЇЄІҐ", "їєіґ"))
    if not value:
        return None
    data = value.encode("utf-8")
    count = 1
    for index in range(0, len(data), 3):
        fallback = len(data) - (index + 1) + 256  # Lua index starts at 1
        count = (
            (count * 8161) % 4294967279
            + data[index] * 16776193
            + (data[index + 1] if index + 1 < len(data) else fallback) * 8372226
            + (data[index + 2] if index + 2 < len(data) else fallback) * 3932164
        )
    return count % MODULUS


def audit_gossip_rows(lines, gossip):
    """Count distinct English wordings per NPC; deduplicate corpus variants.

    Spoken corpus provides NPC identity and English original text; ClassicUA
    holds hashes of current English text. Common hashes work for *any* NPC
    with a valid ID; NPC-specific hashes are scoped to their NPC.
    """
    if not isinstance(lines, list):
        raise ValueError("invalid_spoken_corpus_lines")
    if set(gossip) != {"byNpc", "common"}:
        raise ValueError("invalid_classicua_gossip_lookup")

    words = defaultdict(dict)
    total_rows = 0
    excluded_gossip_rows = 0
    empty_gossip_rows = 0
    for row in lines:
        if not isinstance(row, dict):
            raise ValueError("invalid_spoken_corpus_row")
        if row.get("source") != "gossip":
            continue
        total_rows += 1
        if row.get("npcType") not in ("creature", "vehicle") \
                or type(row.get("npcId")) is not int or row["npcId"] <= 0:
            excluded_gossip_rows += 1
            continue
        english = row.get("originalText")
        if not isinstance(english, str) or not english.strip():
            english = row.get("text")
        digest = classicua_hash(english)
        if digest is None:
            empty_gossip_rows += 1
            continue
        npc = row["npcId"]
        existing = words[npc].get(digest)
        name = row.get("npcName")
        if existing is None:
            words[npc][digest] = name if isinstance(name, str) else ""
        elif not existing and isinstance(name, str):
            words[npc][digest] = name

    missing = []
    covered_npcs = 0
    fully_covered = 0
    covered_texts = 0
    total_texts = 0
    npc_matches = 0
    common_matches = 0
    for npc, hashes in sorted(words.items()):
        explicit = gossip["byNpc"].get(npc, {})
        common = gossip["common"]
        npc_covered = 0
        for digest in hashes:
            if digest in explicit:
                npc_matches += 1
                npc_covered += 1
            elif digest in common:
                common_matches += 1
                npc_covered += 1
        total = len(hashes)
        uncovered = total - npc_covered
        covered_texts += npc_covered
        total_texts += total
        if npc_covered:
            covered_npcs += 1
        if npc_covered == total:
            fully_covered += 1
        if uncovered:
            missing.append({
                "npc_id": npc,
                "npc_name": next((name for name in hashes.values() if name), ""),
                "total_wordings": total,
                "covered_wordings": npc_covered,
                "untranslated_wordings": uncovered,
            })

    missing.sort(key=lambda row: (-row["untranslated_wordings"], row["npc_id"]))
    summary = {
        "corpus_gossip_rows": total_rows,
        "excluded_non_npc_gossip_rows": excluded_gossip_rows,
        "empty_npc_gossip_rows": empty_gossip_rows,
        "total_gossip_npcs": len(words),
        "covered_gossip_npcs": covered_npcs,
        "fully_covered_gossip_npcs": fully_covered,
        "partially_covered_gossip_npcs": covered_npcs - fully_covered,
        "untranslated_gossip_npcs": len(words) - covered_npcs,
        "total_distinct_npc_wordings": total_texts,
        "covered_distinct_npc_wordings": covered_texts,
        "untranslated_distinct_npc_wordings": total_texts - covered_texts,
        "wordings_matched_by_npc_hash": npc_matches,
        "wordings_matched_by_common_hash": common_matches,
        "classicua_explicit_npc_ids": len(gossip["byNpc"]),
        "classicua_explicit_hashes": sum(len(rows) for rows in gossip["byNpc"].values()),
        "classicua_common_hashes": len(gossip["common"]),
    }
    assert covered_texts == npc_matches + common_matches
    assert len(missing) == len(words) - fully_covered
    return summary, missing


def read_pinned_corpus(spoken_path, revision):
    """Read the frozen committed corpus, never an untracked working-tree copy."""
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("invalid_pinned_spoken_revision")
    path = Path(spoken_path)
    head = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()
    if head != revision:
        raise ValueError("pinned_spoken_revision_mismatch")
    data = subprocess.run(
        ["git", "-C", str(path), "show", revision + ":" + CORPUS_PATH],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    if not 0 < len(data) < 16 * 1024 * 1024:
        raise ValueError("invalid_spoken_corpus_size")
    corpus = json.loads(gzip.decompress(data))
    if not isinstance(corpus, dict) or not isinstance(corpus.get("lines"), list):
        raise ValueError("invalid_spoken_corpus")
    return corpus["lines"]


def run(classicua, spoken):
    lock = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))
    state = build_state(
        classicua, spoken, ROOT / "build/stage4b-decisions.json",
        None, ROOT / "build/stage3-ui-reviews.json",
        ROOT / "build/translation-reviews.json",
        ROOT / "config/translation_sources.json")
    if state.source.revision != lock["classicua"]["revision"] \
            or state.inventory.revision != lock["spoken"]["revision"]:
        raise ValueError("pinned_gossip_sources_mismatch")
    gossip = local_gossip_texts(state)
    lines = read_pinned_corpus(spoken, lock["spoken"]["revision"])
    summary, missing = audit_gossip_rows(lines, gossip)
    result = {
        "scope": "pinned_spoken_creature_npc_gossip_exact_classicua_hash",
        "not_representative_of": [
            "in_game_client_acceptance", "approved_mapping", "audio_coverage",
            "all_gossip_reply_options", "npc_quest_title_coverage",
        ],
        "spoken_revision": lock["spoken"]["revision"],
        "classicua_revision": lock["classicua"]["revision"],
        "summary": summary,
    }
    return result, missing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classicua", type=Path, required=True)
    parser.add_argument("--spoken", type=Path, required=True)
    args = parser.parse_args(argv)
    result, missing = run(args.classicua, args.spoken)
    output = ROOT / "build/gossip-coverage.json"
    worksheet = ROOT / "build/gossip-untranslated-npcs.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
                      + "\n", encoding="utf-8")
    with worksheet.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "npc_id", "npc_name", "total_wordings", "covered_wordings",
            "untranslated_wordings"])
        writer.writeheader()
        writer.writerows(missing)
    print("Gossip corpus (pinned revisions; exact English hash, no audio):")
    print(json.dumps(result["summary"], sort_keys=True, indent=2))
    print("Metadata-only report:", output)
    print("Untranslated NPC worksheet:", worksheet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
