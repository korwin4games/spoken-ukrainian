#!/usr/bin/env python3
"""Build a private local-test ZIP for one Ukrainian localization addon.

Re-audits pinned ClassicUA/Spoken before packaging local selections or running
the full Quest import. Generated Ukrainian translations are in ignored
dist/ only. Provisional text is for an opt-in, independent quest preview panel,
NOT the official audio-gated Spoken narrator/captions and NOT a release pack.
"""
import argparse
from collections import defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from zipfile import ZipFile, ZipInfo, ZIP_STORED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.auto_one_to_one import validate_machine_ledger
from adapters.translation_approvals import _validate_ledger
from adapters.spoken import PublicSource
from adapters.classicua.source import GitSource
from adapters.classicua.lua import Parser, Table
from tools.review_ui_server import build_state, validate_source_paths, _reason
from adapters.import_summary import unique_one_to_one_hint_pairs

DIST = ROOT / "dist"
QUEST_MODULE = "Spoken_Quest_UA"
GOSSIP_MODULE = "Spoken_Gossip_UA"
MODULE_DOMAINS = {QUEST_MODULE: "quest", GOSSIP_MODULE: "gossip"}
ARCHIVES = {module: DIST / f"{module}_Local_Test.zip" for module in MODULE_DOMAINS}
ARCHIVE = ARCHIVES[QUEST_MODULE]
TEMPLATE_FILES = {
    "Spoken_Ukrainian": ("Spoken_Ukrainian.toc", "Core.lua"),
    QUEST_MODULE: (f"{QUEST_MODULE}.toc", "QuestFont.lua", "Module.lua", "NativeQuestFrame.lua",
                   "QuestJournal.lua", "GossipQuestTitles.lua", "NotoSans-Regular.ttf", "OFL-NotoSans.txt"),
    GOSSIP_MODULE: (f"{GOSSIP_MODULE}.toc", "GossipFrame.lua"),
}
QUEST_TARGET = re.compile(r"q:([1-9][0-9]*):(accept|progress|complete)(?::.*)?\Z")
QUEST_SOURCE = re.compile(r"quest:(horde|alliance):([1-9][0-9]*):(accept|progress|complete)\Z")
MAX_TEXT = 60000
UKRAINIAN_CASES = ("н", "р", "д", "з", "о", "м", "к")


def lua_quote(value):
    """Quote UTF-8 text as a Lua 5.1 literal, never as JSON/Python source."""
    if type(value) is not str or not value.strip() or len(value) > MAX_TEXT:
        raise ValueError("invalid_quest_translation_body")
    out = ['"']
    for char in value:
        code = ord(char)
        if char == "\\":
            out.append("\\\\")
        elif char == '"':
            out.append('\\"')
        elif char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        elif char == "\t":
            out.append("\\t")
        elif code < 32 or code == 127:
            out.append("\\%03d" % code)
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def current_quest_texts(state, selected_out=None, agent_rows=(), *, skipped=None):
    """Only currently imported references after real full-source revalidation."""
    machine = validate_machine_ledger(state.machine_imports.file.data)
    reviewed = _validate_ledger(state.translations.file.data)
    version_by_id = {v["id"]: v for v in reviewed["versions"]}
    machine_by_id = {v["id"]: v for v in machine["versions"]}
    texts = {}
    from adapters.crosswalk import quest_moment
    from adapters.spoken.text_index import ambiguous_quest_moments
    blocked = (state.blocked_quest_moments() if hasattr(state, "blocked_quest_moments") else set())
    index = getattr(state, "original_index", None)
    ambiguous = ambiguous_quest_moments(index)
    wordings = defaultdict(set)
    for target, wording in getattr(index, "original_english", {}).items():
        if QUEST_TARGET.fullmatch(target):
            wordings[quest_moment(target)].add(wording)
    ambiguous.update(moment for moment, variants in wordings.items() if len(variants) > 1)

    def excluded(target):
        moment = quest_moment(target)
        reason = ("quest_mapping_rejected_or_deferred" if moment in blocked else
                  "quest_multiple_verified_originals" if moment in ambiguous else None)
        if reason and skipped is not None and (target, reason) not in skipped:
            skipped.append((target, reason))
        return reason is not None

    conflicted_moments = set()
    supporting_fields = defaultdict(lambda: {"title": set(), "objective": set()})
    source_views = None
    for imports, versions, human in (
            (machine["imports"], machine_by_id, False),
            (reviewed["imports"], version_by_id, True)):
        for ref in imports:
            target_id = ref["target_id"]
            if target_id in texts:
                raise ValueError("duplicate_canonical_quest_import")
            if target_id not in state.inventory.targets:
                raise ValueError("unrecognized_canonical_quest_import")
            if state.inventory.targets[target_id].family != "quest":
                raise ValueError("unexpected_nonquest_import")
            if not QUEST_TARGET.fullmatch(target_id):
                raise ValueError("invalid_canonical_quest_id")
            if excluded(target_id):
                continue
            row = versions[ref["version_id"]]
            if row["target_id"] != target_id:
                raise ValueError("quest_import_target_mismatch")
            if not human and row["decision"] != "machine_1to1_provisional":
                raise ValueError("machine_translation_not_provisional")
            if human and row["kind"] not in ("manual", "provider"):
                raise ValueError("invalid_human_import_version")
            if not row["text"].strip():
                raise ValueError("blank_quest_import")
            texts[target_id] = {"text": row["text"], "reviewed": human}
            # The Quest title is ClassicUA field [1], not a Spoken
            # narration event. Read it only from the audited source unit
            # bound to this imported Quest ID/event; never guess by title.
            source_match = QUEST_SOURCE.fullmatch(row.get("source_id", ""))
            target_match = QUEST_TARGET.fullmatch(target_id)
            if (source_match is not None
                    and int(source_match.group(2)) == int(target_match.group(1))
                    and source_match.group(3) == target_match.group(2)
                    and source_match.group(0) in state.source.units):
                if source_views is None:
                    source_views, _ = state.dataset.faction_views(include_ai=True)
                record = source_views[source_match.group(1)].get(int(source_match.group(2)))
                for key, slot, limit in (("title", 1, 500), ("objective", 3, MAX_TEXT)):
                    leaf = record.fields.get((slot,)) if record else None
                    if leaf and isinstance(leaf.node.value, str):
                        value = leaf.node.value.strip()
                        if value and len(value) <= limit:
                            supporting_fields[int(source_match.group(2))][key].add(value)

    for row in agent_rows:
        if row["domain"] == "quest":
            target = row["target_id"]
            if not excluded(target) and not texts.get(target, {}).get("reviewed"):
                texts[target] = {"text": row["text"], "reviewed": False}

    # A source-review Quest override is valid only on top of a separately
    # human-approved Stage 3 Spoken ↔ source mapping. Pinned English, target
    # and canonical context must still match. Manual Quest Translation Review
    # and explicit source selection must not silently contradict one another.
    from adapters.sqlite_translation_store import DB_ENV
    db_path = os.environ.get(DB_ENV)
    if db_path:
        from adapters.source_revision_store import SourceReviewStore
        from tools.source_revision_review import quest_contexts
        selected_quest = SourceReviewStore(db_path).active(
            quest_contexts(state), domain="quest", skipped=skipped)
        if selected_quest:
            mapped = {o.target_id for o in state.translation_observations()}
            for selection in selected_quest:
                target = selection["target_id"]
                if excluded(target):
                    continue
                if target not in mapped:
                    if skipped is not None:
                        skipped.append((target, "source_quest_selection_requires_approved_stage3_mapping"))
                        continue
                    raise ValueError("source_quest_selection_requires_approved_stage3_mapping")
                already = texts.get(target)
                if (already and already["reviewed"]
                        and already["text"] != selection["ukrainian_text"]):
                    if skipped is not None:
                        skipped.append((target, "conflicting_human_reviewed_quest_selection"))
                        conflicted_moments.add(QUEST_TARGET.fullmatch(target).groups())
                        continue
                    raise ValueError("conflicting_human_reviewed_quest_selection")
                texts[target] = {"text": selection["ukrainian_text"], "reviewed": True}
                if selected_out is not None:
                    selected_out.append(selection)
    # The preview only has QuestID and event from public WoW functions.
    # It cannot choose between different NPC voice / wording variants;
    # skip the whole moment when their texts conflict.
    moments = defaultdict(list)
    for target, data in texts.items():
        quest, event = QUEST_TARGET.fullmatch(target).groups()
        if (quest, event) in conflicted_moments:
            continue
        moments[(int(quest), event)].append(data)
    result = {}
    skipped_count = 0
    for (quest, event), rows in sorted(moments.items()):
        unique_texts = {row["text"] for row in rows}
        if len(unique_texts) != 1:
            if skipped is not None:
                skipped.append((f"q:{quest}:{event}", "conflicting_quest_runtime_variants"))
            skipped_count += len(rows)
            continue
        result.setdefault(quest, {})[event] = {
            "text": rows[0]["text"],
            "reviewed": all(row["reviewed"] for row in rows),
        }
    if db_path:
        from tools.quest_runtime_review import approved
        for moment, review in approved(state, db_path, skipped).items():
            _, quest_id, event = moment.split(":")
            quest = int(quest_id)
            if review is None:
                if quest in result:
                    result[quest].pop(event, None)
                    if not result[quest]:
                        del result[quest]
            else:
                if (quest, event) in conflicted_moments:
                    continue
                result.setdefault(quest, {})[event] = {
                    "text": review["text"], "reviewed": True, "review_source": review["source"],
                }
    # Conflicting source factions stay ambiguous: omit unsupported fields.
    for quest, fields in supporting_fields.items():
        if quest in result:
            for key, candidates in fields.items():
                if len(candidates) == 1:
                    result[quest][key] = next(iter(candidates))
    # Local choices are private test-pack preferences, not fabricated approvals.
    from tools.quest_simple import resolved as simple_resolved
    for moment, choice in simple_resolved(state, db_path).items():
        _, number, event = moment.split(":")
        quest = int(number)
        if choice.get("conflict"):
            if quest in result:
                result[quest].pop(event, None)
                if not result[quest]:
                    del result[quest]
            if skipped is not None:
                skipped.append((moment, "quest_choice_required"))
            continue
        if not choice["selected"] and event in result.get(quest, {}):
            continue
        result.setdefault(quest, {})[event] = {
            "text": choice["text"], "reviewed": False, "quick": True,
            "quick_source": choice["source"], "quick_selected": choice["selected"],
        }
        for field in ("title", "objective"):
            if field in choice and field not in result[quest]:
                result[quest][field] = choice[field]
    return result, len(texts), skipped_count


def read_classicua_inflections(classicua_path, source_files):
    """Read exact audited ClassicUA grammatical forms for a local preview.

    These are embedded only in the user's private ZIP. No ClassicUA Lua
    executes: the pinned data files are parsed as literal tables.
    """
    reader = GitSource(classicua_path)
    result = {}
    for kind in ("race", "class"):
        path = "entries/" + kind + ".lua"
        text = reader.read(path)
        if reader.hashes[path] != source_files.get(path):
            raise ValueError("classicua_grammar_source_hash_changed")
        # Grammar source files append executable compatibility loops and aliases
        # after their literal tables. Parse ONLY the pinned literal constructor,
        # never execute or attempt to interpret the trailing Lua statements.
        match = re.search(r"^addonTable\." + kind + r"\s*=\s*(?=\{)", text, re.MULTILINE)
        if match is None:
            raise ValueError("invalid_classicua_grammar_table")
        node = Parser(text[match.end():], path).value()
        if not isinstance(node.value, Table):
            raise ValueError("invalid_classicua_grammar_table")
        groups = {}
        for key, record in node.value.effective().items():
            if (type(key) is not str or not key
                    or not isinstance(record.value.value, Table)):
                raise ValueError("invalid_classicua_grammar_entry")
            forms = {}
            for case, values in record.value.value.effective().items():
                if case not in UKRAINIAN_CASES or not isinstance(values.value.value, Table):
                    continue
                seq = values.value.value.effective()
                male, female = seq.get(1), seq.get(2)
                if (male is None or female is None or
                        any(type(item.value.value) is not str or not item.value.value.strip()
                            or len(item.value.value) > 128 for item in (male, female))):
                    raise ValueError("invalid_classicua_gender_forms")
                forms[case] = (male.value.value, female.value.value)
            if "н" not in forms:
                raise ValueError("missing_classicua_nominative")
            groups[key] = forms
        if not groups:
            raise ValueError("missing_classicua_grammar_entries")
        result[kind] = groups
    return result


def local_gossip_titles(state):
    """Title-only lookup by EXACT questID and faction from pinned ClassicUA.

    This is independent of Spoken narrated Quest accept/progress/complete.
    It never upgrades a title to a reviewed mapping/Quest narration. Exclude
    AI-marked titles when the user's explicit import policy opts out.
    """
    allow_ai = state.policy.allows_ai_transations("classicua")
    views, _ = state.dataset.faction_views(include_ai=allow_ai)
    titles = {}
    for faction in ("alliance", "horde"):
        rows = {}
        for quest_id, record in views[faction].items():
            if type(quest_id) is not int or quest_id <= 0:
                continue
            if record.ai and not allow_ai:
                continue
            field = record.fields.get((1,))
            if not field or type(field.node.value) is not str:
                continue
            title = field.node.value.strip()
            if not title or len(title) > 500:
                continue
            # No unpinned third-party source file is trusted for this export.
            if field.origin.file not in state.source.files:
                raise ValueError("unverified_classicua_quest_title_source")
            rows[quest_id] = title
        titles[faction] = rows
    return titles


def import_reason_for_quest(state, quest_id):
    """Metadata-only Quest diagnostic, with no source text exposed."""
    if type(quest_id) is not int or quest_id <= 0:
        raise ValueError("invalid_diagnostic_quest_id")
    prefix = "q:" + str(quest_id) + ":"
    targets = sorted(k for k, target in state.inventory.targets.items()
                     if target.family == "quest" and k.startswith(prefix))
    hints = [row for row in state._hints
             if row["source_id"].startswith("quest:")
             and row["source_id"].split(":")[2] == str(quest_id)]
    refs = [row["target_id"] for store in
            (state.machine_imports.file.data, state.translations.file.data)
            for row in store.get("imports", [])
            if row["target_id"].startswith(prefix)]
    eligible = unique_one_to_one_hint_pairs(
        state._hints, state.source.units, state.inventory,
        allow_ai_transations=state.policy.allows_ai_transations("classicua"))
    source_rows = []
    for row in hints:
        source_id = row["source_id"]
        source_rows.append({
            "source_event": source_id.split(":")[-1],
            "faction": source_id.split(":")[1],
            "candidate_count": len(row["candidates"]),
            "eligible_strict_one_to_one": any(pair[0] == source_id for pair in eligible),
            "candidate_contexts": [
                {"identity": target_id,
                 "contexts": len(state.inventory.contexts.get(target_id, ())),
                 "factions": sorted({ctx.get("faction", "?") for ctx in
                     state.inventory.contexts.get(target_id, ())}),
                 "verified_english": target_id in state.original_index.original_english}
                for target_id in row["candidates"] if target_id in state.inventory.targets],
        })
    return {"quest_id": quest_id,
            "spoken_narrated_targets": len(targets),
            "classicua_candidates": len(hints),
            "candidate_reasons": sorted({row["reason"] for row in hints}),
            "source_events": source_rows,
            "auto_imported_targets": len(set(refs)),
            "allow_ai_transations": state.policy.allows_ai_transations("classicua")}


def unknown_faction_import_counts(state):
    """Metadata-only counts of CURRENT imported records lacking Spoken faction.

    Unknown is not evidence of either Horde or Alliance. These are private
    local-test records, never an automatic human mapping approval. Count
    target IDs (not source texts) after the importer has validated its ledgers.
    """
    summary = {"machine_provisional": 0, "human_reviewed": 0}
    for label, ledger in (
            ("machine_provisional", state.machine_imports.file.data),
            ("human_reviewed", state.translations.file.data)):
        seen = set()
        for ref in ledger["imports"]:
            target = ref["target_id"]
            if target in seen:
                raise ValueError("duplicate_quest_faction_import_target")
            seen.add(target)
            contexts = state.inventory.contexts.get(target, ())
            if len(contexts) == 1 and contexts[0].get("faction") == "unknown":
                summary[label] += 1
    return summary


def local_gossip_texts(state):
    """Only effective, pinned ClassicUA NPC/hash text entries for local testing.

    ClassicUA gossip hashes identify normalized English display wording.
    They are not Spoken line IDs and do NOT create approved Spoken mappings.
    Ignore dynamic "!code" patterns because they cannot be verified by an
    exact English hash; absence of a match means keep native English.
    """
    allow_ai = state.policy.allows_ai_transations("classicua")
    result = {"byNpc": {}, "common": {}}
    records = state.dataset.records.get("gossip", {})
    for key, record in sorted(records.items(), key=lambda item: str(item[0])):
        if key == "!common":
            dest = result["common"]
        elif type(key) is int and key > 0:
            dest = {}
        else:
            continue
        if record.ai and not allow_ai:
            continue
        for slot, leaf in record.fields.items():
            if (len(slot) != 1 or type(slot[0]) is not int or slot[0] <= 0
                    or slot[0] >= 4294967291):
                continue
            text = leaf.node.value
            if type(text) is not str or not text.strip() or len(text) > MAX_TEXT:
                continue
            if (state.source.files.get(leaf.origin.file) != leaf.origin.sha256
                    or leaf.origin.revision != state.source.revision):
                raise ValueError("unverified_classicua_gossip_source")
            digest = slot[0]
            if digest in dest and dest[digest] != text:
                raise ValueError("conflicting_classicua_gossip_hash")
            dest[digest] = text
        if type(key) is int and dest:
            result["byNpc"][key] = dest
    return result


def render_gossip_lua(gossip, *, excluded=(), inflections=None):
    """UTF-8 Lua data table, packed into private ignored ZIP only."""
    if type(gossip) is not dict or set(gossip) != {"byNpc", "common"}:
        raise ValueError("invalid_gossip_lookup")
    lines = [
        "-- GENERATED local test from audited source and human-reviewed Gossip hashes.",
        "-- Not an approved Spoken Gossip text mapping; no audio files included.",
        "SpokenUkrainian = SpokenUkrainian or {}",
        *inflection_lines(inflections),
        "SpokenUkrainian.GossipTexts = {",
        "    byNpc = {",
    ]
    for npcID, rows in sorted(gossip["byNpc"].items()):
        if type(npcID) is not int or npcID <= 0 or type(rows) is not dict:
            raise ValueError("invalid_gossip_npc_id")
        lines.append("        [%d] = {" % npcID)
        for digest, value in sorted(rows.items()):
            if type(digest) is not int or not 0 < digest < 4294967291:
                raise ValueError("invalid_gossip_text_hash")
            lines.append("            [%d] = %s," % (digest, lua_quote(value)))
        lines.append("        },")
    lines.append("    },")
    lines.append("    common = {")
    for digest, value in sorted(gossip["common"].items()):
        if type(digest) is not int or not 0 < digest < 4294967291:
            raise ValueError("invalid_gossip_common_hash")
        lines.append("        [%d] = %s," % (digest, lua_quote(value)))
    lines.append("    },")
    if excluded:
        by_npc = defaultdict(list)
        for npc, hashed in excluded:
            if type(npc) is not int or npc <= 0 or type(hashed) is not int or not 0 < hashed < 4294967291:
                raise ValueError("invalid_gossip_exclusion")
            by_npc[npc].append(hashed)
        lines.append("    excluded = {")
        for npc, hashes in sorted(by_npc.items()):
            lines.append("        [%d] = {%s}," % (
                npc, ", ".join("[%d] = true" % hashed for hashed in sorted(hashes))))
        lines.append("    },")
    lines.append("}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def render_quest_lua(preview, pinned_spoken_sha, inflections=None, gossip_titles=None):
    if not re.fullmatch(r"[a-f0-9]{40}", pinned_spoken_sha):
        raise ValueError("invalid_spoken_pin")
    lines = [
        "-- GENERATED local test from pinned, audited Quest imports. Never edit.",
        "-- NOT RELEASE-READY. machine 1:1 entries lack human Stage 3 mapping review.",
        "-- No recordings, synthetic sound lengths or playback metadata.",
        "SpokenUkrainian = SpokenUkrainian or {}",
    ]
    lines.extend(inflection_lines(inflections))
    lines.extend(quest_lines(preview, gossip_titles))
    return ("\n".join(lines) + "\n").encode("utf-8")


def inflection_lines(inflections):
    lines = ["SpokenUkrainian.Inflections = {"]
    for kind, groups in sorted((inflections or {}).items()):
        if kind not in ("class", "race") or type(groups) is not dict:
            raise ValueError("invalid_build_inflection_group")
        lines.append("    [" + lua_quote(kind) + "] = {")
        for key, forms in sorted(groups.items()):
            lines.append("        [" + lua_quote(key) + "] = {")
            for case, pair in sorted(forms.items()):
                if case not in UKRAINIAN_CASES or len(pair) != 2:
                    raise ValueError("invalid_build_inflection_case")
                lines.append("            [" + lua_quote(case) + "] = {"
                             + lua_quote(pair[0]) + ", " + lua_quote(pair[1]) + "},")
            lines.append("        },")
        lines.append("    },")
    lines.append("}")
    return lines


def quest_lines(preview, gossip_titles):
    lines = []
    # Gossip has reliable per-row questID on WoW Forever. Titles are
    # independently sourced, provisional, and NEVER counted as narration.
    lines.append("SpokenUkrainian.GossipQuestTitles = {")
    for faction, rows in sorted((gossip_titles or {}).items()):
        if faction not in ("alliance", "horde") or type(rows) is not dict:
            raise ValueError("invalid_gossip_title_faction")
        lines.append("    [" + lua_quote(faction) + "] = {")
        for quest_id, title in sorted(rows.items()):
            if type(quest_id) is not int or quest_id <= 0 or type(title) is not str:
                raise ValueError("invalid_gossip_title_entry")
            if len(title) > 500:
                raise ValueError("oversized_gossip_title")
            lines.append("        [%d] = %s," % (quest_id, lua_quote(title)))
        lines.append("    },")
    lines.append("}")
    lines.append("SpokenUkrainian.QuestTranslations = {")
    for quest, events in sorted(preview.items()):
        if type(quest) is not int or quest < 1:
            raise ValueError("invalid_quest_id")
        lines.append("    [%d] = {" % quest)
        for field_name in ("title", "objective"):
            if type(events.get(field_name)) is str and events[field_name].strip():
                lines.append("        " + field_name + " = " + lua_quote(events[field_name]) + ",")
        for event in ("accept", "progress", "complete"):
            if event in events:
                row = events[event]
                lines.append("        %s = { text = %s, reviewed = %s%s }," % (
                    event, lua_quote(row["text"]),
                    "true" if row["reviewed"] else "false",
                    ", quick = true" if row.get("quick") else ""))
        lines.append("    },")
    lines.append("}")
    return lines


def template_entries(preview_lua=None, gossip_lua=None, *, module=QUEST_MODULE, text_pack_lua=None):
    if module not in MODULE_DOMAINS:
        raise ValueError("manager_unknown_module")
    entries = {}
    for folder in ("Spoken_Ukrainian", module):
        directory = ROOT / "addons" / folder
        expected = set(TEMPLATE_FILES[folder])
        if directory.is_symlink() or not directory.is_dir() or {
                p.name for p in directory.iterdir()} != expected:
            raise ValueError("unexpected_ukrainian_addon_template")
        for name in TEMPLATE_FILES[folder]:
            path = directory / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("unsafe_ukrainian_addon_template")
            content = path.read_bytes()
            entries[folder + "/" + name] = content if path.suffix == ".ttf" else content.replace(b"\r\n", b"\n")
    base_toc = entries["Spoken_Ukrainian/Spoken_Ukrainian.toc"].decode("utf-8").replace("\r\n", "\n")
    toc = entries[f"{module}/{module}.toc"].decode("utf-8").replace("\r\n", "\n")
    for required in (
            "## Title: Spoken Ukrainian\n",
            "## Dependencies: Spoken\n",
            "Core.lua\n"):
        if required not in base_toc:
            raise ValueError("missing_base_ukrainian_toc_contract")
    from tools.spoken_text_pack import render_spoken_text_pack

    if module == GOSSIP_MODULE:
        if ("## Dependencies: Spoken_Ukrainian\n" not in toc
                or "## X-Spoken-Text: ukUA\n" not in toc
                or "## X-Spoken-TextFormat: 1\n" not in toc
                or "## X-Spoken-LanguageFont: NotoSans-Regular.ttf\n" not in toc
                or "GossipTranslations.lua\nTextPack.lua\nGossipFrame.lua\n" not in toc):
            raise ValueError("missing_gossip_ukrainian_toc_contract")
        # Keep the native Gossip addon independent from Quest, including its font.
        # Reuse the audited/licensed font bytes instead of committing a duplicate.
        for name in ("NotoSans-Regular.ttf", "OFL-NotoSans.txt"):
            source = ROOT / "addons" / QUEST_MODULE / name
            if source.is_symlink() or not source.is_file():
                raise ValueError("unsafe_ukrainian_addon_template")
            entries[f"{module}/{name}"] = source.read_bytes()
        entries[f"{module}/GossipTranslations.lua"] = gossip_lua
        entries[f"{module}/TextPack.lua"] = (
            text_pack_lua if text_pack_lua is not None else render_spoken_text_pack())
        return entries
    for required in (
            "## Title: Spoken Ukrainian: Quests\n",
            "## Dependencies: Spoken, Spoken_Ukrainian\n",
            "## X-Spoken-Text: ukUA\n",
            "## X-Spoken-TextFormat: 1\n",
            "## X-Spoken-LanguageFont: NotoSans-Regular.ttf\n",
            "Translations.lua\nTextPack.lua\nQuestFont.lua\nModule.lua\nNativeQuestFrame.lua\nQuestJournal.lua\nGossipQuestTitles.lua\n"):
        if required not in toc:
            raise ValueError("missing_quest_ukrainian_toc_contract")
    # Module must never invent sound files or call AddOn playback.
    module = entries["Spoken_Quest_UA/Module.lua"].decode("utf-8")
    frame_code = entries["Spoken_Quest_UA/NativeQuestFrame.lua"].decode("utf-8")
    if not all(symbol in frame_code for symbol in (
            "MODIFIER_STATE_CHANGED", "hooksecurefunc", "GetQuestID",
            "IsShiftKeyDown", "QuestProgressText")):
        raise ValueError("missing_native_questframe_translation_contract")
    gossip_code = entries["Spoken_Quest_UA/GossipQuestTitles.lua"].decode("utf-8")
    if not all(symbol in gossip_code for symbol in (
            "GossipAvailableQuestButtonMixin", "QuestFrameGreetingPanel",
            "GetAvailableQuestInfo", "UnitFactionGroup", "IsShiftKeyDown")):
        raise ValueError("missing_gossip_quest_title_contract")
    if "QUEST_DETAIL" not in module or "SoundLengthLookupByFileName" in module:
        raise ValueError("missing_quest_text_pack_contract")
    entries["Spoken_Quest_UA/Translations.lua"] = preview_lua
    entries["Spoken_Quest_UA/TextPack.lua"] = (
        text_pack_lua if text_pack_lua is not None else render_spoken_text_pack())
    return entries


def write_zip(entries, destination=ARCHIVE):
    """Deterministic, fail-closed and atomic private local-test ZIP."""
    destination = Path(destination).resolve()
    if destination.parent != DIST.resolve() or destination.suffix != ".zip":
        raise ValueError("zip_output_must_be_under_ignored_dist")
    if any(part in ("..", "") for part in destination.parts):
        raise ValueError("unsafe_output_path")
    if DIST.is_symlink() or destination.is_symlink():
        raise ValueError("unsafe_dist_symlink")
    DIST.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")
    if temp.exists() or temp.is_symlink():
        raise ValueError("old_temporary_build_file")
    try:
        with ZipFile(temp, "w", compression=ZIP_STORED) as archive:
            for name, content in sorted(entries.items()):
                if (name.startswith("/") or "\\" in name or ".." in name.split("/")
                        or name.split("/")[0] not in TEMPLATE_FILES):
                    raise ValueError("unsafe_ukrainian_archive_name")
                item = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                item.create_system = 3
                item.external_attr = 0o100644 << 16
                archive.writestr(item, content)
        os.replace(temp, destination)
    finally:
        if temp.exists():
            temp.unlink()
    sha = sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(
        sha + "  " + destination.name + "\n", encoding="ascii")
    return destination, sha


def local_test_state(classicua, spoken):
    validate_source_paths(classicua, spoken)
    return build_state(
        classicua, spoken,
        ROOT / "build/stage4b-decisions.json",
        None,
        ROOT / "build/stage3-ui-reviews.json",
        ROOT / "build/translation-reviews.json",
        ROOT / "config/translation_sources.json")


def build_gossip(classicua, spoken, destination):
    from adapters.import_statistics import store_successful_build
    from adapters.source_revision_store import sha
    from adapters.sqlite_translation_store import DB_ENV, default_db_path
    from tools.manager_inventory import load_inventory

    db_path = Path(os.environ.get(DB_ENV) or default_db_path())
    archive = ARCHIVES[GOSSIP_MODULE] if destination is None else destination
    view = load_inventory(classicua, spoken, db_path, archive, module=GOSSIP_MODULE)
    gossip = {"byNpc": {}, "common": {}}
    units = []
    for row in view.rows.values():
        selection = row["selection"]
        # A stale saved decision is not an eligible import, but should not
        # prevent other ready Gossip records from entering the new ZIP.
        if row["status"] == "stale":
            continue
        if selection is None:
            continue
        npc, hashed = row["npc_id"], row["english_hash"]
        gossip["byNpc"].setdefault(npc, {})[hashed] = selection["rendered"]
        units.append({"domain": "gossip", "unit": f"npc:{npc}:{hashed}", "entity": str(npc),
                      "source": selection["source"],
                      "route": "pinned_unique" if selection.get("auto") else "user_selected",
                      "text_sha256": sha(selection["rendered"])})
    forms = read_classicua_inflections(classicua, view.state.source.files)
    from tools.spoken_text_pack import gossip_payload, render_spoken_text_pack

    from tools.gossip_coverage import read_pinned_corpus
    text_lines = gossip_payload(
        view.rows.values(), corpus_lines=read_pinned_corpus(spoken, view.state.inventory.revision))
    entries = template_entries(
        None, render_gossip_lua(gossip, inflections=forms), module=GOSSIP_MODULE,
        text_pack_lua=render_spoken_text_pack(lines=text_lines))
    artifact, digest = write_zip(entries, archive)
    imported = store_successful_build(
        db_path, artifact_sha256=digest, module=GOSSIP_MODULE, rows=units,
        spoken_revision=view.state.inventory.revision, classicua_revision=view.state.source.revision)
    return {"artifact": artifact, "sha256": digest, "import_inventory": imported,
            "gossip_text_records": {"npc_ids": len(gossip["byNpc"]), "npc_hashes": len(units),
                                    "common_hashes": 0}}


def build(classicua, spoken, *, module=QUEST_MODULE, before_import=None, prepare=None,
          destination=None, skipped=None, incremental=False):
    """Build one private addon using its pinned module-specific selection rules."""
    if module not in MODULE_DOMAINS:
        raise ValueError("manager_unknown_module")
    is_quest = module == QUEST_MODULE
    classicua, spoken = Path(classicua), Path(spoken)
    if not is_quest:
        if before_import is not None:
            raise ValueError("manager_invalid_review_request")
        return build_gossip(classicua, spoken, destination)
    state = local_test_state(classicua, spoken)
    previous, ready = {}, set()
    if incremental:
        from adapters.sqlite_translation_store import DB_ENV
        from tools.manager_inventory import load_inventory
        from tools.quest_incremental import previous_snapshot
        db_path = os.environ.get(DB_ENV)
        if not db_path:
            raise ValueError("manager_incremental_database_required")
        previous, _ = previous_snapshot(db_path, ARCHIVES[module],
                                        state.inventory.revision, state.source.revision)
        catalog = load_inventory(classicua, spoken, db_path, ARCHIVES[module],
                                 module=module, state=state)
        ready = {identity for identity, row in catalog.rows.items()
                 if row.get("ready_to_import")}
    if before_import is not None:
        before_import(state)
    # Explicitly call the *same* guarded UI/CLI action. Re-check current
    # canonical mappings, source bytes, rights policy and source versions.
    report = {}
    if is_quest and not incremental:
        report = state.translation_action(
            "auto_import_one_to_one", {"source": "classicua"},
            **({} if skipped is None else {"skipped": skipped}))["report"]
    if prepare is not None:
        prepare(state)
    from adapters.sqlite_translation_store import DB_ENV
    from adapters.translation_agent import TranslationAgent, has_imports
    db_path = os.environ.get(DB_ENV)
    agent_rows = ()
    if db_path and has_imports(db_path):
        from tools.translation_agent import evidence
        agent_rows = TranslationAgent(db_path, lambda: evidence(state, spoken, db_path)).effective_imports()
    selected_quest = []
    agent_rows = [row for row in agent_rows if row["domain"] == MODULE_DOMAINS[module]]
    if not is_quest:
        preview, imported, ambiguous = {}, 0, 0
    elif agent_rows or skipped is not None:
        preview, imported, ambiguous = current_quest_texts(
            state, selected_quest, agent_rows, skipped=skipped)
    else:
        preview, imported, ambiguous = current_quest_texts(state, selected_quest)
    if incremental:
        from tools.quest_incremental import merge_ready
        preview = merge_ready(previous, preview, ready)
    preview_count = sum(event in ("accept", "progress", "complete")
                        for events in preview.values() for event in events)
    if is_quest and not preview_count:
        raise ValueError("no_unambiguous_quest_imports_for_local_test_pack")
    unknown_factions = unknown_faction_import_counts(state) if is_quest else {}
    forms = read_classicua_inflections(classicua, state.source.files)
    titles = local_gossip_titles(state) if is_quest else {}
    gossip, reviewed_gossip, selected_gossip, excluded_gossip, source_proofs, gossip_page = (
        {"byNpc": {}, "common": {}}, {}, [], {}, {}, {})
    from tools.spoken_text_pack import quest_payload, quest_source_moments, render_spoken_text_pack

    text_titles, text_lines = quest_payload(
        preview, source_moments=quest_source_moments(state), faction_titles=titles)
    entries = template_entries(
        render_quest_lua(preview, state.inventory.revision, forms, titles) if is_quest else None,
        render_gossip_lua(gossip, excluded=excluded_gossip, inflections=forms) if not is_quest else None,
        module=module, text_pack_lua=render_spoken_text_pack(text_titles, text_lines))
    import_inventory = None
    if db_path:
        from adapters.import_statistics import store_successful_build
        from tools.import_build_inventory import collect_build_rows
        inventory_rows = collect_build_rows(
            state, preview, gossip, titles, reviewed_gossip,
            selected_gossip, selected_quest, source_proofs, db_path, machine_gossip=gossip,
            agent_rows=agent_rows, excluded_gossip=excluded_gossip)
    artifact, digest = write_zip(entries, ARCHIVES[module] if destination is None else destination)
    if db_path:
        import_inventory = store_successful_build(
            db_path, artifact_sha256=digest, module=module,
            spoken_revision=state.inventory.revision,
            classicua_revision=state.source.revision,
            rows=inventory_rows)
    return {
        "artifact": artifact, "sha256": digest,
        "import_inventory": import_inventory,
        "reported_total_spoken": report.get("total_spoken_records", 0),
        "imported_quest_records": imported,
        "previewable_quest_moments": preview_count,
        "skipped_ambiguous_preview_variants": ambiguous,
        "machine_provisional": report.get("machine_one_to_one_imported", 0),
        "human_reviewed": report.get("human_reviewed_imported_total", 0),
        "title_only_gossip_records": {k: len(v) for k, v in titles.items()},
        "gossip_text_records": {
            "npc_ids": len(gossip["byNpc"]),
            "npc_hashes": sum(len(v) for v in gossip["byNpc"].values()),
            "common_hashes": len(gossip["common"]),
        },
        "reviewed_gossip_text_records": {
            "npc_ids": len(reviewed_gossip),
            "npc_hashes": sum(len(rows) for rows in reviewed_gossip.values()),
        },
        "explicit_source_gossip_selections": len(selected_gossip),
        "gossip_machine_import": gossip_page,
        "unknown_faction_imports": unknown_factions,
        "quest_97279": import_reason_for_quest(state, 97279) if is_quest else {},
        "report": report,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classicua", type=Path, required=True,
                        help="Local CLEAN Git checkout at sources.lock.json pinned ClassicUA commit")
    parser.add_argument("--module", choices=tuple(MODULE_DOMAINS), default=QUEST_MODULE)
    parser.add_argument("--spoken", type=Path, required=True,
                        help="Local CLEAN Git checkout at sources.lock.json pinned Spoken commit")
    args = parser.parse_args(argv)
    print(f"Spoken Ukrainian local TEST build for {args.module}...",
          flush=True)
    try:
        from adapters.sqlite_translation_store import DB_ENV, default_db_path
        from tools.translation_manager import reimport
        result = reimport(args.classicua, args.spoken, os.environ.get(DB_ENV) or default_db_path(),
                          module=args.module, confirm=True)
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print("Module build failed reason=" + _reason(exc), file=sys.stderr)
        return 1
    print("Local test ZIP:", result["artifact"])
    print("SHA-256:", result["sha256"])
    return 0


if __name__ == "__main__":
    # Executed CLIs use the persistent SQLite store by default. Test/library
    # direct calls retain their explicit isolated JSON fixture backend.
    import os
    from adapters.sqlite_translation_store import enable_sqlite, DB_ENV
    with enable_sqlite(os.environ.get(DB_ENV)):
        raise SystemExit(main())
