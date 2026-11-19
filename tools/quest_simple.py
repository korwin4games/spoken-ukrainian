"""Simple private Quest selection without reviewer attestations.

Keep historic review tables intact; never present a local choice as a human approval.
"""
from collections import defaultdict

from adapters.auto_one_to_one import EVENT_POSITION
from adapters.crosswalk import digest, quest_moment
from adapters.source_revision_store import sha
from adapters.sqlite_translation_store import connection
from tools.quest_runtime_review import binding


def pinned_options(state):
    """Current ClassicUA text matched by exact Quest ID/event and pinned source hash."""
    hints = defaultdict(set)
    for hint in state._hints:
        if hint.get("status") == "excluded" or hint.get("reason") == "faction_eligibility_conflict":
            continue
        for target in hint.get("candidates", ()):
            hints[target].add(hint["source_id"])
    views, _ = state.dataset.faction_views(
        include_ai=state.policy.allows_ai_transations("classicua"))
    result = defaultdict(list)
    for target, item in state.inventory.targets.items():
        if item.family != "quest":
            continue
        parts = quest_moment(target).split(":")
        if len(parts) != 3 or parts[2] not in ("accept", "progress", "complete"):
            continue
        for source_id in hints[target]:
            source = source_id.split(":")
            if (len(source) != 4 or source[0] != "quest" or source[2] != parts[1]
                    or source[3] != parts[2]):
                continue
            unit = state.source.units.get(source_id)
            if unit is None or unit.ai and not state.policy.allows_ai_transations("classicua"):
                continue
            record = views.get(source[1], {}).get(int(source[2]))
            field = record.fields.get((EVENT_POSITION[source[3]],)) if record else None
            text = field.node.value if field else None
            if type(text) is not str or not text.strip() or sha(text) != unit.effective_sha256:
                continue
            support = {}
            for key, pos in (("title", 1), ("objective", 3)):
                leaf = record.fields.get((pos,))
                if leaf and type(leaf.node.value) is str and leaf.node.value.strip():
                    support[key] = leaf.node.value
            result[quest_moment(target)].append((text, support))
    return result


def groups(state):
    result = defaultdict(list)
    for target, item in state.inventory.targets.items():
        if item.family == "quest":
            result[quest_moment(target)].append(target)
    return result


def selections(db_path):
    if not db_path:
        return {}
    with connection(db_path) as db:
        return {moment: (evidence, text, fingerprint, source) for moment, evidence, text,
                fingerprint, source in db.execute(
                    "SELECT moment, evidence, text, text_sha256, source FROM quest_simple_choices")}


def usable_text(text):
    """Only enforce storage safety, not translation quality or token parity."""
    return (type(text) is str and bool(text.strip()) and len(text) <= 60000
            and "\x00" not in text)


def resolved(state, db_path):
    # Synthetic test states predate the pinned ClassicUA hint index.
    # Do not try to infer candidates from incomplete/mock evidence.
    if not isinstance(getattr(state, "_hints", None), (list, tuple)):
        return {}
    options = pinned_options(state)
    stored = selections(db_path)
    previously_rejected = state.blocked_quest_moments()
    result = {}
    for moment, targets in groups(state).items():
        evidence, originals = binding(state, moment, targets)
        if not evidence:
            continue
        alternatives = {text for text, _ in options[moment] if usable_text(text)}
        selection = stored.get(moment)
        # A prior explicit rejection still prevents *automatic* re-import.
        # A new user choice is explicit and can replace it in this local pack.
        if moment in previously_rejected and not selection:
            continue
        if selection:
            old, text, fingerprint, source = selection
            if (old == digest(evidence) and sha(text) == fingerprint and usable_text(text)
                    and (source == "manual" or text in alternatives)):
                result[moment] = {"text": text, "source": source, "selected": True}
                continue
            result[moment] = {"conflict": True}
            continue
        if len(alternatives) > 1:
            result[moment] = {"conflict": True}
            continue
        if len(alternatives) != 1:
            continue
        text = next(iter(alternatives))
        result[moment] = {"text": text, "source": "classicua", "selected": False}
        for field in ("title", "objective"):
            values = {support[field] for candidate, support in options[moment]
                      if candidate == text and field in support}
            if len(values) == 1:
                result[moment][field] = next(iter(values))
    return result


def apply_choice(action, payload, row, state, db_path):
    required = ({"identity", "binding", "candidate", "confirm"} if action == "choose_quest"
                else {"identity", "binding", "text", "confirm"})
    if set(payload) != required or payload.get("confirm") is not True:
        raise ValueError("manager_invalid_review_request")
    if (row.get("type") != "quest" or not row.get("review_binding")
            or payload["binding"] != row["review_binding"]):
        raise ValueError("manager_review_context_blocked")
    if state.revalidate_inputs is not None:
        state.revalidate_inputs()
    targets = {v["target_id"] for v in row["original_variants"]}
    evidence, originals = binding(state, row["id"], targets)
    if not evidence or digest(evidence) != payload["binding"]:
        raise ValueError("manager_review_context_blocked")
    if action == "choose_quest":
        key = payload["candidate"]
        if type(key) is not str or not key:
            raise ValueError("manager_candidate_unavailable")
        # Any currently displayed Quest candidate can be chosen without
        # historical review or translation validation requirements.
        candidates = {c["text"] for c in row["candidates"]
                      if c["sha256"] == key and sha(c["text"]) == key}
        if len(candidates) != 1:
            raise ValueError("manager_candidate_unavailable")
        text = next(iter(candidates))
        prior = selections(db_path).get(row["id"])
        if prior and prior[0] == payload["binding"] and prior[1] == text:
            source = prior[3]
        elif any(c["text"] == text and c.get("provider") == "classicua" for c in row["candidates"]):
            source = "classicua"
        else:
            source = "manual"  # Explicit local choice, not a human review approval.
    else:
        text, source = payload["text"], "manual"
    if not usable_text(text):
        raise ValueError("manager_invalid_translation_format")
    with connection(db_path) as db:
        db.execute("""INSERT INTO quest_simple_choices
            (moment, evidence, text, text_sha256, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(moment) DO UPDATE SET evidence=excluded.evidence,
                text=excluded.text, text_sha256=excluded.text_sha256,
                source=excluded.source, changed_at=CURRENT_TIMESTAMP""",
            (row["id"], digest(evidence), text, sha(text), source))
    return sha(text)
