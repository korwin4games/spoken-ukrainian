"""Private human review of canonical Quest text at the runtime ID/event boundary."""
import json
from collections import defaultdict

from adapters.crosswalk import digest, quest_moment
from adapters.source_revision_store import CHECKS, SourceReviewStore, sha
from adapters.sqlite_translation_store import connection
from adapters.translation_approvals import status


def candidate_key(choice):
    return choice["review_kind"] + ":" + choice["review_id"].removeprefix("runtime:")


def binding(state, moment, targets):
    """Require a verified wording for every pinned target context."""
    index = state.original_index
    texts = set()
    variants = []
    for target in sorted(targets):
        originals = index.variants.get(target, ())
        if not originals and target in index.original_english:
            originals = (index.original_english[target],)
        contexts = state.inventory.contexts[target]
        if not originals or not contexts or {digest(s) for s in originals} != {
                context["wording_sha256"] for context in contexts}:
            return None, []
        variants.append({"target_id": target, "contexts": contexts})
        texts.update(originals)
    if not texts:
        return None, []
    return {"moment": moment, "spoken": state.inventory.revision,
            "classicua": state.source.revision, "variants": variants}, sorted(texts)


def history(db_path):
    with connection(db_path) as db:
        rows = db.execute("""SELECT id, moment, candidate, evidence, text, decision, reviewer, checks_json
            FROM quest_runtime_reviews ORDER BY id""").fetchall()
    records = []
    for identity, moment, candidate, evidence, text, decision, reviewer, checks in rows:
        try:
            evidence, checks = json.loads(evidence), json.loads(checks)
        except (ValueError, TypeError, RecursionError):
            raise ValueError("invalid_quest_runtime_review") from None
        if (not isinstance(evidence, dict) or evidence.get("moment") != moment
                or not isinstance(reviewer, str) or not 0 < len(reviewer.strip()) <= 120
                or not isinstance(checks, dict)
                or (decision == "approved" and (set(checks) != set(CHECKS)
                                                 or any(v is not True for v in checks.values())))
                or decision != "approved" and checks):
            raise ValueError("invalid_quest_runtime_review")
        records.append({"id": str(identity), "moment": moment, "candidate": candidate, "evidence": evidence,
                        "text": text, "decision": decision})
    return records


def save(db_path, moment, candidate, evidence, text, decision, reviewer, checks):
    with connection(db_path) as db:
        db.execute("""INSERT INTO quest_runtime_reviews
            (moment, candidate, evidence, text, decision, reviewer, checks_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (moment, candidate, json.dumps(evidence, sort_keys=True), text, decision,
             reviewer, json.dumps(checks, sort_keys=True)))


def current_decisions(records):
    latest = {}
    for review in records:
        if review["decision"] != "pending":
            key = (review["moment"], review["candidate"], digest(review["evidence"]))
            latest[key] = review
    return [review for review in latest.values() if review["decision"] == "approved"]


def approved(state, db_path, skipped):
    """Resolve only approvals whose complete evidence and candidate still match."""
    from tools.manager_review import validate_quest_text
    from tools.source_revision_review import quest_contexts

    records = history(db_path)
    approvals = current_decisions(records)
    versions = state.translations.file.data["versions"]
    if not approvals and not any(status(r) == "approved" for r in versions):
        return {}
    blocked = state.blocked_quest_moments()
    observations = state.translation_observations()
    by_target = defaultdict(list)
    for observation in observations:
        by_target[observation.target_id].append(observation)
    referenced = {r["candidate"] for r in approvals}
    current = {r["id"]: r for r in versions if (status(r) == "approved" or "quest:" + r["id"] in referenced)
               and state.translations.current(r, by_target[r["target_id"]], state.policy)}
    store = SourceReviewStore(db_path)
    trusted = quest_contexts(state)
    external = store.active(trusted, domain="quest", skipped=[] if skipped is None else skipped)
    mapped = {o.target_id for o in observations}
    external = [s for s in external if s["target_id"] in mapped
                and (s["provider"] != "classicua" or s["revision"] == state.source.revision)]
    source_candidates = {s["id"]: s for s in store.candidates() if s["domain"] == "quest"}
    with connection(db_path) as db:
        source_status = dict(db.execute("""SELECT candidate_id, decision FROM source_candidate_decisions
            WHERE id IN (SELECT MAX(id) FROM source_candidate_decisions GROUP BY candidate_id)"""))
    drafts = {r["id"]: r for r in records if r["decision"] == "pending"}
    targets = {}
    for target, item in state.inventory.targets.items():
        if item.family == "quest":
            targets.setdefault(quest_moment(target), []).append(target)
    candidates = defaultdict(dict)
    for r in approvals:
        moment = r["moment"]
        evidence, originals = binding(state, moment, targets.get(moment, ()))
        if moment in blocked or not evidence or evidence != r["evidence"]:
            continue
        kind, _, identity = r["candidate"].partition(":")
        source = "manual"
        if kind == "runtime":
            draft = drafts.get(identity)
            if not draft or any(draft[key] != r[key] for key in ("moment", "evidence", "text")):
                continue
        elif kind == "quest":
            version = current.get(identity)
            if (not version or quest_moment(version["target_id"]) != moment or version["text"] != r["text"]
                    or version["rights_status"] != "reviewed"
                    or status(version) in ("rejected", "deferred")):
                continue
            if version["kind"] == "provider":
                source = version["provenance"][0]["provider"]
        elif kind == "source":
            selection = source_candidates.get(identity)
            proof = trusted.get(("quest", selection["target_id"])) if selection else None
            if (not proof or quest_moment(selection["target_id"]) != moment
                    or selection["target_id"] not in mapped or selection["ukrainian_text"] != r["text"]
                    or selection["text_sha256"] != sha(r["text"])
                    or source_status.get(identity) in ("rejected", "deferred")
                    or any(selection[k] != proof[k] for k in ("english_sha256", "context_sha256"))
                    or selection["provider"] == "classicua" and selection["revision"] != state.source.revision):
                continue
            source = selection["provider"]
        else:
            continue
        try:
            validate_quest_text(originals, r["text"])
        except ValueError:
            continue
        candidates[moment][sha(r["text"])] = r | {"source": source}
    human_texts = defaultdict(set)
    for r in current.values():
        if status(r) == "approved":
            human_texts[quest_moment(r["target_id"])].add(r["text_sha256"])
    for r in external:
        human_texts[quest_moment(r["target_id"])].add(r["text_sha256"])
    result = {}
    for moment in sorted(candidates.keys() | human_texts.keys()):
        choices = candidates.get(moment, {})
        fingerprints = choices.keys() | human_texts[moment]
        if len(fingerprints) > 1:
            if skipped is not None:
                skipped.append((moment, "conflicting_quest_runtime_variants"))
            result[moment] = None
        elif choices:
            result[moment] = next(iter(choices.values()))
    return result
