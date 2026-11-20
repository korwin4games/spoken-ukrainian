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


def audit_match_types(match):
    """Expose all audit match types, including those not safe for auto-selection."""
    types = []
    def add(kind):
        if kind and kind not in types:
            types.append(kind)

    for source in match.get("exact_hash_sources", ()):
        add("exact_common" if source.get("scope") == "!common" else "exact_npc")
    for kind, field in (
            ("whitespace_candidate", "whitespace_candidates"),
            ("same_template", "template_candidates"),
            ("corpus_alternate_candidate", "corpus_alternate"),
            ("wrong_npc_scope", "wrong_npc_scope"),
            ("other_family_candidate", "other_families"),
            ("glossary_candidate", "glossary"),
            ("dynamic_candidate", "dynamic"),
            ("reply_only_candidate", "reply_only"),
            ("verified_alias_wording", "alternatives")):
        for entry in match.get(field, ()):
            add(entry.get("test", kind) if kind == "same_template" else kind)
    if match.get("category") and match["category"] != "no_evidence":
        add(match["category"])
    if not types:
        add("no_evidence")
    return types


def safe_audit_candidates(match, originals, npc, state, lookup):
    """Return only unambiguous, in-scope, source-audited template/layout candidates.

    An audit lead is not an approval. Re-check every canonical original and
    source fingerprint; a changed English runtime hash is always kept as the
    target key, never copied from ClassicUA.
    """
    from tools.gossip_mapping_audit import layout_wording
    from tools.gossip_candidate_tables import template
    from tools.gossip_coverage import classicua_hash

    # A single runtime NPC/hash must not collapse variants with different
    # placeholder capitalization into one automatically rendered translation.
    # Uppercase $C/$R render differently from their lowercase forms.
    if not originals or len({tuple(sorted(Counter(TOKENS.findall(original)).items()))
                             for original in originals}) != 1:
        return []

    sources = {}
    for kind, values in (
            ("whitespace_candidate", match.get("whitespace_candidates", ())),
            ("same_template", match.get("template_candidates", ()))):
        for hit in values:
            if kind == "same_template" and hit.get("test") != "same_template":
                continue
            source = hit.get("source", hit) if kind == "same_template" else hit
            scope, source_hash = source.get("scope"), source.get("hash")
            english, path = source.get("english"), source.get("file")
            if (scope not in (npc, "!common") or type(source_hash) is not int
                    or type(english) is not str or not english or type(path) is not str
                    or source.get("effective") is not True
                    or source.get("revision") != state.source.revision
                    or state.source.files.get(path) != source.get("file_sha256")
                    or classicua_hash(english) != source_hash):
                continue
            comparison = layout_wording if kind == "whitespace_candidate" else template
            if not all(comparison(original) == comparison(english) for original in originals):
                continue
            source_record = state.dataset.records.get("gossip", {}).get(scope)
            leaf = source_record.fields.get((source_hash,)) if source_record else None
            if (leaf is None or leaf.origin.file != path
                    or leaf.origin.line != source.get("value_line")):
                continue
            value = (lookup["common"] if scope == "!common"
                     else lookup["byNpc"].get(scope, {})).get(source_hash)
            if type(value) is not str:
                continue
            try:
                for original in originals:
                    runtime_text(original, value)
            except ValueError:
                continue
            sources.setdefault((scope, source_hash), (kind, leaf, value))
    # Even identical Ukrainian bytes cannot establish which of two distinct
    # source originals was meant. Keep these as review alternatives.
    return list(sources.items())


def runtime_text(original, text):
    """Validate player-dependent placeholders and equivalent line breaks.

    Spoken $B is formatting, not a player-dependent token. ClassicUA may use
    literal paragraph breaks instead. Every original break must survive,
    while name/class/race/gender still require an exact count and type match.
    """
    forms = inventory(text)
    if (not usable_text(text) or re.search(
            r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|\|[cCrRhHtTaA]|%(?:\d+\$)?[sdif]", text)):
        raise ValueError("manager_invalid_translation_format")
    if any(form.status != "supported" for form in forms):
        raise ValueError("manager_gossip_unsupported_grammar")
    expected = Counter(t.lower() for t in TOKENS.findall(original))
    actual = Counter(t.lower() for t in TOKENS.findall(text))
    # The addon expands ClassicUA grammatical forms after loading the text.
    for form in forms:
        marker = {"player_name": "$n", "player_class": "$c",
                  "player_race": "$r", "player_gender": "$g"}.get(form.category)
        if marker is None:
            raise ValueError("manager_gossip_unsupported_grammar")
        actual[marker] += 1
    if any(token[1] not in (*RUNTIME_CODES, "g") for token in actual):
        raise ValueError("manager_gossip_unsupported_runtime_token")

    # A Ukrainian newline is the rendered equivalent of $B. Preserve at
    # least as many breaks as the source, without requiring identical layout.
    expected_breaks = expected.pop("$b", 0)
    actual_breaks = actual.pop("$b", 0) + len(re.findall(r"\r\n|\r|\n", text))
    if actual_breaks < expected_breaks:
        raise ValueError("manager_gossip_missing_linebreak")
    if expected != actual:
        raise ValueError("manager_gossip_placeholder_mismatch")
    if (len(GENDER.findall(text)) + sum(f.category == "player_gender" for f in forms)
            != actual["$g"] or any(
                not branch.strip() for pair in GENDER.findall(text) for branch in pair)):
        raise ValueError("manager_gossip_gender_invalid")
    if any(TOKENS.search(branch) for pair in GENDER.findall(text) for branch in pair):
        raise ValueError("manager_gossip_gender_invalid")
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
                choices.append(review_candidate(text, "classicua", ref, state.source.revision, "candidate")
                               | {"match_type": "exact_common" if scope == "!common" else "exact_npc"})
        ambiguous_audit = False
        auto_context_safe = match.get("category") != "ambiguous_npc_type"
        if binding and auto_context_safe and not choices and match:
            matching = safe_audit_candidates(match, originals, npc, state, lookup)
            if len(matching) == 1:
                (scope, source_hash), (kind, leaf, value) = matching[0]
                ref = f"{leaf.origin.file}:{leaf.origin.line} [{scope}][{source_hash}]"
                choices.append(review_candidate(value, "classicua", ref, state.source.revision, "candidate")
                               | {"match_type": kind})
            elif len(matching) > 1:
                ambiguous_audit = True
        selected, built, stale = None, None, False
        if identity in stored:
            old, text, fingerprint, source, ref = stored[identity]
            current = old == binding and sha(text) == fingerprint and (
                source == "manual" or any(c["sha256"] == fingerprint and c["reference"] == ref for c in choices))
            if current:
                try:
                    # Persisted choices must still fit every verified wording
                    # sharing this NPC/hash runtime identity.
                    for original in originals:
                        rendered = runtime_text(original, text)
                except ValueError:
                    current = False
            if current:
                selected = {"text": text, "rendered": rendered, "source": source, "reference": ref,
                            "match_type": next((c["match_type"] for c in choices
                                                if c["sha256"] == fingerprint and c["reference"] == ref),
                                               "manual" if source == "manual" else "unknown")}
                if source == "manual":
                    choices.append(review_candidate(text, source, ref, state.inventory.revision, "selected"))
                unit = units.get(("gossip", f"npc:{npc}:{hashed}"))
                if unit and unit["route"] == "user_selected" and unit["text_sha256"] == sha(rendered):
                    built = unit | {"text_sha256": fingerprint}
            stale = not current
        # A single safe, unambiguous ClassicUA translation needs no manual
        # selection. Ambiguous NPC types or explicit choices require review.
        # A stale explicit user choice must never be silently overwritten.
        if identity not in stored and binding and auto_context_safe:
            unique = {candidate["sha256"]: candidate for candidate in choices}
            if len(unique) == 1:
                candidate = next(iter(unique.values()))
                text = candidate["text"]
                rendered = runtime_text(originals[0], text)
                selected = {"text": text, "rendered": rendered,
                            "source": "classicua", "reference": candidate["reference"],
                            "auto": True, "match_type": candidate.get("match_type", "exact_npc")}
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
        conflict = (ambiguous_audit or len({c["sha256"] for c in choices}) > 1) and selected is None
        yield {"id": identity, "type": "gossip", "label": members[0].get("npcName") or f"NPC {npc}",
               "npc_id": npc, "english_hash": hashed, "originals": originals,
               "contexts": evidence_contexts, "review_binding": binding,
               "status": "stale" if stale else status_for(
                   originals, choices, ready=ready or bool(built), conflict=conflict, unsupported=not binding),
               "mapping_state": "mapping_verified" if binding else "invalid_context",
               "translation_state": translation_state(choices), "built": built,
               "recorded": identity in stored and selected is not None,
               "ready_to_import": ready, "needs_choice": conflict, "candidate_conflict": conflict,
               "unverified_alternatives": alternatives, "match_types": audit_match_types(match),
               "candidates": choices, "selection": selected,
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
