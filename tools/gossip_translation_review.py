#!/usr/bin/env python3
"""Private Gossip translation batches, versioned review and gated local import.

Source texts/proposals live only under ignored build/. No provider API is called;
a user-controlled translator may fill the batch JSON. None of this is audio,
native Spoken caption approval, or public release.
"""
import argparse
import os
from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.local_review_store import LocalFile, strict_json
from tools.gossip_coverage import classicua_hash, read_pinned_corpus

CHECKS = ("text", "grammar", "ai", "rights", "all_contexts")
EMPTY = {"schema_version": 1, "versions": [], "imports": []}
LEDGER = ROOT / "build/gossip-translation-reviews.json"
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
HEX40 = re.compile(r"[a-f0-9]{40}\Z")
PROVIDERS = ("own_translator", "manual")
DECISIONS = ("approved", "rejected", "deferred")


def digest(obj):
    return sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def text_hash(text):
    return sha256(text.encode("utf-8")).hexdigest()


def normalized(text):
    if type(text) is not str:
        return ""
    value = re.sub(" +", " ", text.replace("\u00a0", " ")).strip(" \t\n\r\v\f")
    return value.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                                        "abcdefghijklmnopqrstuvwxyz"))


def discover_groups(lines, gossip, spoken_rev, classicua_rev):
    """Deduplicate equal English text, preserving exact NPC ID/hash for every use."""
    if not (isinstance(lines, list) and isinstance(gossip, dict)
            and set(gossip) == {"byNpc", "common"}
            and HEX40.fullmatch(spoken_rev) and HEX40.fullmatch(classicua_rev)):
        raise ValueError("invalid_gossip_review_inputs")
    groups, by_npc_hash, collisions = {}, {}, set()
    gossip_rows = non_npc = 0
    for row in lines:
        if type(row) is not dict:
            raise ValueError("invalid_gossip_review_row")
        if row.get("source") != "gossip":
            continue
        gossip_rows += 1
        npc = row.get("npcId")
        if row.get("npcType") not in ("creature", "vehicle") or type(npc) is not int or npc <= 0:
            non_npc += 1
            continue
        english = row.get("originalText")
        if type(english) is not str or not english.strip():
            english = row.get("text")
        clean, hash_value = normalized(english), classicua_hash(english)
        display = re.sub(" +", " ", english.replace("\u00a0", " ")).strip(" \t\n\r\v\f") \
            if type(english) is str else ""
        if not clean or not hash_value:
            continue
        if (hash_value in gossip["byNpc"].get(npc, {})
                or hash_value in gossip["common"]):
            continue
        key = npc, hash_value
        if key in by_npc_hash and by_npc_hash[key] != clean:
            collisions.add(key)
            continue
        by_npc_hash[key] = clean
        identity = text_hash(clean)
        group = groups.setdefault(identity, {
            "group_id": identity, "english_sha256": identity, "english": display, "contexts": {}
        })
        name = row.get("npcName")
        group["contexts"][key] = {"npc_id": npc,
                                  "npc_name": name if type(name) is str else "",
                                  "english_hash": hash_value}
    for key in collisions:
        original = by_npc_hash[key]
        identity = text_hash(original)
        groups[identity]["contexts"].pop(key, None)
        if not groups[identity]["contexts"]:
            del groups[identity]
    result = []
    for group in groups.values():
        contexts = sorted(group["contexts"].values(),
                          key=lambda x: (x["npc_id"], x["english_hash"]))
        group["contexts"] = contexts
        group["context_sha256"] = digest({
            "spoken": spoken_rev, "classicua": classicua_rev,
            "english_sha256": group["english_sha256"],
            "pairs": [(c["npc_id"], c["english_hash"]) for c in contexts],
        })
        group["occurrence_count"] = len(contexts)
        result.append(group)
    result.sort(key=lambda x: (-x["occurrence_count"], x["group_id"]))
    occurrences = sum(x["occurrence_count"] for x in result)
    return result, {
        "spoken_gossip_rows": gossip_rows, "non_npc_rows": non_npc,
        "untranslated_npc_wordings_queued": occurrences,
        "unique_english_texts_to_translate": len(result),
        "repeated_occurrences_deduplicated": occurrences - len(result),
        "groups_used_by_multiple_npcs": sum(x["occurrence_count"] > 1 for x in result),
        "excluded_npc_hash_collisions": len(collisions),
    }


def version_id(row):
    return digest({k: row[k] for k in ("group_id", "english_sha256", "context_sha256",
                   "spoken_revision", "classicua_revision", "provider", "text_sha256")})


def version_status(row):
    return row["decisions"][-1]["decision"] if row["decisions"] else "pending"


def validate_ledger(data):
    if (type(data) is not dict or set(data) != set(EMPTY)
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or type(data["versions"]) is not list or type(data["imports"]) is not list):
        raise ValueError("invalid_gossip_review_ledger")
    seen = {}
    fields = {"id", "group_id", "english_sha256", "context_sha256",
              "spoken_revision", "classicua_revision", "provider", "text",
              "text_sha256", "decisions"}
    for row in data["versions"]:
        if (type(row) is not dict or set(row) != fields
                or any(type(row[k]) is not str or not HEX64.fullmatch(row[k])
                       for k in ("id", "group_id", "english_sha256",
                                 "context_sha256", "text_sha256"))
                or row["group_id"] != row["english_sha256"]
                or any(type(row[k]) is not str or not HEX40.fullmatch(row[k])
                       for k in ("spoken_revision", "classicua_revision"))
                or row["provider"] not in PROVIDERS
                or type(row["text"]) is not str or not row["text"].strip()
                or len(row["text"]) > 60000
                or text_hash(row["text"]) != row["text_sha256"]
                or row["id"] != version_id(row) or row["id"] in seen
                or type(row["decisions"]) is not list):
            raise ValueError("invalid_gossip_review_version")
        seen[row["id"]] = row
        for decision in row["decisions"]:
            if (type(decision) is not dict or set(decision) != {"decision", "reviewer", "checks"}
                    or decision["decision"] not in DECISIONS
                    or type(decision["reviewer"]) is not str or not decision["reviewer"].strip()
                    or len(decision["reviewer"]) > 120
                    or type(decision["checks"]) is not dict
                    or set(decision["checks"]) != set(CHECKS)
                    or any(type(v) is not bool for v in decision["checks"].values())
                    or (decision["decision"] == "approved"
                        and not all(decision["checks"].values()))):
                raise ValueError("invalid_gossip_review_attestation")
    imported = set()
    for row in data["imports"]:
        if (type(row) is not dict or set(row) != {"group_id", "version_id"}
                or type(row["group_id"]) is not str
                or row["group_id"] in imported
                or row["version_id"] not in seen
                or seen[row["version_id"]]["group_id"] != row["group_id"]
                or version_status(seen[row["version_id"]]) != "approved"):
            raise ValueError("invalid_gossip_review_import")
        imported.add(row["group_id"])
    return deepcopy(data)


class GossipReviews:
    def __init__(self, groups, spoken_rev, classicua_rev, path=LEDGER, allowed=ROOT / "build"):
        self.groups = {g["group_id"]: g for g in groups}
        self.spoken_rev, self.classicua_rev = spoken_rev, classicua_rev
        self.file = LocalFile(path, allowed, EMPTY, validate_ledger)

    def current(self, version):
        group = self.groups.get(version["group_id"])
        return (group is not None
                and version["english_sha256"] == group["english_sha256"]
                and version["context_sha256"] == group["context_sha256"]
                and version["spoken_revision"] == self.spoken_rev
                and version["classicua_revision"] == self.classicua_rev)

    def propose(self, proposals, provider):
        if provider not in PROVIDERS or type(proposals) is not list or not 0 < len(proposals) <= 100:
            raise ValueError("invalid_gossip_proposal_batch")
        copy = deepcopy(self.file.data)
        ids = {r["id"] for r in copy["versions"]}
        group_ids = set()
        for proposal in proposals:
            if (type(proposal) is not dict
                    or set(proposal) != {"group_id", "english_sha256",
                                        "context_sha256", "ukrainian_text"}):
                raise ValueError("invalid_gossip_proposal_fields")
            group = self.groups.get(proposal["group_id"])
            if (group is None or group["group_id"] in group_ids
                    or proposal["english_sha256"] != group["english_sha256"]
                    or proposal["context_sha256"] != group["context_sha256"]):
                raise ValueError("stale_or_duplicate_gossip_proposal")
            group_ids.add(group["group_id"])
            value = proposal["ukrainian_text"]
            if type(value) is not str or not value.strip() or len(value) > 60000:
                raise ValueError("invalid_gossip_ukrainian_text")
            row = {"group_id": group["group_id"],
                   "english_sha256": group["english_sha256"],
                   "context_sha256": group["context_sha256"],
                   "spoken_revision": self.spoken_rev,
                   "classicua_revision": self.classicua_rev,
                   "provider": provider, "text": value,
                   "text_sha256": text_hash(value), "decisions": []}
            row["id"] = version_id(row)
            if row["id"] in ids:
                raise ValueError("duplicate_gossip_version")
            ids.add(row["id"])
            copy["versions"].append(row)
        self.file.save(copy)
        return len(proposals)

    def decide(self, version_id_value, decision, reviewer, checks):
        if (decision not in DECISIONS or type(reviewer) is not str or not reviewer.strip()
                or len(reviewer) > 120 or type(checks) is not dict
                or set(checks) != set(CHECKS) or any(type(x) is not bool for x in checks.values())
                or (decision == "approved" and not all(checks.values()))):
            raise ValueError("explicit_gossip_attestation_required")
        copy = deepcopy(self.file.data)
        row = next((r for r in copy["versions"] if r["id"] == version_id_value), None)
        if row is None or not self.current(row):
            raise ValueError("stale_or_unknown_gossip_version")
        if row["decisions"] and row["decisions"][-1]["decision"] == decision:
            raise ValueError("duplicate_gossip_decision")
        row["decisions"].append({"decision": decision, "reviewer": reviewer,
                                 "checks": checks})
        if decision != "approved":
            copy["imports"] = [r for r in copy["imports"] if r["version_id"] != row["id"]]
        self.file.save(copy)
        return version_status(row)

    def import_approved(self):
        by_group = defaultdict(list)
        for row in self.file.data["versions"]:
            if self.current(row) and version_status(row) == "approved":
                by_group[row["group_id"]].append(row)
        output = []
        for group, versions in sorted(by_group.items()):
            if len(versions) != 1:
                raise ValueError("conflicting_gossip_approved_versions")
            output.append({"group_id": group, "version_id": versions[0]["id"]})
        copy = deepcopy(self.file.data)
        copy["imports"] = output
        self.file.save(copy)
        return len(output)

    def imported_by_npc(self, original):
        versions = {v["id"]: v for v in self.file.data["versions"]}
        result = defaultdict(dict)
        for entry in self.file.data["imports"]:
            row = versions[entry["version_id"]]
            if not self.current(row) or version_status(row) != "approved":
                raise ValueError("stale_gossip_import")
            for ctx in self.groups[row["group_id"]]["contexts"]:
                npc, h = ctx["npc_id"], ctx["english_hash"]
                if h in original["common"] or h in original["byNpc"].get(npc, {}):
                    raise ValueError("reviewed_gossip_classicua_conflict")
                if h in result[npc] and result[npc][h] != row["text"]:
                    raise ValueError("reviewed_gossip_wording_conflict")
                result[npc][h] = row["text"]
        return dict(result)

    def page(self, offset=0, limit=12):
        if type(offset) is not int or offset < 0 or offset > 100000 or limit not in (12, 20, 40):
            raise ValueError("invalid_gossip_review_page")
        groups = sorted(self.groups.values(),
                        key=lambda g: (-g["occurrence_count"], g["group_id"]))
        versions = defaultdict(list)
        imports = {x["version_id"] for x in self.file.data["imports"]}
        for row in self.file.data["versions"]:
            versions[row["group_id"]].append({**deepcopy(row),
                "status": version_status(row) if self.current(row) else "stale",
                "imported": row["id"] in imports and self.current(row)})
        items = [{**deepcopy(g), "versions": versions[g["group_id"]]}
                 for g in groups[offset:offset + limit]]
        return {"total": len(groups), "offset": offset, "limit": limit,
                "items": items, "imports": len(imports),
                "versions": len(self.file.data["versions"])}


def create_batches(groups, spoken_rev, classicua_rev, directory, batch_size):
    """Private inputs for external translator; blank Ukrainian output by design."""
    if type(batch_size) is not int or not 1 <= batch_size <= 100:
        raise ValueError("invalid_gossip_batch_size")
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError("unsafe_gossip_batch_dir")
    directory.mkdir(parents=True, exist_ok=True)
    # Never delete/recreate earlier batches: they may contain unsent edits.
    # Existing files are reused only when their pinned source content and
    # contexts still match exactly; edited Ukrainian text is preserved.
    for offset in range(0, len(groups), batch_size):
        # Prefill drafts from previously approved, unambiguous translations
        # stored in SQLite. The reused value is NOT approved for new contexts:
        # it still requires explicit propose + human review + import.
        from adapters.sqlite_translation_store import DB_ENV, memory_suggestions
        db_path = os.environ.get(DB_ENV)
        suggestions = memory_suggestions(db_path, "gossip",
                            [g["english_sha256"] for g in groups[offset:offset + batch_size]]) \
                      if db_path else {}
        rows = [{"group_id": g["group_id"], "english_sha256": g["english_sha256"],
                 "context_sha256": g["context_sha256"], "english_original": g["english"],
                 "occurrence_count": g["occurrence_count"],
                 "ukrainian_text": suggestions.get(g["english_sha256"], "")}
                for g in groups[offset:offset + batch_size]]
        bundle = {"schema_version": 1, "spoken_revision": spoken_rev,
                  "classicua_revision": classicua_rev, "entries": rows}
        path = directory / f"batch-{offset // batch_size + 1:04d}.json"
        if path.is_symlink():
            raise ValueError("unsafe_gossip_batch_path")
        if path.exists():
            previous = strict_json(path.read_text(encoding="utf-8"))
            if (type(previous) is not dict or set(previous) != set(bundle)
                    or any(previous.get(key) != bundle[key] for key in
                           ("schema_version", "spoken_revision", "classicua_revision"))
                    or type(previous.get("entries")) is not list
                    or len(previous["entries"]) != len(rows)):
                raise ValueError("stale_gossip_batch_move_aside_before_regeneration")
            for old_row, current in zip(previous["entries"], rows):
                if (type(old_row) is not dict or set(old_row) != set(current)
                        or any(old_row.get(key) != current[key] for key in current
                               if key != "ukrainian_text")):
                    raise ValueError("stale_gossip_batch_move_aside_before_regeneration")
            continue
        path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return (len(groups) + batch_size - 1) // batch_size


def load_proposals(path, spoken_rev, classicua_rev):
    """Only read exact pinned JSON under ignored build/, never arbitrary paths."""
    path = Path(path)
    if path.is_symlink() or not path.resolve().is_relative_to((ROOT / "build").resolve()):
        raise ValueError("proposals_must_reside_under_build")
    data = strict_json(path.read_text(encoding="utf-8"))
    if (type(data) is not dict or set(data) !=
            {"schema_version", "spoken_revision", "classicua_revision", "entries"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or data["spoken_revision"] != spoken_rev
            or data["classicua_revision"] != classicua_rev
            or type(data["entries"]) is not list):
        raise ValueError("stale_or_invalid_gossip_batch")
    proposals = []
    for row in data["entries"]:
        if type(row) is not dict or set(row) not in (
                {"group_id", "english_sha256", "context_sha256", "ukrainian_text"},
                {"group_id", "english_sha256", "context_sha256", "english_original",
                 "occurrence_count", "ukrainian_text"}):
            raise ValueError("invalid_gossip_proposal_fields")
        proposals.append({k: row[k] for k in
                          ("group_id", "english_sha256", "context_sha256", "ukrainian_text")})
    return proposals


def load_reviewed_gossip(state, existing, spoken_path):
    """Called during local ZIP build; fail closed on stale/private edited reviews."""
    lines = read_pinned_corpus(spoken_path, state.inventory.revision)
    groups, _ = discover_groups(lines, existing, state.inventory.revision, state.source.revision)
    return GossipReviews(groups, state.inventory.revision, state.source.revision).imported_by_npc(existing)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("queue", "propose", "review", "import-approved", "status"))
    parser.add_argument("--classicua", type=Path, required=True)
    parser.add_argument("--spoken", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--provider", choices=PROVIDERS, default="own_translator")
    parser.add_argument("--batch-size", type=int, default=40)
    parser.add_argument("--version")
    parser.add_argument("--decision", choices=DECISIONS)
    parser.add_argument("--reviewer")
    for key in CHECKS:
        parser.add_argument("--checked-" + key.replace("_", "-"), action="store_true")
    args = parser.parse_args(argv)
    try:
        from tools.review_ui_server import build_state
        from tools.build_ukrainian import local_gossip_texts
        lock = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))
        state = build_state(args.classicua, args.spoken,
                            ROOT / "build/stage4b-decisions.json", None,
                            ROOT / "build/stage3-ui-reviews.json",
                            ROOT / "build/translation-reviews.json",
                            ROOT / "config/translation_sources.json")
        if (state.inventory.revision != lock["spoken"]["revision"]
                or state.source.revision != lock["classicua"]["revision"]):
            raise ValueError("gossip_source_revisions_differ")
        original = local_gossip_texts(state)
        lines = read_pinned_corpus(args.spoken, state.inventory.revision)
        groups, summary = discover_groups(lines, original, state.inventory.revision,
                                         state.source.revision)
        reviews = GossipReviews(groups, state.inventory.revision, state.source.revision)
        if args.action == "queue":
            output = ROOT / "build/gossip-translation-queue.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(
                {"spoken_revision": state.inventory.revision,
                 "classicua_revision": state.source.revision,
                 "summary": summary, "groups": groups},
                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            batches = create_batches(groups, state.inventory.revision, state.source.revision,
                                     ROOT / "build/gossip-batches", args.batch_size)
            print(json.dumps(summary, sort_keys=True))
            print("Private queue:", output, "private translator batches:", batches)
        elif args.action == "propose":
            if not args.input:
                raise ValueError("missing_gossip_proposal_input")
            proposals = load_proposals(args.input, state.inventory.revision, state.source.revision)
            print("Pending versions added:", reviews.propose(proposals, args.provider))
        elif args.action == "review":
            if not (args.version and args.decision and args.reviewer):
                raise ValueError("missing_gossip_review_identity")
            checks = {k: getattr(args, "checked_" + k) for k in CHECKS}
            print("Decision:", reviews.decide(args.version, args.decision, args.reviewer, checks))
        elif args.action == "import-approved":
            print("Explicitly imported approved groups:", reviews.import_approved())
        else:
            print(json.dumps(reviews.page(0, 12), ensure_ascii=False)[:2000])
        return 0
    except (ValueError, TypeError, OSError, KeyError, RuntimeError) as error:
        message = str(error)
        print("gossip_review_failed:", message if re.fullmatch("[a-z0-9_]{2,80}", message)
              else type(error).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    # Executed CLIs use the persistent SQLite store by default. Test/library
    # direct calls retain their explicit isolated JSON fixture backend.
    import os
    from adapters.sqlite_translation_store import enable_sqlite, DB_ENV
    with enable_sqlite(os.environ.get(DB_ENV)):
        raise SystemExit(main())
