"""Private read model joining pinned originals, review evidence and ZIP inventory."""
from collections import Counter, defaultdict
from functools import cached_property
from types import SimpleNamespace

from adapters.auto_one_to_one import EVENT_POSITION, machine_candidates
from adapters.crosswalk import digest
from adapters.source_revision_store import SourceReviewStore, sha
from adapters.sqlite_translation_store import connection
from adapters.translation_agent import AGENT, QUEST, assessment_rows, metadata, recorded_imports, stale_ids
from adapters.translation_approvals import status as quest_status
from adapters.translation_sources import load_source_policy
from tools.gossip_coverage import read_pinned_corpus
from tools.translation_manager import MODULE, file_stamp
from tools.build_ukrainian import MODULE_DOMAINS
from tools.source_revision_review import quest_contexts
from tools.manager_timing import timing
from tools import quest_runtime_review


STATUS_HELP = {
    "ready": "Переклад готовий до включення в локальний модуль. Натисніть «Створити модуль».",
    "missing": "Перекладу для цього контексту немає. Додайте чернетку, якщо підтверджено контекст запису.",
    "review": "Для цього перекладу бракує чинної перевірки, дозволу або підтвердженого зіставлення.",
    "conflict": "Є неоднозначні варіанти. Звірте оригінали й джерела перед підтвердженням кандидата.",
    "rejected": "Збережено рішення відхилити або відкласти переклад. Перегляньте рішення вручну.",
    "invalid": "Бракує перевіреного оригіналу або не підтримується контекст чи формат. Перевірте джерела.",
    "stale": "Попередні докази змінилися. Перевірте відповідність і версію джерела.",
    "multiple_originals": "Гра передає лише ID квесту та етап. Підтвердьте один переклад, який підходить для кожного наведеного оригіналу й контексту.",
}
GOSSIP_MATCH_TYPES = frozenset({
    "all", "exact_npc", "exact_common", "whitespace_candidate", "same_template",
    "one_token_edit", "corpus_alternate_candidate", "wrong_npc_scope",
    "other_family_candidate", "glossary_candidate", "dynamic_candidate",
    "reply_only_candidate", "verified_alias_wording", "hash_collision",
    "ambiguous_npc_type", "missing_verified_original", "no_evidence",
})

MAPPING_STATES = {"mapping_verified", "mapping_provisional", "mapping_pending",
                  "mapping_conflict", "mapping_rejected", "invalid_context", "stale"}
TRANSLATION_STATES = {"translation_available", "translation_missing", "translation_pending",
                      "translation_approved", "translation_rejected"}


def quest_bucket(row):
    """Exactly one UI bucket per Quest or Gossip, independent of review statuses."""
    if row.get("ready_to_import"):
        return "quest_ready"
    if row.get("built"):
        return "quest_imported"
    return "quest_problem"



def latest_units(db, archive, spoken_revision, classicua_revision, module=MODULE):
    db.execute("BEGIN")
    try:
        head = db.execute("""SELECT s.id, s.artifact_sha256, s.created_at
            FROM module_build_heads h JOIN build_import_snapshots s ON s.id=h.snapshot_id
            WHERE h.module=? AND s.module=? AND s.spoken_revision=? AND s.classicua_revision=?""",
            (module, module, spoken_revision, classicua_revision)).fetchone()
        if not head or file_stamp(archive) != head[1]:
            return {}, None
        rows = db.execute("""SELECT domain, unit_key, source, route, text_sha256
            FROM build_import_units WHERE snapshot_id=?""", (head[0],)).fetchall()
        return {(domain, key): {"source": source, "route": route, "text_sha256": fingerprint}
                for domain, key, source, route, fingerprint in rows}, {"sha256": head[1], "built_at": head[2]}
    finally:
        db.rollback()


class ModuleInventory:
    def __init__(self, rows, build, units, module=MODULE, state=None, corpus_lines=None):
        self.module = module
        self.rows = {r["id"]: r for r in rows if r["type"] == MODULE_DOMAINS[module]}
        self.build = build
        self.units = units
        self.state = state
        self.corpus_lines = corpus_lines

    def summary(self):
        return self._summary

    @cached_property
    def _summary(self):
        result = {}
        for kind in (MODULE_DOMAINS[self.module],):
            rows = [r for r in self.rows.values() if r["type"] == kind]
            counts = Counter(r["status"] for r in rows)
            pending = Counter(r["status"] for r in rows if r["built"] is None)
            built = sum(r["built"] is not None for r in rows)
            conflicts = sum(r.get("candidate_conflict", r["status"] == "conflict") for r in rows)
            result[kind] = {"total": len(rows), "included": built, "not_included": len(rows) - built,
                            "recorded": sum(r["recorded"] for r in rows),
                            "conflicts": conflicts,
                            "multiple_originals": sum(len(r.get("originals", ())) > 1 for r in rows
                                                      if r["type"] == "quest"),
                            "conflicting_candidates": conflicts, "missing": counts["missing"],
                            "ready": sum(bool(r.get("ready_to_import")) for r in rows),
                            "quest_imported": sum(quest_bucket(r) == "quest_imported" for r in rows),
                            "quest_problem": sum(quest_bucket(r) == "quest_problem" for r in rows),
                            "pending_review": pending["review"] + pending["stale"],
                            "mapping_states": dict(Counter(r.get("mapping_state", r["status"]) for r in rows)),
                            "translation_states": dict(Counter(r.get("translation_state", r["status"]) for r in rows)),
                            "import_states": dict(Counter(r.get("import_state", "included_in_zip" if r["built"]
                                else "recorded_in_database" if r["recorded"] else "not_imported") for r in rows)),
                            "in_review_queue": sum(bool(r.get("review_queue")) for r in rows),
                            "agent_warnings": len({identity for r in rows for identity in r.get("agent_warning_ids", [])}),
                            "agent_warning_rows": sum(bool(r.get("agent_warning")) for r in rows),
                            "unverified_alternatives": sum(bool(r.get("unverified_alternatives")) for r in rows),
                            "not_included_by_status": dict(pending),
                            "by_status": dict(counts)}
        result["gossip_archive_units"] = {
            "npc_hash_pairs": sum(domain == "gossip" for domain, _ in self.units),
            "common_hashes": sum(domain == "gossip_common" for domain, _ in self.units),
        }
        return result

    def page(self, *, module=MODULE, query="", kind="all", filter_by="all", status="all",
             match_type="all", offset=0, limit=30):
        if (module != self.module or kind not in ("all", MODULE_DOMAINS[self.module])
                or filter_by not in ("all", "imported", "not_imported", "conflicts", "multiple_originals",
                                     "quest_imported", "quest_ready", "quest_problem")
                or status not in {"all", *STATUS_HELP, *MAPPING_STATES, *TRANSLATION_STATES}
                or match_type not in GOSSIP_MATCH_TYPES
                or (MODULE_DOMAINS[self.module] != "gossip" and match_type != "all")
                or type(query) is not str or len(query) > 200
                or type(offset) is not int or offset < 0
                or type(limit) is not int or not 1 <= limit <= 100):
            raise ValueError("manager_invalid_filters")
        needles = query.casefold().split()
        items = []
        total = 0
        for row in self.rows.values():
            if kind not in ("all", row["type"]) or status not in (
                    "all", row["status"], row.get("mapping_state"), row.get("translation_state")):
                continue
            if match_type != "all" and match_type not in row.get("match_types", ()):
                continue
            if filter_by == "imported" and not row["built"] or filter_by == "not_imported" and row["built"]:
                continue
            if filter_by == "conflicts" and not row.get("candidate_conflict", row["status"] == "conflict"):
                continue
            if filter_by == "multiple_originals" and (row["type"] != "quest" or len(row["originals"]) < 2):
                continue
            if filter_by.startswith("quest_") and quest_bucket(row) != filter_by:
                continue
            if needles:
                text = " ".join([row["id"], row["label"], *row["originals"],
                                 *(c["text"] for c in row["candidates"])]).casefold()
                if not all(word in text for word in needles):
                    continue
            if offset <= total < offset + limit:
                items.append({k: row[k] for k in ("id", "type", "label", "status", "built", "recorded",
                    "mapping_state", "translation_state", "import_state", "review_queue",
                    "agent_warning", "unverified_alternatives", "candidate_conflict",
                    "ready_to_import", "needs_choice", "npc_id", "english_hash", "match_types") if k in row})
            total += 1
        return {"module": module, "summary": self.summary(), "build": self.build,
                "total": total, "items": items}

    def detail(self, *, module=MODULE, identity):
        if module != self.module or type(identity) is not str or identity not in self.rows:
            raise ValueError("manager_item_not_found")
        row = self.rows[identity]
        help_text = ("Переклад доступний у перевіреній локальній збірці."
                     if row["status"] == "ready" and row["built"] else STATUS_HELP[row["status"]])
        if row["status"] == "missing":
            if row.get("draft_available"):
                help_text = "Перекладу ще немає. Введіть український текст і збережіть чернетку."
            elif row["type"] == "quest":
                if row.get("mapping_state") == "mapping_verified":
                    help_text = "Для цього зіставлення бракує дозволеного джерела з чинними доказами."
                elif row.get("review_queue") == "quest_mapping":
                    help_text = "Спершу підтвердьте зіставлення ClassicUA та Spoken двома незалежними рецензентами."
                else:
                    help_text = "Бракує підтвердженого зіставлення Stage 3. Звірте закріплені джерела й контекст."
        from tools.manager_review import validate_quest_text, validate_text
        choices = []
        for candidate in row["candidates"]:
            choice = dict(candidate)
            eligibility = choice.get("eligibility", "source_review")
            if (not row["originals"] or row["type"] != "quest" and len(row["originals"]) != 1
                    or row["type"] == "quest" and not row.get("review_binding")) or row.get("mapping_state") in (
                    "invalid_context", "mapping_conflict", "mapping_rejected"):
                eligibility = "context_blocked"
            elif choice.get("review") in ("rejected", "deferred", "stale", "pending_update"):
                eligibility = "stale" if choice["review"] in ("stale", "pending_update") else "review_blocked"
            elif eligibility in ("selectable", "register"):
                choice["draft_editable"] = eligibility == "selectable" and choice.get("review_kind") == "quest"
                try:
                    if row["type"] == "quest":
                        validate_quest_text(row["originals"], choice["text"])
                    else:
                        validate_text(row["originals"][0], choice["text"])
                except ValueError:
                    eligibility = "format_blocked"
            choices.append(choice | {"eligibility": eligibility})
        return {**row, "help": help_text, "candidates": choices,
                "mapping_options": self.mapping_options(row)}

    def mapping_options(self, row):
        if (self.state is None or row.get("review_queue") != "quest_mapping"
                or not row["originals"] or row.get("mapping_state") == "mapping_rejected"):
            return []
        options = []
        for variant in row.get("original_variants", []):
            target = variant["target_id"]
            for faction in variant["review_factions"]:
                page = self.state.page(faction, limit=40, target_filter=target)
                for item in page["items"]:
                    for option in item["target_options"]:
                        for facts in option["variants"]:
                            if (facts["english_original"] != variant["text"]
                                    or facts["faction"] not in (faction, "both", "neutral")):
                                continue
                            options.append({
                                "source_id": item["source_id"], "target_id": target,
                                "source_text": item["ukrainian_text"], "facts": facts,
                                "evidence": {
                                    "source_reference": item["source_reference"],
                                    "source_context_sha256": item["source_context_sha256"],
                                    "source_blob_sha256": item["source_blob_sha256"],
                                    "target_reference": option["target_reference"],
                                    "target_context_sha256": option["target_context_sha256"],
                                    "target_blob_sha256": option["target_blob_sha256"],
                                },
                            })
        return options


def review_candidate(text, source, reference, revision, review):
    return {"text": text, "provider": source, "reference": reference,
            "revision": revision, "review": review, "sha256": sha(text)}


def assessment_key(candidate):
    return (candidate["target_id"], candidate["provider"], candidate["revision"], candidate["text_sha256"])


def assessment_reference(candidate):
    origin = candidate["provenance"]
    return (origin.get("source_ref") or origin.get("source_file") or origin.get("declared_source_ref")
            or origin.get("origin", {}).get("file"))


def translation_state(choices):
    decisions = {item["review"] for item in choices}
    if not decisions:
        return "translation_missing"
    if decisions & {"approved", "source_selected"}:
        return "translation_approved"
    if decisions & {"pending", "pending_update", "stale"}:
        return "translation_pending"
    if decisions <= {"rejected", "deferred", "candidate"} and decisions & {"rejected", "deferred"}:
        return "translation_rejected"
    return "translation_available"


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


def load_inventory(classicua, spoken, db_path, archive, *, module=MODULE, skipped=(), state=None, input_loader=None):
    with timing("inventory", module):
        return _load_inventory(classicua, spoken, db_path, archive, module=module, skipped=skipped,
                               state=state, input_loader=input_loader)


def _load_inventory(classicua, spoken, db_path, archive, *, module, skipped, state, input_loader):
    from tools.review_ui_server import ROOT, build_state, load_review_inputs

    domain = MODULE_DOMAINS[module]
    inputs = input_loader() if state is None and input_loader is not None else None
    if state is None and domain == "gossip":
        if inputs is None:
            inputs = load_review_inputs(classicua, spoken, keep_lines=True)
        dataset, source, inventory, original_index, _ = inputs
        state = SimpleNamespace(dataset=dataset, source=source, inventory=inventory,
                                original_index=original_index, allowed_directory=ROOT / "build",
                                policy=load_source_policy(ROOT / "config/translation_sources.json"))
    elif state is None:
        state = build_state(classicua, spoken, state_path("stage4b-decisions.json"),
                            local_reviews_path=state_path("stage3-ui-reviews.json"),
                            translations_path=state_path("translation-reviews.json"), inputs=inputs)
    lines = inputs[-1] if inputs is not None else read_pinned_corpus(spoken, state.inventory.revision)
    originals = state.original_index.original_english
    lines = lines if domain == "gossip" else [line for line in lines if (line.get("source") == "gossip") == (domain == "gossip")]
    glossary = {line.get("lineId"): line for line in lines}
    if domain == "gossip":
        from tools.gossip_simple import audit_catalog, rows as gossip_rows

        with connection(db_path) as db:
            units, build = latest_units(db, archive, state.inventory.revision, state.source.revision, module)
        current_units = {key: value for key, value in units.items()
                         if value["route"] in ("user_selected", "pinned_unique")}
        audit = audit_catalog(classicua, spoken)
        return ModuleInventory(gossip_rows(state, lines, db_path, current_units, audit),
                               build if not units or current_units else None, current_units, module, state,
                               corpus_lines=lines)
    with timing("sqlite_reads", module), connection(db_path) as db:
        units, build = latest_units(db, archive, state.inventory.revision, state.source.revision, module)
        agent_targets = {r["target_id"] for r in recorded_imports(db) if r["domain"] == domain}
        assessments = [r for r in assessment_rows(db, latest=True) if r["candidate"]["domain"] == domain]
        stale_assessments = stale_ids(db)
        source_selected = {r[0] for r in db.execute("SELECT candidate_id FROM source_active_selections")}
        source_status = dict(db.execute("""SELECT candidate_id, decision FROM source_candidate_decisions
            WHERE id IN (SELECT MAX(id) FROM source_candidate_decisions GROUP BY candidate_id)"""))

    candidate_sources = defaultdict(list)
    store = SourceReviewStore(db_path)
    for source in store.candidates():
        if source["domain"] == domain:
            candidate_sources[source["target_id"]].append(source)
    assessment_index = defaultdict(list)
    for review in assessments:
        assessment_index[assessment_key(review["candidate"])].append(review)
    current_assessments = {}
    skipped_ids = {key: reason for key, reason in skipped}

    def decorate(entry, targets, built, choices, recorded, status, **extra):
        warnings = set()
        for choice in choices:
            scores = {score["candidate"]["id"]: score for key in targets for score in
                      assessment_index[key, choice["provider"], choice["revision"], choice["sha256"]]
                      if assessment_reference(score["candidate"]) == choice["reference"]}
            current = [score for identity, score in scores.items() if identity not in stale_assessments
                       and score["agent"] == AGENT
                       and current_assessments.get(identity) == score["candidate"]]
            if len(current) == 1:
                choice["validation"] = current[0]["status"]
                choice["checks"] = current[0]["checks"]
                if current[0]["status"] != "agent_verified":
                    warnings.add(current[0]["candidate"]["id"])
            elif scores:
                choice["validation"] = "stale"
        # Preserve different review decisions for the same source text.
        choices = list({(r["sha256"], r["provider"], r["reference"], r["review"],
                         r.get("review_id"), r.get("registration_key")): r
                        for r in choices}.values())
        reason = next((skipped_ids[key] for key in targets if key in skipped_ids), extra.pop("reason", None))
        if reason and "conflict" in reason and status not in ("multiple_originals", "invalid"):
            status = "conflict"
        fallback_mapping = extra.pop("mapping", "mapping_pending")
        mapping = ("invalid_context" if not entry["originals"] or status == "invalid" else fallback_mapping)
        return {**entry, "status": status, "built": built, "candidates": choices,
                "recorded": recorded, "problem": reason, "mapping_state": mapping,
                "translation_state": translation_state(choices),
                "import_state": "included_in_zip" if built else
                    "recorded_in_database" if recorded else "not_imported",
                "agent_warning": bool(warnings), "agent_warning_ids": sorted(warnings), **extra}

    trusted = quest_contexts(state)

    def external(domain, target, choices):
        for source in candidate_sources[target]:
            if source["domain"] != domain:
                continue
            proof = trusted.get((domain, target))
            eligibility = "selectable"
            if (not proof or any(source[k] != proof[k] for k in ("english_sha256", "context_sha256"))
                    or source["text_sha256"] != sha(source["ukrainian_text"])
                    or source["provider"] == "classicua" and source["revision"] != state.source.revision):
                eligibility = "stale"
            elif domain == "quest" and target not in observed_targets:
                eligibility = "mapping_required" if target not in reviewed_targets else "source_review"
            is_active = source["id"] in source_selected
            choices.append(review_candidate(source["ukrainian_text"], source["provider"],
                source["source_ref"], source["revision"],
                "source_selected" if is_active else source_status.get(source["id"], "candidate"))
                | {"review_id": source["id"], "review_kind": "source", "eligibility": eligibility})

    rows = []
    indexed_quest = defaultdict(list)
    for ledger, method in ((state.translations.file.data, "reviewed"), (state.machine_imports.file.data, "machine_1to1")):
        imported = imported_ids(ledger)
        for row in ledger["versions"]:
            indexed_quest[row["target_id"]].append((row, row["id"] in imported, method))
    variants = getattr(state.original_index, "variants", {})
    hints = defaultdict(list)
    quest_queue = defaultdict(set)
    decisions = {(r["source_id"], r["target_id"]): r["decision"]
                 for r in getattr(state, "decisions", {}).get("decisions", [])}
    reviewed_sources = {r.decision.source_id for r in getattr(state, "reviews", ())
                        if r.decision.mapping_status == "approved"}
    for hint in state._hints:
        for target in hint["candidates"]:
            source_id = hint["source_id"]
            hints[target].append(source_id)
            if (source_id not in reviewed_sources and hint["status"] != "excluded"
                    and hint["reason"] != "faction_eligibility_conflict"
                    and decisions.get((source_id, target)) != "rejected"):
                quest_queue[target].add(source_id.split(":")[1])
    enabled = state.policy.auto_approves_one_to_one("classicua")
    q_machine = machine_candidates(
        state.dataset, state.source, state.inventory, state.original_index, state._hints,
        allow_ai_transations=state.policy.allows_ai_transations("classicua")) if enabled else []
    q_auto = {r["target_id"]: r for r in q_machine}
    observations = state.translation_observations()
    observed_targets = defaultdict(list)
    for observation in observations:
        observed_targets[observation.target_id].append(observation)
    reviewed_targets = {r.decision.target_id for r in getattr(state, "reviews", ())
                        if r.decision.mapping_status == "approved"}
    if assessments:
        from tools.translation_agent import evidence
        current_assessments = {r["id"]: metadata(r) for r in evidence(
            state, spoken, db_path, revalidate=False, lines=lines, observations=observations,
            quest_machine=q_machine if enabled else None, domain="quest")}
    rejected_moments = state.blocked_quest_moments() if hasattr(state, "blocked_quest_moments") else set()
    review_ready = {r["target_id"] for r in state.translations.eligible(
        observations, state.policy, skipped=[])}
    quest_groups = defaultdict(list)
    for target, item in state.inventory.targets.items():
        match = QUEST.fullmatch(target) if item.family == "quest" else None
        if match:
            quest_groups[match.group(1)].append(target)
    runtime_history = defaultdict(list)
    runtime_approved = {}
    from tools.quest_simple import resolved as simple_resolved, selections as simple_selections
    from tools.quest_source_compatibility import matching_evidence, matching_selection
    local_choices = simple_selections(db_path)
    quick_resolved = simple_resolved(state, db_path)
    for review in quest_runtime_review.history(db_path):
        runtime_history[review["moment"]].append(review)
    runtime_approved = quest_runtime_review.approved(state, db_path, None)
    for moment, targets in sorted(quest_groups.items(), key=lambda x: (int(x[0].split(":")[1]), x[0])):
        _, quest_id, event = moment.split(":")
        title = next((glossary.get(target, {}).get("questTitle") for target in targets
                      if glossary.get(target, {}).get("questTitle")), f"Quest {quest_id}")
        original_variants = []
        for target in targets:
            for text in variants.get(target, (originals[target],) if target in originals else ()):
                wording = digest(text)
                contexts_for_wording = [c | {"index": i} for i, c in enumerate(state.inventory.contexts[target])
                                        if c["wording_sha256"] == wording]
                original_variants.append({"target_id": target, "text": text, "contexts": contexts_for_wording,
                                          "source_ids": sorted(hints[target]), "revision": state.inventory.revision,
                                          "fingerprint": wording,
                                          "review_factions": sorted(quest_queue[target])})
        english = sorted({variant["text"] for variant in original_variants})
        multiple = len(english) > 1
        choices = []
        recorded = ready = False
        for target in targets:
            ready |= target in review_ready or target in q_auto and not any(
                method == "reviewed" or r.get("decision") == "pending_update"
                for r, _, method in indexed_quest[target])
            external("quest", target, choices)
            recorded |= target in agent_targets
            available = [r for r in (o.row() for o in observed_targets[target])
                         if r["rights_status"] == "reviewed"
                         and state.policy.stores(r["provenance"][0]["provider"])]
            stored_ids = {r["id"] for r, _, method in indexed_quest[target] if method == "reviewed"}
            for r in available:
                p = r["provenance"][0]
                if r["id"] not in stored_ids:
                    choices.append(review_candidate(r["text"], p["provider"], p["source_ref"],
                                                    p["revision"], "candidate")
                                   | {"registration_key": r["id"], "eligibility": "register"})
            for r, saved, method in indexed_quest[target]:
                p = r.get("provenance", [{}])[0]
                choices.append(review_candidate(r["text"], p.get("provider", "classicua" if method == "machine_1to1" else "manual"),
                    p.get("source_ref", r.get("source_file", r["source_id"])),
                    p.get("revision", r.get("source_revision")), quest_status(r) if method == "reviewed" else r["decision"]))
                if method == "reviewed":
                    eligibility = ("stale" if not state.translations.current(r, observed_targets[target], state.policy)
                                   else "rights_blocked" if r["rights_status"] != "reviewed" else "selectable")
                    choices[-1].update(review_id=r["id"], review_kind="quest", eligibility=eligibility)
                else:
                    choices[-1]["eligibility"] = "mapping_required" if target not in reviewed_targets else "source_review"
                recorded |= saved
                if "shared_bindings" in r:
                    choices[-1]["shared_bindings"] = r["shared_bindings"]
            for source_id in hints[target]:
                unit = state.source.units[source_id]
                _, faction, number, source_event = source_id.split(":")
                record = state._views[faction].get(int(number))
                field = record.fields.get((EVENT_POSITION[source_event],)) if record else None
                if field and isinstance(field.node.value, str) and sha(field.node.value) == unit.effective_sha256:
                    if any(r["source_id"] == source_id and r["text"] == field.node.value for r in available):
                        continue
                    choices.append(review_candidate(field.node.value, "classicua", unit.origin_file,
                                                    unit.source_revision, "candidate") | {
                        "eligibility": "rights_blocked" if unit.ai else
                        "mapping_required" if target not in reviewed_targets else "source_review"})
        built = units.get(("quests", f"{quest_id}:{event}"))
        binding, _ = quest_runtime_review.binding(state, moment, targets)
        current_quick = quick_resolved.get(moment)
        quick_ready = bool(current_quick and current_quick.get("text") and
                           (not built or built["text_sha256"] != sha(current_quick["text"])))
        quick_conflict = bool(current_quick and current_quick.get("conflict"))
        quick = local_choices.get(moment)
        # The current validated one-to-one choice is a real importable
        # candidate even if historical Stage 3 review has not approved it.
        if current_quick and current_quick.get("text") and not any(
                choice["sha256"] == sha(current_quick["text"]) for choice in choices):
            choices.append(review_candidate(
                current_quick["text"], current_quick["source"], "pinned Quest ID/event",
                state.source.revision, "candidate") | {"eligibility": "auto_selected"})
        if quick and binding and matching_selection(quick[0], binding):
            if not any(c["sha256"] == quick[2] for c in choices):
                choices.append(review_candidate(quick[1], quick[3], "local", state.inventory.revision, "local"))
            recorded = True
        approved = runtime_approved.get(moment)
        decisions = quest_runtime_review.current_decisions(runtime_history[moment])
        approvals = {r["candidate"] for r in decisions if binding is not None
                     and matching_evidence(r["evidence"], binding)}
        for choice in choices:
            if choice.get("review_id") and quest_runtime_review.candidate_key(choice) in approvals:
                choice["runtime_approval"] = True
            if approved and choice.get("review_id") and approved["candidate"] == quest_runtime_review.candidate_key(choice):
                choice["review"] = "approved"
        recorded |= bool(approved)
        for review in runtime_history[moment]:
            if review["decision"] != "pending":
                continue
            current = binding is not None and matching_evidence(review["evidence"], binding)
            decision = ("stale" if not current else "approved" if approved and
                        approved["candidate"] == "runtime:" + review["id"] else "pending")
            choices.append(review_candidate(review["text"], "manual", moment, state.inventory.revision, decision)
                           | {"review_id": "runtime:" + review["id"], "review_kind": "runtime",
                              "eligibility": "selectable" if current else "stale",
                              "runtime_approval": "runtime:" + review["id"] in approvals})
        conflict = len({r["sha256"] for r in choices if r["review"] not in (
            "rejected", "deferred", "pending_update", "stale") and r.get("eligibility") != "stale"}) > 1
        ready = quick_ready or (bool(approved) or
                               ready and not multiple and moment not in rejected_moments)
        queue = "quest_mapping" if any(quest_queue[t] for t in targets) else (
            "quest_translation" if set(targets) & reviewed_targets else None)
        stale_review = bool(decisions) and moment not in runtime_approved
        reason = (None if quick_ready else
                  "quest_mapping_rejected_or_deferred" if moment in rejected_moments else
                  "conflicting_quest_runtime_variants" if moment in runtime_approved and not approved else
                  "quest_runtime_review_stale" if stale_review else
                  "quest_multiple_verified_originals" if multiple and not approved else
                  "quest_original_missing" if not english else
                  "quest_mapping_unverified" if choices and not ready and not queue else None)
        mapping = ("mapping_rejected" if moment in rejected_moments else
                   "mapping_verified" if set(targets) & reviewed_targets else
                   "mapping_provisional" if set(targets) & q_auto.keys() else "mapping_pending")
        status = ("ready" if quick_ready else
                  "rejected" if moment in rejected_moments else "ready" if approved else
                  "conflict" if moment in runtime_approved else "multiple_originals" if multiple else
                  status_for(english, choices, conflict=conflict, ready=ready))
        rows.append(decorate({"id": moment, "type": "quest", "label": title, "originals": english},
                    targets + [moment], built, choices, recorded, status, mapping=mapping, reason=reason,
                    review_queue=queue, original_variants=original_variants, candidate_conflict=conflict and not quick_ready,
                    draft_available=bool(binding) and moment not in rejected_moments,
                    ready_to_import=quick_ready, needs_choice=quick_conflict,
                    selected_sha256=(sha(current_quick["text"]) if current_quick and current_quick.get("text")
                                     else quick[2] if quick and binding
                                     and matching_selection(quick[0], binding) else None),
                    review_binding=digest(binding) if binding else None,
                    approved_variant_count=len(english) if approved and multiple else 0,
                    quest_id=quest_id, event=event, contexts=[c for t in targets for c in state.inventory.contexts[t]]))

    return ModuleInventory(rows, build, units, module, state)


def state_path(name):
    from tools.review_ui_server import ROOT
    return ROOT / "build" / name
