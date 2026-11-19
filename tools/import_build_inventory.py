"""Annotate exactly the texts emitted in a local-test ZIP, without private bodies.

Counts are per displayed Quest moment and per Gossip NPC/hash. A single
English Gossip group used by multiple NPCs counts once per NPC/hash in the
built inventory. Other future modules remain zero until included in the pack.
"""
from collections import defaultdict
from hashlib import sha256
import json
import re

from adapters.import_statistics import QUEST_ID
from adapters.local_review_store import strict_json
from adapters.sqlite_translation_store import connection

QUEST_MOMENT = re.compile(r"q:([1-9][0-9]*):(accept|progress|complete)(?::.*)?\Z")


def collect_build_rows(state, preview, gossip, titles, reviewed_gossip,
                       selected_gossip, selected_quest, trusted_gossip, db_path,
                       machine_gossip=None, agent_rows=(), excluded_gossip=None):
    """Build a metadata-only manifest from the same selected texts as the ZIP."""
    rows = []
    by_moment = defaultdict(list)
    agent_gossip = {}
    for row in agent_rows:
        if row["domain"] == "quest":
            match = QUEST_MOMENT.fullmatch(row["target_id"])
            by_moment[int(match.group(1)), match.group(2)].append(
                (row["provider"], "agent_verified", row["text"]))
        else:
            agent_gossip[row["target_id"]] = row
    for ledger_name, route in (
            ("machine_imports", "machine_1to1"), ("translations", "reviewed")):
        ledger = getattr(state, ledger_name).file.data
        versions = {v["id"]: v for v in ledger["versions"]}
        for ref in ledger["imports"]:
            version = versions[ref["version_id"]]
            match = QUEST_MOMENT.fullmatch(ref["target_id"])
            if match is None:
                raise ValueError("build_import_unrecognized_quest_target")
            if route == "machine_1to1":
                source = "classicua"
            elif version["kind"] == "manual":
                source = "manual"
            else:
                provenance = {p["provider"] for p in version["provenance"]}
                source = next(iter(provenance)) if len(provenance) == 1 else "multiple"
            by_moment[int(match.group(1)), match.group(2)].append(
                (source, route, version["text"]))
    for selected in selected_quest:
        match = QUEST_MOMENT.fullmatch(selected["target_id"])
        if match is None:
            raise ValueError("build_import_invalid_selected_quest_target")
        by_moment[int(match.group(1)), match.group(2)].append(
            (selected["provider"], "source_selected", selected["ukrainian_text"]))
    for quest_id, events in preview.items():
        for event, value in events.items():
            if event not in ("accept", "progress", "complete"):
                continue  # Title and objective are a separate source-only field.
            text = value["text"]
            if "quick_source" in value:
                rows.append({"domain": "quests", "unit": f"{quest_id}:{event}",
                             "entity": str(quest_id), "source": value["quick_source"],
                             "route": "user_selected" if value.get("quick_selected") else "pinned_unique",
                             "text_sha256": sha256(text.encode("utf-8")).hexdigest()})
                continue
            if "review_source" in value:
                rows.append({"domain": "quests", "unit": f"{quest_id}:{event}",
                             "entity": str(quest_id), "source": value["review_source"], "route": "reviewed",
                             "text_sha256": sha256(text.encode("utf-8")).hexdigest()})
                continue
            contributions = [(source, route) for source, route, body
                             in by_moment.get((int(quest_id), event), ()) if body == text]
            if not contributions:
                raise ValueError("build_import_quest_provenance_missing")
            sources = sorted({c[0] for c in contributions})
            source = "+".join(sources)
            route = ("source_selected" if any(r == "source_selected" for _, r in contributions)
                     else "reviewed" if any(r == "reviewed" for _, r in contributions)
                     else "agent_verified" if any(r == "agent_verified" for _, r in contributions)
                     else "machine_1to1")
            rows.append({"domain": "quests", "unit": f"{quest_id}:{event}",
                         "entity": str(quest_id), "source": source, "route": route,
                         "text_sha256": sha256(text.encode("utf-8")).hexdigest()})

    reviews = {}
    if reviewed_gossip:
        with connection(db_path) as db:
            record = db.execute("""SELECT payload FROM ledger_documents
                WHERE ledger_name = 'gossip-translation-reviews.json'""").fetchone()
        if record is None:
            raise ValueError("build_import_gossip_review_ledger_unavailable")
        from tools.gossip_translation_review import validate_ledger
        ledger = validate_ledger(strict_json(record[0]))
        versions = {v["id"]: v for v in ledger["versions"]}
        reviews = {versions[i["version_id"]]["group_id"]:
                   versions[i["version_id"]]["provider"] for i in ledger["imports"]}
    selected = {}
    for row in selected_gossip:
        match = re.fullmatch(r"gossip:([1-9][0-9]*):([1-9][0-9]*)", row["target_id"])
        if not match:
            raise ValueError("build_import_gossip_selection_identity_invalid")
        selected[tuple(int(x) for x in match.groups())] = row["provider"]

    for hashed in sorted(gossip["common"]):
        agent = agent_gossip.get(f"gossip:common:{hashed}")
        rows.append({"domain": "gossip_common", "unit": f"common:{hashed}",
                     "entity": "common", "source": "classicua",
                     "route": ("agent_verified" if agent else
                               "machine_1to1" if machine_gossip is not None else "pinned_source")})
    for npc, translations in sorted(gossip["byNpc"].items()):
        for hashed in sorted(translations):
            key = (npc, hashed)
            if key in selected:
                source, route = selected[key], "source_selected"
            elif hashed in reviewed_gossip.get(npc, {}):
                proof = trusted_gossip.get(("gossip", f"gossip:{npc}:{hashed}"))
                if not proof or proof["english_sha256"] not in reviews:
                    raise ValueError("build_import_gossip_provenance_missing")
                source, route = reviews[proof["english_sha256"]], "reviewed"
            elif agent := agent_gossip.get(f"gossip:{npc}:{hashed}"):
                source, route = agent["provider"], "agent_verified"
            else:
                source, route = "classicua", ("machine_1to1" if machine_gossip is not None
                                             else "pinned_source")
            rows.append({"domain": "gossip", "unit": f"npc:{npc}:{hashed}",
                         "entity": str(npc), "source": source, "route": route})

    for faction, group in sorted(titles.items()):
        for quest_id in sorted(group):
            rows.append({"domain": "gossip_titles",
                         "unit": f"title:{faction}:{quest_id}",
                         "entity": str(quest_id),
                         "source": "classicua", "route": "pinned_source"})
    for (npc, hashed), source in sorted((excluded_gossip or {}).items()):
        rows.append({"domain": "gossip_excluded", "unit": f"npc:{npc}:{hashed}",
                     "entity": str(npc), "source": source, "route": "excluded"})
    for row in rows:
        if row["domain"] == "gossip":
            _, npc, hashed = row["unit"].split(":")
            text = gossip["byNpc"][int(npc)][int(hashed)]
        elif row["domain"] == "gossip_common":
            text = gossip["common"][int(row["unit"].split(":")[1])]
        else:
            continue
        row["text_sha256"] = sha256(text.encode("utf-8")).hexdigest()
    return rows
