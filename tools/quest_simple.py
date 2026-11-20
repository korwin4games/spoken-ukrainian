"""Simple private Quest selection without reviewer attestations.

Keep historic review tables intact; never present a local choice as a human approval.
"""
from collections import defaultdict

from adapters.auto_one_to_one import EVENT_POSITION
from adapters.crosswalk import digest, quest_moment
from adapters.source_revision_store import sha
from adapters.sqlite_translation_store import connection
from tools.quest_runtime_review import binding
from tools.quest_source_compatibility import matching_selection


def pinned_options(state):
    """Current ClassicUA text matched by exact Quest ID/event and pinned source hash."""
    # Match only the pinned Quest ID/event. Stage 3 hint/reviewer status is
    # not required for *private test* content; it is not a public mapping
    # approval. The English wordings may differ across the same moment.
    can_store = getattr(state.policy, "stores", None)
    if callable(can_store) and not can_store("classicua"):
        return {}  # Respect the configured provider/rights policy.
    views, _ = state.dataset.faction_views(
        include_ai=state.policy.allows_ai_transations("classicua"))
    result = defaultdict(list)
    for target, item in state.inventory.targets.items():
        if item.family != "quest":
            continue
        moment = quest_moment(target)
        parts = moment.split(":")
        if (len(parts) != 3 or parts[0] != "q" or not parts[1].isdigit()
                or parts[2] not in EVENT_POSITION):
            continue
        quest_id, event = int(parts[1]), parts[2]
        contexts = state.inventory.contexts.get(target, ())
        # The only valid relaxed match is a canonical Quest ID + event with
        # matching faction. Unknown/neutral Spoken factions can share either.
        if (not contexts or any(
                c.get("quest_id", quest_id) != quest_id
                or c.get("source", event) != event for c in contexts)):
            continue
        factions = {c.get("faction") for c in contexts
                    if c.get("faction") not in (None, "unknown", "both", "neutral")}
        for faction in ("horde", "alliance"):
            if factions and faction not in factions:
                continue
            source_id = f"quest:{faction}:{quest_id}:{event}"
            unit = state.source.units.get(source_id)
            if (unit is None or unit.ai
                    and not state.policy.allows_ai_transations("classicua")):
                continue
            record = views.get(faction, {}).get(quest_id)
            field = record.fields.get((EVENT_POSITION[event],)) if record else None
            text = field.node.value if field else None
            # Preserve provenance: the effective source field must match the
            # pinned ClassicUA unit; never use translation/name similarity.
            if type(text) is not str or not text.strip() or sha(text) != unit.effective_sha256:
                continue
            support = {}
            for key, pos in (("title", 1), ("objective", 3)):
                leaf = record.fields.get((pos,))
                if leaf and type(leaf.node.value) is str and leaf.node.value.strip():
                    support[key] = leaf.node.value
            result[moment].append((text, support))
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
        alternatives = {text for text, _ in options.get(moment, ()) if usable_text(text)}
        selection = stored.get(moment)
        # A prior explicit rejection still prevents *automatic* re-import.
        # A new user choice is explicit and can replace it in this local pack.
        if moment in previously_rejected and not selection:
            continue
        if selection:
            old, text, fingerprint, source = selection
            if matching_selection(old, evidence) and sha(text) == fingerprint and usable_text(text):
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


def apply_choice(action, payload, row, state, db_path, *, revalidate_inputs=True, db=None):
    required = ({"identity", "binding", "candidate", "confirm"} if action == "choose_quest"
                else {"identity", "binding", "text", "confirm"})
    if set(payload) != required or payload.get("confirm") is not True:
        raise ValueError("manager_invalid_review_request")
    if (row.get("type") != "quest" or not row.get("review_binding")
            or payload["binding"] != row["review_binding"]):
        raise ValueError("manager_review_context_blocked")
    if revalidate_inputs and state.revalidate_inputs is not None:
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
        prior = (db.execute("""SELECT evidence, text, text_sha256, source
            FROM quest_simple_choices WHERE moment=?""", (row["id"],)).fetchone()
            if db is not None else selections(db_path).get(row["id"]))
        if prior and matching_selection(prior[0], evidence) and prior[1] == text:
            source = prior[3]
        elif any(c["text"] == text and c.get("provider") == "classicua" for c in row["candidates"]):
            source = "classicua"
        else:
            source = "manual"  # Explicit local choice, not a human review approval.
    else:
        text, source = payload["text"], "manual"
    if not usable_text(text):
        raise ValueError("manager_invalid_translation_format")
    statement = """INSERT INTO quest_simple_choices
            (moment, evidence, text, text_sha256, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(moment) DO UPDATE SET evidence=excluded.evidence,
                text=excluded.text, text_sha256=excluded.text_sha256,
                source=excluded.source, changed_at=CURRENT_TIMESTAMP"""
    values = (row["id"], digest(evidence), text, sha(text), source)
    if db is None:
        with connection(db_path) as own_db:
            own_db.execute(statement, values)
    else:
        db.execute(statement, values)
    return sha(text)
