"""Private read model joining pinned originals, review evidence and ZIP inventory."""
from collections import Counter, defaultdict

from adapters.auto_one_to_one import EVENT_POSITION, machine_candidates
from adapters.crosswalk import digest
from adapters.source_revision_store import SourceReviewStore, sha
from adapters.sqlite_translation_store import connection
from adapters.translation_agent import QUEST, assessment_rows, recorded_imports
from adapters.translation_approvals import status as quest_status
from tools.gossip_coverage import classicua_hash, read_pinned_corpus
from tools.gossip_machine_import import GossipMachineImport
from tools.gossip_translation_review import normalized, version_status
from tools.translation_manager import MODULE, file_stamp


STATUS_HELP = {
    "ready": "Переклад пройшов перевірки для локального імпорту. Запустіть переімпорт модуля.",
    "missing": "Перекладу для цього контексту немає. Відкрийте розширену перевірку, щоб підготувати переклад.",
    "review": "Для цього перекладу бракує чинної перевірки, дозволу або підтвердженого зіставлення.",
    "conflict": "Є неоднозначні варіанти. Звірте оригінали й джерела в розширеній перевірці.",
    "rejected": "Збережено рішення відхилити або відкласти переклад. Перегляньте рішення вручну.",
    "invalid": "Бракує перевіреного оригіналу або не підтримується контекст чи формат. Перевірте джерела.",
    "stale": "Попередні докази змінилися. Перевірте відповідність і версію джерела.",
}


def latest_units(db, archive, spoken_revision, classicua_revision):
    db.execute("BEGIN")
    try:
        head = db.execute("""SELECT s.id, s.artifact_sha256, s.created_at
            FROM build_import_head h JOIN build_import_snapshots s ON s.id=h.snapshot_id
            WHERE h.singleton=1 AND s.spoken_revision=? AND s.classicua_revision=?""",
            (spoken_revision, classicua_revision)).fetchone()
        if not head or file_stamp(archive) != head[1]:
            return {}, None
        rows = db.execute("""SELECT domain, unit_key, source, route, text_sha256
            FROM build_import_units WHERE snapshot_id=?""", (head[0],)).fetchall()
        return {(domain, key): {"source": source, "route": route, "text_sha256": fingerprint}
                for domain, key, source, route, fingerprint in rows}, {"sha256": head[1], "built_at": head[2]}
    finally:
        db.rollback()


class ModuleInventory:
    def __init__(self, rows, build, units):
        self.rows = {r["id"]: r for r in rows}
        self.build = build
        self.units = units

    def summary(self):
        result = {}
        for kind in ("quest", "gossip"):
            rows = [r for r in self.rows.values() if r["type"] == kind]
            counts = Counter(r["status"] for r in rows)
            pending = Counter(r["status"] for r in rows if r["built"] is None)
            built = sum(r["built"] is not None for r in rows)
            result[kind] = {"total": len(rows), "included": built, "not_included": len(rows) - built,
                            "recorded": sum(r["recorded"] for r in rows),
                            "conflicts": counts["conflict"], "missing": counts["missing"],
                            "ready": sum(r["status"] == "ready" and not r["built"] for r in rows),
                            "pending_review": pending["review"] + pending["stale"],
                            "not_included_by_status": dict(pending),
                            "by_status": dict(counts)}
        result["gossip_archive_units"] = {
            "npc_hash_pairs": sum(domain == "gossip" for domain, _ in self.units),
            "common_hashes": sum(domain == "gossip_common" for domain, _ in self.units),
        }
        return result

    def page(self, *, module=MODULE, query="", kind="all", filter_by="all", status="all", offset=0, limit=30):
        if (module != MODULE or kind not in ("all", "quest", "gossip")
                or filter_by not in ("all", "imported", "not_imported", "conflicts")
                or status not in ("all", *STATUS_HELP)
                or type(query) is not str or len(query) > 200
                or type(offset) is not int or offset < 0
                or type(limit) is not int or not 1 <= limit <= 100):
            raise ValueError("manager_invalid_filters")
        needles = query.casefold().split()
        matches = []
        for row in self.rows.values():
            if kind not in ("all", row["type"]) or status not in ("all", row["status"]):
                continue
            if filter_by == "imported" and not row["built"] or filter_by == "not_imported" and row["built"]:
                continue
            if filter_by == "conflicts" and row["status"] != "conflict":
                continue
            if needles:
                text = " ".join([row["id"], row["label"], *row["originals"],
                                 *(c["text"] for c in row["candidates"])]).casefold()
                if not all(word in text for word in needles):
                    continue
            matches.append({k: row[k] for k in ("id", "type", "label", "status", "built", "recorded")})
        return {"module": module, "summary": self.summary(), "build": self.build,
                "total": len(matches), "items": matches[offset:offset + limit]}

    def detail(self, *, module=MODULE, identity):
        if module != MODULE or type(identity) is not str or identity not in self.rows:
            raise ValueError("manager_item_not_found")
        row = self.rows[identity]
        help_text = ("Переклад доступний у перевіреній локальній збірці."
                     if row["status"] == "ready" and row["built"] else STATUS_HELP[row["status"]])
        return {**row, "help": help_text}


def review_candidate(text, source, reference, revision, review):
    return {"text": text, "provider": source, "reference": reference,
            "revision": revision, "review": review, "sha256": sha(text)}


def imported_ids(ledger):
    return {entry["version_id"] for entry in ledger["imports"]}


def status_for(originals, candidates, *, conflict=False, ready=False, unsupported=False):
    if conflict:
        return "conflict"
    if not originals or unsupported:
        return "invalid"
    if ready:
        return "ready"
    if not candidates:
        return "missing"
    reviews = {r["review"] for r in candidates}
    if reviews <= {"rejected", "deferred", "candidate"} and reviews & {"rejected", "deferred"}:
        return "rejected"
    if "stale" in reviews or "pending_update" in reviews:
        return "stale"
    return "review"


def load_inventory(classicua, spoken, db_path, archive, *, skipped=(), state=None):
    from tools.build_ukrainian import local_gossip_texts
    from tools.review_ui_server import build_state

    if state is None:
        state = build_state(classicua, spoken, state_path("stage4b-decisions.json"),
                            local_reviews_path=state_path("stage3-ui-reviews.json"),
                            translations_path=state_path("translation-reviews.json"))
    lines = read_pinned_corpus(spoken, state.inventory.revision)
    originals = state.original_index.original_english
    glossary = {}
    contexts = defaultdict(dict)
    for line in lines:
        identity = line.get("lineId")
        glossary[identity] = line
        if line.get("source") == "gossip" and identity in state.inventory.targets:
            english = line.get("originalText")
            if isinstance(english, str) and english.strip() and any(
                    ctx["wording_sha256"] == digest(english)
                    for ctx in state.inventory.contexts.get(identity, ())):
                normalized_english = normalized(english).translate(str.maketrans("ЇЄІҐ", "їєіґ"))
                key = (line.get("npcId"), classicua_hash(english), sha(normalized_english))
                contexts[key][identity] = (english, line.get("npcName"), line.get("npcType"))

    gossip_rows, placements, _, blocked, manual = GossipMachineImport(state, spoken).inspect(revalidate=False)
    raw_gossip = local_gossip_texts(state)
    gossip_machine = state_path("gossip-machine-one-to-one.json")
    quest_versions = state.translations.file.data
    quest_machine = state.machine_imports.file.data
    with connection(db_path) as db:
        units, build = latest_units(db, archive, state.inventory.revision, state.source.revision)
        agent = list(recorded_imports(db))
        assessments = assessment_rows(db, latest=True)
        from adapters.gossip_machine import EMPTY, validate_ledger
        from adapters.local_review_store import strict_json
        saved = db.execute("SELECT payload FROM ledger_documents WHERE ledger_name=?", (gossip_machine.name,)).fetchone()
        gm = validate_ledger(strict_json(saved[0])) if saved else EMPTY
        source_selected = {r[0] for r in db.execute("SELECT candidate_id FROM source_active_selections")}

    indexed_quest = defaultdict(list)
    indexed_gossip = defaultdict(list)
    for ledger, method in ((quest_versions, "reviewed"), (quest_machine, "machine_1to1")):
        imported = imported_ids(ledger)
        for row in ledger["versions"]:
            indexed_quest[row["target_id"]].append((row, row["id"] in imported, method))
    for ledger, method in ((manual, "reviewed"), (gm, "machine_1to1")):
        imported = imported_ids(ledger)
        for row in ledger["versions"]:
            indexed_gossip[row.get("group_id", row.get("target_id"))].append(
                (row, row["id"] in imported, method))

    candidate_sources = defaultdict(list)
    store = SourceReviewStore(db_path)
    for source in store.candidates():
        candidate_sources[source["target_id"]].append(source)
    agent_targets = {r["target_id"] for r in agent}
    assessment_index = defaultdict(dict)
    for review in assessments:
        c = review["candidate"]
        assessment_index[c["target_id"]].setdefault(c["text_sha256"], review)
    skipped_ids = {key: reason for key, reason in skipped}

    def decorate(entry, targets, built, choices, recorded, status, **extra):
        for choice in choices:
            score = next((assessment_index[key].get(choice["sha256"]) for key in targets
                          if choice["sha256"] in assessment_index[key]), None)
            if score:
                choice["validation"] = score["status"]
                choice["checks"] = score["checks"]
        # Preserve different review decisions for the same source text.
        choices = list({(r["sha256"], r["provider"], r["reference"], r["review"]): r
                        for r in choices}.values())
        reason = next((skipped_ids[key] for key in targets if key in skipped_ids), None)
        if reason and "conflict" in reason:
            status = "conflict"
        return {**entry, "status": status, "built": built, "candidates": choices,
                "recorded": recorded, "problem": reason, **extra}

    def external(target, choices):
        for source in candidate_sources[target]:
            is_active = source["id"] in source_selected
            choices.append(review_candidate(source["ukrainian_text"], source["provider"],
                source["source_ref"], source["revision"], "source_selected" if is_active else "candidate"))

    hints = defaultdict(list)
    for hint in state._hints:
        for target in hint["candidates"]:
            hints[target].append(hint["source_id"])
    enabled = state.policy.auto_approves_one_to_one("classicua")
    q_auto = {r["target_id"] for r in machine_candidates(
        state.dataset, state.source, state.inventory, state.original_index, state._hints,
        allow_ai_transations=state.policy.allows_ai_transations("classicua"))} if enabled else set()
    observations = state.translation_observations()
    review_ready = {r["target_id"] for r in state.translations.eligible(
        observations, state.policy, skipped=[])}
    quest_groups = defaultdict(list)
    for target, item in state.inventory.targets.items():
        match = QUEST.fullmatch(target) if item.family == "quest" else None
        if match:
            quest_groups[match.group(1)].append(target)
    rows = []
    for moment, targets in sorted(quest_groups.items(), key=lambda x: (int(x[0].split(":")[1]), x[0])):
        _, quest_id, event = moment.split(":")
        title = next((glossary.get(target, {}).get("questTitle") for target in targets
                      if glossary.get(target, {}).get("questTitle")), f"Quest {quest_id}")
        english = sorted({originals[target] for target in targets if target in originals})
        choices = []
        recorded = ready = False
        for target in targets:
            ready |= target in review_ready or target in q_auto and not any(
                method == "reviewed" or r.get("decision") == "pending_update"
                for r, _, method in indexed_quest[target])
            external(target, choices)
            recorded |= target in agent_targets
            for r, saved, method in indexed_quest[target]:
                p = r.get("provenance", [{}])[0]
                choices.append(review_candidate(r["text"], p.get("provider", "classicua" if method == "machine_1to1" else "manual"),
                    p.get("source_ref", r.get("source_file", r["source_id"])),
                    p.get("revision", r.get("source_revision")), quest_status(r) if method == "reviewed" else r["decision"]))
                recorded |= saved
            for source_id in hints[target]:
                unit = state.source.units[source_id]
                _, faction, number, source_event = source_id.split(":")
                record = state._views[faction].get(int(number))
                field = record.fields.get((EVENT_POSITION[source_event],)) if record else None
                if field and isinstance(field.node.value, str) and sha(field.node.value) == unit.effective_sha256:
                    choices.append(review_candidate(field.node.value, "classicua", unit.origin_file,
                                                    unit.source_revision, "candidate"))
        built = units.get(("quests", f"{quest_id}:{event}"))
        conflict = (not built and len({r["sha256"] for r in choices}) > 1 and
                    len({r["sha256"] for r in choices if r["review"] not in ("rejected", "deferred")}) > 1
                    and (len(targets) > 1 or not ready))
        rows.append(decorate({"id": moment, "type": "quest", "label": title, "originals": english},
                    targets + [moment], built, choices, recorded,
                    status_for(english, choices, conflict=conflict, ready=ready),
                    quest_id=quest_id, event=event, contexts=[c for t in targets for c in state.inventory.contexts[t]]))

    known = set()
    eligible_gossip = {r["target_id"]: r for r in gossip_rows}
    for item in placements:
        npc, hashed, fingerprint = (item[k] for k in ("npc_id", "english_hash", "english_sha256"))
        matching = contexts.get((npc, hashed, fingerprint), {})
        known.update(matching)
        english = sorted({v[0] for v in matching.values()})
        group_ids = {sha(normalized(text)) for text in english}
        npc_target = f"gossip:{npc}:{hashed}"
        target = item["target_id"]
        built = units.get(("gossip", f"npc:{npc}:{hashed}")) or units.get(("gossip_common", f"common:{hashed}"))
        if item["status"] == "conflict" or not english:
            built = None
        choices = []
        external(npc_target, choices)
        recorded = target in agent_targets or npc_target in agent_targets
        for key in [*sorted(group_ids), target]:
            for r, saved, method in indexed_gossip[key]:
                recorded |= saved
                choices.append(review_candidate(r["text"], r.get("provider", "classicua"),
                    r.get("source_file", r.get("group_id")), r.get("source_revision", r.get("classicua_revision")),
                    version_status(r) if method == "reviewed" else r["decision"]))
        translation = raw_gossip["byNpc"].get(npc, {}).get(hashed) or raw_gossip["common"].get(hashed)
        if translation:
            current = eligible_gossip.get(target, {})
            choices.append(review_candidate(translation, "classicua", current.get("source_file", target),
                                            state.source.revision, "candidate"))
        ready = (item["status"] == "eligible" and target not in blocked
                 and not any(r["review"] == "pending_update" for r in choices))
        conflict = item["status"] == "conflict" or (not built and len(
            {r["sha256"] for r in choices if r["review"] not in ("rejected", "deferred")}) > 1)
        name = next((v[1] for v in matching.values() if v[1]), f"NPC {npc}")
        rows.append(decorate({"id": f"{npc_target}:{fingerprint}", "type": "gossip", "label": name,
                             "originals": english}, [npc_target, target, *group_ids], built, choices,
                    recorded, status_for(english, choices, conflict=conflict, ready=ready),
                    npc_id=npc, english_hash=hashed, contexts=sorted(matching)))
    for identity, target in sorted(state.inventory.targets.items()):
        if target.family != "gossip" or identity in known:
            continue
        line = glossary.get(identity, {})
        rows.append(decorate({"id": identity, "type": "gossip", "label": line.get("npcName") or identity,
                             "originals": [originals[identity]] if identity in originals else []},
                    [identity], None, [], False, "invalid", npc_id=line.get("npcId"),
                    contexts=state.inventory.contexts[identity]))
    return ModuleInventory(rows, build, units)


def state_path(name):
    from tools.review_ui_server import ROOT
    return ROOT / "build" / name
