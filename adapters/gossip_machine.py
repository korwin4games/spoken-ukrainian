"""Private ClassicUA Gossip imports. Identity evidence is provisional, never human approval."""
from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
import re

from adapters.crosswalk import digest
from adapters.local_review_store import LocalFile

EMPTY = {"schema_version": 1, "versions": [], "imports": []}
NAME = "gossip-machine-one-to-one.json"
HEX = re.compile(r"[0-9a-f]{64}\Z")
REV = re.compile(r"[0-9a-f]{40}\Z")
TARGET = re.compile(r"gossip:(common|[1-9][0-9]*):([1-9][0-9]*)\Z")
FIELDS = {"id", "target_id", "english_sha256", "context_sha256", "bindings",
          "spoken_revision", "source_revision", "source_file", "source_layer",
          "source_file_sha256", "source_context_sha256", "text", "text_sha256",
          "source_provenance", "source_overrides",
          "ai", "approval_status", "decision"}


def text_sha(text):
    return sha256(text.encode("utf-8")).hexdigest()


def record_id(row):
    return digest({k: v for k, v in row.items() if k != "id"})


def validate_ledger(data):
    if (type(data) is not dict or set(data) != set(EMPTY)
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or type(data["versions"]) is not list or type(data["imports"]) is not list):
        raise ValueError("invalid_gossip_machine_ledger")
    seen, targets = {}, set()
    for row in data["versions"]:
        if (type(row) is not dict or set(row) != FIELDS
                or type(row["target_id"]) is not str or not TARGET.fullmatch(row["target_id"])
                or row["decision"] not in ("machine_1to1_provisional", "pending_update")
                or row["approval_status"] != "unreviewed" or type(row["ai"]) is not bool
                or any(type(row[k]) is not str or not HEX.fullmatch(row[k]) for k in
                       ("id", "english_sha256", "context_sha256", "source_file_sha256",
                        "source_context_sha256", "text_sha256"))
                or any(type(row[k]) is not str or not REV.fullmatch(row[k]) for k in
                       ("spoken_revision", "source_revision"))
                or any(type(row[k]) is not str or not row[k] for k in
                       ("source_file", "source_layer", "text"))
                or not row["text"].strip() or len(row["text"]) > 60000
                or row["text_sha256"] != text_sha(row["text"])
                or type(row["source_provenance"]) is not dict
                or set(row["source_provenance"]) != {"repository", "revision", "file", "line", "column", "layer", "sha256", "source_key"}
                or type(row["source_overrides"]) is not list
                or row["source_context_sha256"] != digest([row["source_provenance"], row["source_overrides"]])
                or type(row["bindings"]) is not list or not row["bindings"]
                or any(type(b) is not int or b <= 0 for b in row["bindings"])
                or row["bindings"] != sorted(set(row["bindings"]))
                or row["id"] != record_id(row) or row["id"] in seen):
            raise ValueError("invalid_gossip_machine_provenance")
        scope, hashed = TARGET.fullmatch(row["target_id"]).groups()
        origin = row["source_provenance"]
        if ((origin["revision"], origin["file"], origin["layer"], origin["sha256"]) !=
                (row["source_revision"], row["source_file"], row["source_layer"], row["source_file_sha256"])
                or type(origin["line"]) is not int or origin["line"] <= 0
                or type(origin["column"]) is not int or origin["column"] <= 0):
            raise ValueError("invalid_gossip_machine_source_origin")
        if int(hashed) >= 4294967291 or (scope != "common" and row["bindings"] != [int(scope)]):
            raise ValueError("invalid_gossip_machine_binding")
        seen[row["id"]] = row
    for ref in data["imports"]:
        if (type(ref) is not dict or set(ref) != {"target_id", "version_id"}
                or type(ref["version_id"]) is not str or ref["version_id"] not in seen
                or ref["target_id"] != seen[ref["version_id"]]["target_id"]
                or seen[ref["version_id"]]["decision"] != "machine_1to1_provisional"
                or ref["target_id"] in targets):
            raise ValueError("invalid_gossip_machine_import")
        targets.add(ref["target_id"])
    return deepcopy(data)


def candidates(state, lines, lookup):
    """Deduplicate NPC/hash placements; reject global hash collisions before matching.

    ClassicUA stores hashes, not English bytes. Exact normalized English is
    proven by the pinned Spoken corpus; the ClassicUA identity remains a
    provisional hash match. NPC names never participate in this evidence.
    """
    from tools.gossip_coverage import classicua_hash
    from tools.gossip_translation_review import normalized
    words, pairs, types = defaultdict(set), defaultdict(set), defaultdict(set)
    unknown = 0
    for line in lines:
        if type(line) is not dict:
            raise ValueError("invalid_gossip_machine_corpus_row")
        if line.get("source") != "gossip":
            continue
        npc = line.get("npcId")
        english = line.get("originalText")
        if type(english) is not str or not english.strip():
            english = line.get("text")
        clean = normalized(english).translate(str.maketrans("ЇЄІҐ", "їєіґ"))
        hashed = classicua_hash(english)
        if not clean or hashed is None:
            unknown += 1
            continue
        words[hashed].add(clean)
        if (line.get("npcType") not in ("creature", "vehicle")
                or type(npc) is not int or npc <= 0):
            unknown += 1
            continue
        pairs[npc, hashed].add(clean)
        types[npc, hashed].add(line["npcType"])
    collisions = {h for h, variants in words.items() if len(variants) != 1}
    ambiguous_common = {h for (_, h), values in types.items() if len(values) != 1}
    grouped, items = defaultdict(list), []
    for (npc, hashed), variants in sorted(pairs.items()):
        status = "conflict" if hashed in collisions or len(types[npc, hashed]) != 1 else "untranslated"
        scope = npc if hashed in lookup["byNpc"].get(npc, {}) else "common"
        if scope == "common" and hashed in ambiguous_common:
            status = "conflict"
        if status != "conflict" and (hashed in lookup["byNpc"].get(npc, {})
                                      or hashed in lookup["common"]):
            status = "eligible"
            grouped[scope, hashed].append(npc)
        for clean in sorted(variants):
            items.append({"npc_id": npc, "english_hash": hashed,
                          "english_sha256": text_sha(clean), "status": status,
                          "target_id": f"gossip:{scope}:{hashed}"})
    output = []
    for (scope, hashed), npcs in sorted(grouped.items(), key=lambda x: str(x[0])):
        record = state.dataset.records["gossip"]["!common" if scope == "common" else scope]
        leaf = record.fields[(hashed,)]
        origin = leaf.origin
        if (origin.revision != state.source.revision
                or state.source.files.get(origin.file) != origin.sha256):
            raise ValueError("unverified_classicua_gossip_machine_source")
        english_sha = text_sha(next(iter(words[hashed])))
        row = {"target_id": f"gossip:{scope}:{hashed}", "english_sha256": english_sha,
               "bindings": sorted(set(npcs)),
               "context_sha256": digest([english_sha, sorted(set(npcs)), hashed]),
               "spoken_revision": state.inventory.revision,
               "source_revision": origin.revision, "source_file": origin.file,
               "source_layer": origin.layer, "source_file_sha256": origin.sha256,
               "source_provenance": dict(origin.__dict__),
               "source_overrides": [dict(p.__dict__) for p in leaf.predecessors],
               "source_context_sha256": digest([origin.__dict__, [p.__dict__ for p in leaf.predecessors]]),
               "text": leaf.node.value, "text_sha256": text_sha(leaf.node.value),
               "ai": record.ai, "approval_status": "unreviewed",
               "decision": "machine_1to1_provisional"}
        row["id"] = record_id(row)
        output.append(row)
    return output, items, unknown


class GossipMachineStore:
    def __init__(self, path, allowed):
        self.file = LocalFile(path, allowed, EMPTY, validate_ledger)

    def run(self, rows, blocked=()):
        validate_ledger({**deepcopy(EMPTY), "versions": rows})
        if len({r["target_id"] for r in rows}) != len(rows):
            raise ValueError("ambiguous_gossip_machine_candidates")
        data = deepcopy(self.file.data)
        known = {r["id"]: r for r in data["versions"]}
        history = defaultdict(list)
        old_bindings = set()
        for row in data["versions"]:
            history[row["target_id"]].append(row)
            hashed = row["target_id"].rsplit(":", 1)[1]
            old_bindings.update((npc, hashed) for npc in row["bindings"])
        imports = []
        blocked = set(blocked)
        current = {r["target_id"]: r for r in rows if r["target_id"] not in blocked}
        # Record invalidation even when a source disappears or a human blocks it.
        for target, previous in history.items():
            row = current.get(target)
            if row is None or row["id"] not in known:
                stale = deepcopy(row or previous[-1])
                stale["decision"] = "pending_update"
                stale["id"] = record_id(stale)
                if stale["id"] not in known:
                    known[stale["id"]] = stale
                    data["versions"].append(stale)
        pending = {r["target_id"] for r in data["versions"] if r["decision"] == "pending_update"}
        for target, row in sorted(current.items()):
            if not history[target]:
                version = deepcopy(row)
                if any((npc, target.rsplit(":", 1)[1]) in old_bindings for npc in row["bindings"]):
                    version["decision"] = "pending_update"
                    version["id"] = record_id(version)
                    pending.add(target)
                known[version["id"]] = version
                data["versions"].append(version)
            if row["id"] in known and target not in pending:
                imports.append({"target_id": target, "version_id": row["id"]})
        data["versions"].sort(key=lambda r: (r["target_id"], r["id"]))
        data["imports"] = imports
        self.file.save(data)
        return len(imports)

    def lookup(self, rows, blocked=()):
        current = {r["id"]: r for r in rows if r["target_id"] not in set(blocked)}
        result = {"byNpc": {}, "common": {}}
        for ref in self.file.data["imports"]:
            row = current.get(ref["version_id"])
            if row is None:
                continue  # Stale imports are never emitted, even before refresh.
            scope, hashed = TARGET.fullmatch(row["target_id"]).groups()
            dest = result["common"] if scope == "common" else result["byNpc"].setdefault(int(scope), {})
            dest[int(hashed)] = row["text"]
        return result
