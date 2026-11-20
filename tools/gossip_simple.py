"""Private Gossip choices bound to the original NPC/hash runtime context."""
from collections import Counter, defaultdict
from functools import lru_cache
import json
import re

from adapters.classicua.grammar import inventory
from adapters.crosswalk import digest
from adapters.source_revision_store import sha
from adapters.sqlite_translation_store import connection
from tools.gossip_coverage import gossip_evidence
from tools.quest_simple import usable_text


TOKENS = re.compile(r"\$[A-Za-z]")
GENDER = re.compile(r"\$[Gg]\s*([^:;{}]+):([^:;{}]+);")
RUNTIME_CODES = {"n": "{ім'я}", "c": "{клас}", "r": "{раса}", "b": "\n"}


def audit_catalog(classicua, spoken):
    from tools.gossip_mapping_audit import ROOT

    lock = (ROOT / "sources.lock.json").read_bytes()
    baselines = (ROOT / "config/gossip_audit_baselines.json").read_bytes()
    return _audit_catalog(str(classicua), str(spoken), lock, baselines)


@lru_cache(maxsize=2)
def _audit_catalog(classicua, spoken, lock, baselines):
    from tools.gossip_mapping_audit import audit, source_inventory, spoken_baseline
    from tools.gossip_candidate_tables import one_edit, template, tokens

    pin = json.loads(lock)
    baseline = json.loads(baselines)[pin["spoken"]["version"]]
    if baseline["revision"] != pin["spoken"]["revision"]:
        raise ValueError("pinned_spoken_revision_mismatch")
    lines, aliases = spoken_baseline(spoken, baseline)
    _, effective, *source = source_inventory(classicua, pin["classicua"])
    _, _, pairs = audit(lines, aliases, effective, *source)
    by_index = {i: row for i, row in enumerate(lines)}
    index = defaultdict(list)
    for (scope, _), entry in effective.items():
        text = template(entry["english"])
        words = tokens(text)
        index[scope, len(words)].append((text, words, entry))
    for pair in pairs:
        if pair["category"] != "no_evidence":
            continue
        text = template(by_index[pair["corpus_indices"][0]]["originalText"])
        words = tokens(text)
        pair["template_candidates"] = []
        for scope in (pair["npc_id"], "!common"):
            for size in (len(words) - 1, len(words), len(words) + 1):
                for other_text, other, source_row in index[scope, size]:
                    if (text and text == other_text) or one_edit(words, other):
                        pair["template_candidates"].append({"source": source_row,
                            "test": "same_template" if text == other_text else "one_token_edit"})
    return {(pair["npc_id"], pair["hash"]): pair for pair in pairs}


def runtime_text(original, text):
    if (not usable_text(text) or re.search(
            r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|\|[cCrRhHtTaA]|%(?:\d+\$)?[sdif]", text)
            or any(form.status != "supported" for form in inventory(text))):
        raise ValueError("manager_invalid_translation_format")
    expected = Counter(t.lower() for t in TOKENS.findall(original))
    actual = Counter(t.lower() for t in TOKENS.findall(text))
    if expected != actual or any(t[1] not in (*RUNTIME_CODES, "g") for t in actual):
        raise ValueError("manager_invalid_translation_format")
    if len(GENDER.findall(text)) != actual["$g"] or any(
            not branch.strip() for pair in GENDER.findall(text) for branch in pair):
        raise ValueError("manager_invalid_translation_format")
    if any(TOKENS.search(branch) for pair in GENDER.findall(text) for branch in pair):
        raise ValueError("manager_invalid_translation_format")
    text = GENDER.sub(lambda m: "{стать:" + m[1].strip() + ":" + m[2].strip() + "}", text)
    return TOKENS.sub(lambda m: {"$C": "{Клас}", "$R": "{Раса}"}.get(
        m[0], RUNTIME_CODES[m[0][1].lower()]), text)


def contexts(state, lines):
    evidence, _, unsafe, _, _ = gossip_evidence(lines)
    groups = defaultdict(list)
    for line, npc, hashed in evidence:
        identity, english = line["lineId"], line["originalText"]
        verified = any(all(ctx.get(key) == value for key, value in {
            "wording_sha256": digest(english), "npc_id": npc, "npc_type": line["npcType"],
            "voice": line.get("voice"), "player_gender": line.get("playerGender"),
        }.items()) for ctx in state.inventory.contexts.get(identity, ()))
        if not verified:
            unsafe.add((npc, hashed))
        groups[npc, hashed].append(line)
    return groups, unsafe


def selections(db_path):
    if db_path is None:
        return {}
    with connection(db_path) as db:
        return {r[0]: r[1:] for r in db.execute(
            "SELECT identity,evidence,text,text_sha256,source,reference FROM gossip_simple_choices")}


def rows(state, lines, db_path, units, audit=None):
    from tools.build_ukrainian import local_gossip_texts
    from tools.manager_inventory import review_candidate, status_for, translation_state

    lookup = local_gossip_texts(state)
    groups, unsafe = contexts(state, lines)
    stored = selections(db_path)
    for (npc, hashed), members in sorted(groups.items()):
        identity = f"gossip:{npc}:{hashed}"
        originals = sorted({line["originalText"] for line in members})
        fields = ("lineId", "npcType", "race", "gender", "playerGender", "voice", "originalText")
        evidence_contexts = [{key: line.get(key) for key in fields} for line in members]
        match = audit.get((npc, hashed), {}) if audit else {}
        binding = None if (npc, hashed) in unsafe or match.get("category") == "hash_collision" else digest({
            "spoken": state.inventory.revision, "classicua": state.source.revision,
            "identity": identity, "contexts": evidence_contexts})
        choices = []
        exact_scopes = {source["scope"] for source in match.get("exact_hash_sources", ())}
        if binding:
            for scope, text in ((npc, lookup["byNpc"].get(npc, {}).get(hashed)),
                                ("!common", lookup["common"].get(hashed))):
                if text is None or audit is not None and scope not in exact_scopes:
                    continue
                leaf = state.dataset.records["gossip"][scope].fields[(hashed,)]
                ref = f"{leaf.origin.file}:{leaf.origin.line} [{scope}][{hashed}]"
                try:
                    # Shared NPC/hash mappings must be safe for every verified
                    # original, not just the first wording variant.
                    for original in originals:
                        runtime_text(original, text)
                except ValueError:
                    continue
                choices.append(review_candidate(text, "classicua", ref, state.source.revision, "candidate"))
        selected, built, stale = None, None, False
        if identity in stored:
            old, text, fingerprint, source, ref = stored[identity]
            current = old == binding and sha(text) == fingerprint and (
                source == "manual" or any(c["sha256"] == fingerprint and c["reference"] == ref for c in choices))
            if current:
                try:
                    rendered = runtime_text(originals[0], text)
                except ValueError:
                    current = False
            if current:
                selected = {"text": text, "rendered": rendered, "source": source, "reference": ref}
                if source == "manual":
                    choices.append(review_candidate(text, source, ref, state.inventory.revision, "selected"))
                unit = units.get(("gossip", f"npc:{npc}:{hashed}"))
                if unit and unit["route"] == "user_selected" and unit["text_sha256"] == sha(rendered):
                    built = unit | {"text_sha256": fingerprint}
            stale = not current
        # A single safe exact-hash ClassicUA translation needs no manual
        # selection. Two different valid translations still require a choice.
        # A stale explicit user choice must never be silently overwritten.
        if identity not in stored and binding:
            unique = {candidate["sha256"]: candidate for candidate in choices}
            if len(unique) == 1:
                candidate = next(iter(unique.values()))
                text = candidate["text"]
                rendered = runtime_text(originals[0], text)
                selected = {"text": text, "rendered": rendered,
                            "source": "classicua", "reference": candidate["reference"],
                            "auto": True}
                unit = units.get(("gossip", f"npc:{npc}:{hashed}"))
                if (unit and unit["route"] == "pinned_unique"
                        and unit["text_sha256"] == sha(rendered)):
                    built = unit | {"text_sha256": sha(text)}
        alternatives = []
        for field in ("corpus_alternate", "whitespace_candidates", "alternatives", "wrong_npc_scope",
                      "other_families", "glossary", "dynamic", "reply_only", "template_candidates"):
            for item in match.get(field, ()):
                source = item.get("source") or item
                origin = source.get("origin", source)
                scope, source_hash = source.get("scope"), source.get("hash")
                text = (lookup["common"] if scope == "!common" else lookup["byNpc"].get(scope, {})).get(source_hash)
                alternatives.append({"kind": item.get("test", field), "english": source.get("english"),
                                     "canonical_id": item.get("canonical_id"),
                                     "reference": f"{origin.get('file', '')}:{origin.get('key_line', origin.get('line', ''))}",
                                     "scope": scope, "hash": source_hash, "ukrainian": text})
        ready = selected is not None and built is None
        conflict = len({c["sha256"] for c in choices}) > 1 and selected is None
        yield {"id": identity, "type": "gossip", "label": members[0].get("npcName") or f"NPC {npc}",
               "npc_id": npc, "english_hash": hashed, "originals": originals,
               "contexts": evidence_contexts, "review_binding": binding,
               "status": "stale" if stale else status_for(
                   originals, choices, ready=ready or bool(built), conflict=conflict, unsupported=not binding),
               "mapping_state": "mapping_verified" if binding else "invalid_context",
               "translation_state": translation_state(choices), "built": built,
               "recorded": identity in stored and selected is not None,
               "ready_to_import": ready, "needs_choice": conflict, "candidate_conflict": conflict,
               "unverified_alternatives": alternatives, "candidates": choices, "selection": selected,
               "selected_sha256": sha(selected["text"]) if selected else None}


def apply_choice(action, payload, row, state, db_path, *, revalidate_inputs=False, db):
    if row["type"] != "gossip" or not row["review_binding"] or row["review_binding"] != payload["binding"]:
        raise ValueError("manager_review_context_blocked")
    if action == "choose_gossip":
        candidate = next((c for c in row["candidates"] if c["sha256"] == payload["candidate"]), None)
        if candidate is None:
            raise ValueError("manager_candidate_unavailable")
        text, source, ref = candidate["text"], candidate["provider"], candidate["reference"]
    else:
        text, source, ref = payload["text"], "manual", "local_selection"
    for original in row["originals"]:
        runtime_text(original, text)
    db.execute("""INSERT INTO gossip_simple_choices VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(identity) DO UPDATE SET evidence=excluded.evidence, text=excluded.text,
        text_sha256=excluded.text_sha256, source=excluded.source, reference=excluded.reference""",
        (row["id"], row["review_binding"], text, sha(text), source, ref))
