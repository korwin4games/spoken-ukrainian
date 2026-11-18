"""Private import provenance reports: recorded approvals vs actual local-test ZIP.

Never count pending proposals as imports. Recorded reviewer imports are a live,
validated view over the *existing* authoritative SQLite ledgers; successful
builds also persist an immutable metadata-only inventory of embedded texts.
"""
from collections import defaultdict
from hashlib import sha256
import json
import re

from adapters.local_review_store import strict_json
from adapters.sqlite_translation_store import connection

CATEGORIES = ("quests", "gossip", "gossip_common", "gossip_titles", "places", "readables",
              "bosses", "compendium")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
QUEST_ID = re.compile(r"q:([1-9][0-9]*):(?:accept|progress|complete)(?::.*)?\Z")
ROUTES = frozenset({"machine_1to1", "reviewed", "source_selected", "pinned_source", "agent_verified"})
MAX_ROWS = 200000


def _group(rows):
    grouped = defaultdict(lambda: {"text_records": 0, "entities": set(), "texts": set(), "unknown": 0})
    totals = {category: 0 for category in CATEGORIES}
    for row in rows:
        domain, source, route = row["domain"], row["source"], row["route"]
        if domain not in CATEGORIES:
            raise ValueError("unknown_import_category")
        key = (domain, source, route)
        grouped[key]["text_records"] += 1
        grouped[key]["entities"].add(row["entity"])
        if row.get("text_sha256"):
            grouped[key]["texts"].add(row["text_sha256"])
        else:
            grouped[key]["unknown"] += 1
        totals[domain] += 1
    entries = [
        {"category": domain, "source": source, "route": route,
         "text_records": data["text_records"], "unique_entities": len(data["entities"]),
         "unique_translation_texts": len(data["texts"]), "unknown_text_fingerprints": data["unknown"]}
        for (domain, source, route), data in sorted(grouped.items())
    ]
    gossip_rows = [r for r in rows if r["domain"] in ("gossip", "gossip_common")]
    npc_rows = [r for r in gossip_rows if r["domain"] == "gossip" and
                (r["unit"].startswith("npc:") or r["unit"].startswith("gossip:"))]
    return {"total_text_records": len(rows), "categories": totals, "rows": entries,
            "gossip_counts": {
                "unique_translation_texts": len({r["text_sha256"] for r in gossip_rows if r.get("text_sha256")}),
                "npc_hash_occurrences": len({r["unit"].split(":", 1)[1] for r in npc_rows}),
                "distinct_npc_ids": len({r["entity"] for r in npc_rows}),
                "common_fallback_translations": len({r["unit"].rsplit(":", 1)[1]
                    for r in gossip_rows if r["domain"] == "gossip_common"}),
                "reviewed_english_groups": sum(r["domain"] == "gossip" and not
                    (r["unit"].startswith("npc:") or r["unit"].startswith("gossip:")) for r in gossip_rows),
                "unknown_text_fingerprints": sum(not r.get("text_sha256") for r in gossip_rows)}}


def recorded_rows(documents, selected=()):
    """Exactly one row per explicitly recorded target reference, no candidate counts."""
    result, keys = [], set()

    for ledger_name, category, route in (
            ("machine-one-to-one.json", "quests", "machine_1to1"),
            ("translation-reviews.json", "quests", "reviewed"),
            ("gossip-translation-reviews.json", "gossip", "reviewed")):
        doc = documents.get(ledger_name)
        if doc is None:
            continue
        versions = {row["id"]: row for row in doc["versions"]}
        for ref in doc["imports"]:
            version = versions[ref["version_id"]]
            if category == "quests":
                target = ref["target_id"]
                match = QUEST_ID.fullmatch(target)
                if match is None:
                    raise ValueError("invalid_import_statistics_quest_target")
                entity = match.group(1)
                if route == "machine_1to1":
                    source = "classicua"
                elif version["kind"] == "manual":
                    source = "manual"
                else:
                    origins = {p["provider"] for p in version["provenance"]}
                    source = next(iter(origins)) if len(origins) == 1 else "multiple"
            else:
                target = ref["group_id"]
                entity = target  # Gossip groups: NPC coverage needs a pinned corpus.
                source = version["provider"]
            ident = category, target
            if ident in keys:
                raise ValueError("duplicate_recorded_translation_import")
            keys.add(ident)
            result.append({"domain": category, "source": source, "route": route,
                           "unit": target, "entity": entity, "text_sha256": version["text_sha256"]})
    for selection in selected:
        category = "quests" if selection["domain"] == "quest" else "gossip"
        ident = category, selection["target_id"]
        # Source selections have a separate status from review imports and
        # may supersede existing embedded ClassicUA, but do not make an
        # unbuilt translation count as an installed text.
        result.append({"domain": category, "source": selection["provider"],
                       "route": "source_selected", "unit": selection["target_id"],
                       "text_sha256": selection.get("text_sha256", ""),
                       "entity": selection["target_id"].split(":")[1] if
                             category == "gossip" else
                             (QUEST_ID.fullmatch(selection["target_id"]).group(1)
                              if QUEST_ID.fullmatch(selection["target_id"]) else
                              selection["target_id"])})
    return result


def read_recorded_imports(db_path):
    """Validate current ledger shapes before grouping; no untrusted SQL counts."""
    from adapters.auto_one_to_one import validate_machine_ledger
    from adapters.translation_approvals import validate_ledger as validate_quests
    from tools.gossip_translation_review import validate_ledger as validate_gossip
    from adapters.gossip_machine import validate_ledger as validate_gossip_machine
    from adapters.translation_agent import recorded_imports

    validators = {
        "machine-one-to-one.json": validate_machine_ledger,
        "translation-reviews.json": validate_quests,
        "gossip-translation-reviews.json": validate_gossip,
        "gossip-machine-one-to-one.json": validate_gossip_machine,
    }
    documents = {}
    with connection(db_path) as db:
        db.execute("BEGIN")
        agent = list(recorded_imports(db))
        for ledger, payload in db.execute(
                """SELECT ledger_name, payload FROM ledger_documents
                   WHERE ledger_name IN (?, ?, ?, ?)""",
                tuple(validators)):
            documents[ledger] = validators[ledger](strict_json(payload))
        selected = db.execute("""SELECT c.domain, c.target_id, s.provider, c.text_sha256
            FROM source_active_selections a
            JOIN source_candidates c ON c.id = a.candidate_id
            JOIN source_snapshots s ON s.id = c.snapshot_id
            WHERE (SELECT d.decision FROM source_candidate_decisions d
                   WHERE d.candidate_id = c.id
                   ORDER BY d.id DESC LIMIT 1) = 'approved'""").fetchall()
    selected = [{"domain": domain, "target_id": target, "provider": provider, "text_sha256": text_sha}
                for domain, target, provider, text_sha in selected]
    rows = recorded_rows(documents)
    for row in agent:
        target = row["target_id"]
        entity = target.split(":")[1]
        domain = "quests" if row["domain"] == "quest" else (
            "gossip_common" if entity == "common" else "gossip")
        rows.append({"domain": domain, "unit": target, "entity": entity,
                     "source": row["provider"], "route": "agent_verified",
                     "text_sha256": row["text_sha256"]})
    machine = documents.get("gossip-machine-one-to-one.json", {"versions": [], "imports": []})
    versions = {r["id"]: r for r in machine["versions"]}
    for ref in machine["imports"]:
        row = versions[ref["version_id"]]
        scope, hashed = row["target_id"].split(":")[1:]
        rows.append({"domain": "gossip_common" if scope == "common" else "gossip",
                     "unit": row["target_id"], "entity": scope, "source": "classicua",
                     "route": "machine_1to1", "text_sha256": row["text_sha256"]})
    choices = recorded_rows({}, selected)
    return {"recorded_imports": _group(rows),
            "selected_not_necessarily_built": _group(choices)}


def _validate_build_rows(rows):
    if type(rows) is not list or len(rows) > MAX_ROWS:
        raise ValueError("invalid_build_inventory_rows")
    indexed = {}
    for row in rows:
        if type(row) is not dict or set(row) not in (
                {"domain", "unit", "entity", "source", "route"},
                {"domain", "unit", "entity", "source", "route", "text_sha256"}):
            raise ValueError("invalid_build_inventory_row")
        if "text_sha256" in row and (type(row["text_sha256"]) is not str
                                      or not HEX64.fullmatch(row["text_sha256"])):
            raise ValueError("invalid_build_inventory_text_fingerprint")
        if (row["domain"] not in CATEGORIES or row["route"] not in ROUTES
                or any(type(row[k]) is not str or not row[k] or len(row[k]) > 256
                       for k in ("unit", "entity", "source"))):
            raise ValueError("invalid_build_inventory_row")
        key = row["domain"], row["unit"]
        if key in indexed:
            raise ValueError("duplicate_build_inventory_unit")
        indexed[key] = row
    return [indexed[k] for k in sorted(indexed)]


def store_successful_build(db_path, *, artifact_sha256, spoken_revision,
                           classicua_revision, rows):
    """Persist metadata after a successful ZIP write, never before."""
    if (type(artifact_sha256) is not str or not HEX64.fullmatch(artifact_sha256)
            or any(type(x) is not str or not re.fullmatch(r"[a-f0-9]{40}", x)
                   for x in (spoken_revision, classicua_revision))):
        raise ValueError("invalid_build_inventory_revision")
    checked = _validate_build_rows(rows)
    payload = json.dumps([artifact_sha256, spoken_revision, classicua_revision,
                          checked], ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    fingerprint = sha256(payload).hexdigest()
    with connection(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            exists = db.execute(
                "SELECT id FROM build_import_snapshots WHERE fingerprint = ?",
                (fingerprint,)).fetchone()
            if exists is not None:
                snapshot_id = exists[0]
                new = False
            else:
                cur = db.execute("""INSERT INTO build_import_snapshots
                    (fingerprint, artifact_sha256, spoken_revision, classicua_revision)
                    VALUES (?, ?, ?, ?)""",
                    (fingerprint, artifact_sha256, spoken_revision, classicua_revision))
                snapshot_id = cur.lastrowid
                db.executemany("""INSERT INTO build_import_units
                    (snapshot_id, domain, unit_key, entity_key, source, route, text_sha256)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    [(snapshot_id, r["domain"], r["unit"], r["entity"],
                      r["source"], r["route"], r.get("text_sha256", "")) for r in checked])
                new = True
            db.execute("""INSERT INTO build_import_head(singleton, snapshot_id) VALUES(1, ?)
                ON CONFLICT(singleton) DO UPDATE SET snapshot_id=excluded.snapshot_id""", (snapshot_id,))
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return {"snapshot_id": snapshot_id, "new_snapshot": new, **_group(checked)}


def latest_successful_build(db_path):
    with connection(db_path) as db:
        head = db.execute("""SELECT id, artifact_sha256, spoken_revision,
            classicua_revision, created_at FROM build_import_snapshots
            WHERE id = (SELECT snapshot_id FROM build_import_head WHERE singleton=1)""").fetchone()
        if head is None:
            return None
        rows = [
            {"domain": d, "unit": u, "entity": e, "source": s, "route": r, "text_sha256": t}
            for d, u, e, s, r, t in db.execute("""SELECT domain, unit_key, entity_key,
                source, route, text_sha256 FROM build_import_units WHERE snapshot_id = ?""",
                                             (head[0],))]
    return {"snapshot_id": head[0], "artifact_sha256": head[1],
            "spoken_revision": head[2], "classicua_revision": head[3],
            "built_at": head[4], **_group(rows)}


def report(db_path):
    return {**read_recorded_imports(db_path),
            "latest_successful_build": latest_successful_build(db_path)}
