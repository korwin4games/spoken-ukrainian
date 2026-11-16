"""In-memory records retain original words; report serialization is metadata-only."""
from dataclasses import dataclass, field
import json
from .grammar import inventory
from .lua import Node, Table

QUEST_FIELDS = {1: "title", 2: "description", 3: "objective", 4: "progress", 5: "completion"}
ROW_FIELDS = {"npc": {1, 2, "en", "feminine", "feminine_tag"},
              **{category: {1, 2, 3, 4, 5, "en", "ai", "tasks"}
                 for category in ("quest_alliance", "quest_horde", "quest_both")}}


@dataclass(frozen=True)
class Origin:
    repository: str
    revision: str
    file: str
    line: int
    column: int
    layer: str
    sha256: str
    source_key: object


@dataclass(frozen=True)
class Field:
    path: tuple
    node: Node
    origin: Origin
    predecessors: tuple[Origin, ...] = ()
    grammar: tuple = ()


@dataclass
class Record:
    category: str
    key: object
    node: Node
    origin: Origin
    predecessors: tuple[Origin, ...] = ()
    fields: dict = field(default_factory=dict)

    @property
    def identity(self):
        return "classicua:" + self.category + ":" + json.dumps(self.key, ensure_ascii=False)

    @property
    def ai(self):
        if not isinstance(self.node.value, Table):
            return False
        flag = self.node.value.get("ai")
        return flag is not None and flag.value is not None and flag.value is not False

    @property
    def unsupported_fields(self):
        if self.category not in ROW_FIELDS or not isinstance(self.node.value, Table):
            return ()
        return tuple(k for k in self.node.value.effective() if k not in ROW_FIELDS[self.category])

    @property
    def missing_fields(self):
        if not self.category.startswith("quest_"):
            return ()
        return tuple(name for key, name in QUEST_FIELDS.items()
                     if (key,) not in self.fields or self.fields[(key,)].node.value in (None, ""))


def leaves(node, path=()):
    if isinstance(node.value, Table):
        declared = {}
        for entry in node.value.entries:
            declared[entry.key.value] = entry
        for key, entry in declared.items():
            yield from leaves(entry.value, path + (key,))
    else:
        yield path, node


def equal_values(left, right):
    if isinstance(left.value, Table) and isinstance(right.value, Table):
        a, b = left.value.effective(), right.value.effective()
        return a.keys() == b.keys() and all(equal_values(a[k].value, b[k].value) for k in a)
    return type(left.value) is type(right.value) and left.value == right.value


def make_record(category, key, node, origin_for, old=None):
    origin = origin_for(node, key)
    record = Record(category, key, node, origin,
                    old.predecessors + (old.origin,) if old else ())
    for path, leaf in leaves(node):
        previous = old.fields.get(path) if old else None
        leaf_origin = origin_for(leaf, key)
        if previous and previous.node is leaf:
            record.fields[path] = previous
        else:
            predecessors = previous.predecessors + (previous.origin,) if previous else ()
            findings = tuple(inventory(leaf.value)) if isinstance(leaf.value, str) else ()
            record.fields[path] = Field(path, leaf, leaf_origin, predecessors, findings)
    return record


class Dataset:
    def __init__(self, origin_for):
        self.origin_for = origin_for
        self.records = {}
        self.raw = []
        self.replacements = []
        self.warnings = []

    def apply(self, category, layer, table, mode):
        records = self.records.setdefault(category, {})
        if mode == "initialize" and records:
            raise ValueError("Unexpected reinitialization of populated category " + category)
        raw_rows = [make_record(category, entry.key.value, entry.value, self.origin_for)
                    for entry in table.value.entries if entry.value.value is not None]
        raw_missing = {}
        for row in raw_rows:
            for name in row.missing_fields:
                raw_missing[name] = raw_missing.get(name, 0) + 1
        self.raw.append({"category": category, "layer": layer,
                         "declarations": len(table.value.entries),
                         "unique_non_nil_keys": len(table.value.effective()),
                         "ai_marked_declarations": sum(bool(row.ai) for row in raw_rows),
                         "missing_positional_fields": raw_missing,
                         "gossip_hash_declarations": sum(
                             type(e.key.value) is int
                             for row in raw_rows if category == "gossip" and isinstance(row.node.value, Table)
                             for e in row.node.value.entries)})
        # Lua pairs sees the completed table, not overwritten declarations inside it.
        seen = set()
        for entry in table.value.entries:
            if entry.key.value in seen:
                self.warnings.append({"file": entry.key.file, "line": entry.key.line, "code": "duplicate_table_key", "category": category})
            seen.add(entry.key.value)
        for key, entry in table.value.effective().items():
            old = records.get(key)
            node = entry.value
            if old:
                self.replacements.append({"category": category, "layer": layer,
                                          "file": node.file, "line": node.line})
            if mode == "gossip" and old and isinstance(old.node.value, Table) and isinstance(node.value, Table):
                incoming = list(node.value.effective().values())
                node = Node(Table(old.node.value.entries + incoming), node.file, node.line, node.column)
            records[key] = make_record(category, key, node, self.origin_for, old)

    def faction_views(self, include_ai=True):
        shared = self.records.get("quest_both", {})
        views, conflicts = {}, []
        for faction in ("alliance", "horde"):
            own = self.records.get("quest_" + faction, {})
            # ClassicUA removes AI rows before faction/shared lookup, allowing shared fallback.
            selected_shared = {k: v for k, v in shared.items() if include_ai or not v.ai}
            selected_own = {k: v for k, v in own.items() if include_ai or not v.ai}
            views[faction] = selected_shared | selected_own
            for key in sorted(own.keys() & shared.keys(), key=lambda k: (type(k).__name__, str(k))):
                conflicts.append({"faction": faction, "quest_id": key,
                                  "different": not equal_values(own[key].node, shared[key].node),
                                  "winner": own[key].identity,
                                  "faction_file": own[key].origin.file,
                                  "shared_file": shared[key].origin.file})
        return views, conflicts
