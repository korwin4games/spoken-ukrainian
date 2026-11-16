"""Read pinned Git objects and reconstruct the Camelot manifest without running Lua."""
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
from xml.parsers import expat

from .lua import SourceError, Table, parse_file
from .model import Dataset, Origin, ROW_FIELDS

PINNED_REVISION = "1770d208ad853d23d61105cf510d53804770d916"
REPOSITORY = "https://github.com/greenya/ClassicUA"
FAMILIES = frozenset({"quest_alliance", "quest_horde", "quest_both", "gossip",
                      "item_text", "object_text", "npc", "object", "zone"})
LAYERS = ("classic", "sod", "forever")
SCHEMA = ROW_FIELDS


class GitSource:
    def __init__(self, path, revision=None):
        revision = PINNED_REVISION if revision is None else revision
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise SourceError("<checkout>", 1, "Explicit full source revision required")
        self.revision = revision
        self.path = Path(path).resolve()
        self.hashes = {}
        revision = self.git("rev-parse", "HEAD").decode().strip()
        if revision != self.revision:
            raise SourceError("<checkout>", 1, "Git HEAD does not match the pinned ClassicUA revision")
        if Path(self.git("rev-parse", "--show-toplevel").decode().strip()).resolve() != self.path:
            raise SourceError("<checkout>", 1, "--source must name the Git checkout root")
        if self.git("status", "--porcelain", "--untracked-files=no").strip():
            raise SourceError("<checkout>", 1, "Tracked ClassicUA files are modified; use a clean pinned checkout")

    def git(self, *args):
        result = subprocess.run(["git", "--no-optional-locks", "-C", str(self.path), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            raise SourceError("<checkout>", 1, "Git source validation/read failed")
        return result.stdout

    def read(self, path):
        path = safe_relative(path)
        data = self.git("show", self.revision + ":" + path)
        self.hashes[path] = hashlib.sha256(data).hexdigest()
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise SourceError(path, 1, "Source is not valid UTF-8") from None


def safe_relative(path):
    path = path.replace("\\", "/")
    if ":" in path or path.startswith("/"):
        raise SourceError("<manifest>", 1, "Absolute paths and URI references are unsupported")
    path = posixpath.normpath(path)
    if path in ("", ".", "..") or path.startswith("../"):
        raise SourceError("<manifest>", 1, "Manifest path escapes the source root")
    return path


def loading_order(reader):
    result, visiting = [], set()

    def visit(path):
        path = safe_relative(path)
        if path in visiting:
            raise SourceError(path, 1, "Cyclic XML inclusion")
        if path.endswith(".lua"):
            result.append(path)
            return
        text = reader.read(path)
        if path.endswith(".toc"):
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    visit(line)
            return
        if not path.endswith(".xml"):
            raise SourceError(path, 1, "Unsupported manifest extension")
        visiting.add(path)
        parser = expat.ParserCreate()
        children = []

        def start(tag, attrs):
            if tag in ("Script", "Include"):
                if "file" not in attrs:
                    raise SourceError(path, parser.CurrentLineNumber, "Manifest entry has no file")
                children.append(safe_relative(posixpath.join(posixpath.dirname(path), attrs["file"].replace("\\", "/"))))

        def no_entities(*args):
            raise SourceError(path, parser.CurrentLineNumber, "XML entities and doctypes are unsupported")

        parser.StartElementHandler = start
        parser.StartDoctypeDeclHandler = no_entities
        parser.EntityDeclHandler = no_entities
        parser.ExternalEntityRefHandler = no_entities
        try:
            parser.Parse(text, True)
        except expat.ExpatError as error:
            raise SourceError(path, error.lineno, "Malformed XML manifest") from None
        for child in children:
            visit(child)
        visiting.remove(path)

    visit("ClassicUA_Camelot.toc")
    return result


def source_category(path):
    parts = PurePosixPath(path).parts
    family = PurePosixPath(path).stem
    if parts[0] != "entries" or family not in FAMILIES:
        return None
    if len(parts) == 2 and family == "zone":
        return family, "common"
    if len(parts) == 3 and parts[1] in LAYERS and family != "zone":
        return family, parts[1]
    return None


def load_dataset(reader, revision=PINNED_REVISION):
    order = loading_order(reader)
    selected = [(path, source_category(path)) for path in order if source_category(path)]
    observed_layers = list(dict.fromkeys(layer for _, (_, layer) in selected if layer != "common"))
    if observed_layers != list(LAYERS):
        raise SourceError("ClassicUA_Camelot.toc", 1, "Expected classic, sod, forever layer order")
    expected_paths = {f"entries/{layer}/{family}.lua" for layer in LAYERS for family in FAMILIES - {"zone"}}
    expected_paths.add("entries/zone.lua")
    if {path for path, _ in selected} != expected_paths:
        raise SourceError("ClassicUA_Camelot.toc", 1, "Required source families are missing or unexpected")
    files = {}

    def origin_for(node, key):
        info = files[node.file]
        return Origin(REPOSITORY, revision, node.file, node.line, node.column,
                      info["layer"], reader.hashes[node.file], key)

    dataset = Dataset(origin_for)
    for path, (category, layer) in selected:
        files[path] = {"category": category, "layer": layer}
        node, mode = parse_file(reader.read(path), category, path)
        for entry in node.value.entries:
            key, value = entry.key.value, entry.value.value
            if category in {"zone", "object", "object_text"}:
                valid_key = isinstance(key, str)
            elif category == "gossip":
                valid_key = type(key) is int and key > 0 or key == "!common"
            else:
                valid_key = type(key) is int and key > 0
            if not valid_key:
                raise SourceError(path, entry.key.line, "Invalid source record key type")
            if value is not None and not isinstance(value, str if category in {"zone", "object"} else Table):
                raise SourceError(path, entry.value.line, "Invalid source record value type")
        if mode == "initialize" and layer not in ("classic", "common"):
            raise SourceError(path, node.line, "Unexpected category initialization in an overlay")
        dataset.apply(category, layer, node, mode)
    return dataset, order


def counts(counter):
    return dict(sorted(counter.items()))


def metadata_report(dataset, hashes, order, revision=PINNED_REVISION):
    summaries = {}
    provenance, review_findings = [], []
    grammar_categories, grammar_status, grammar_forms, grammar_details = Counter(), Counter(), Counter(), Counter()
    warnings = list(dataset.warnings)
    for category, records in sorted(dataset.records.items()):
        missing, invalid, types, inherited = Counter(), Counter(), Counter(), Counter()
        ai, nils, text_fields, code_entries, hashes_count, variants = 0, 0, 0, 0, 0, 0
        for record in records.values():
            def key_ref(key):
                return key if type(key) in (int, float) else {"sha256": hashlib.sha256(str(key).encode("utf-8")).hexdigest()}

            def origin_meta(origin):
                return {"file": origin.file, "line": origin.line, "column": origin.column,
                        "layer": origin.layer, "sha256": origin.sha256}

            record_ref = hashlib.sha256(record.identity.encode("utf-8")).hexdigest()
            field_metadata = []
            for leaf in record.fields.values():
                item = {"identity": [key_ref(k) for k in leaf.path], "origin": origin_meta(leaf.origin),
                        "predecessors": [origin_meta(o) for o in leaf.predecessors],
                        "value_type": type(leaf.node.value).__name__}
                if isinstance(leaf.node.value, str):
                    item["text_sha256"] = hashlib.sha256(leaf.node.value.encode("utf-8")).hexdigest()
                field_metadata.append(item)
            provenance.append({"record_ref": record_ref, "category": category, "source_key": key_ref(record.key),
                               "origin": origin_meta(record.origin), "ai": bool(record.ai),
                               "predecessors": [origin_meta(o) for o in record.predecessors],
                               "missing_fields": list(record.missing_fields),
                               "unsupported_fields": [key_ref(k) for k in record.unsupported_fields],
                               "fields": field_metadata})
            ai += bool(record.ai)
            inherited[record.origin.layer] += 1
            missing.update(record.missing_fields)
            if category in SCHEMA and isinstance(record.node.value, Table):
                for entry in record.node.value.entries:
                    if entry.key.value not in SCHEMA[category]:
                        # Unknown field names may themselves contain source content.
                        invalid["unexpected_row_field"] += 1
                if category.startswith("quest_"):
                    flag = record.node.value.get("ai")
                    if flag is not None and type(flag.value) is not bool:
                        types["non_boolean_ai_flag"] += 1
                    for index in range(1, 6):
                        node = record.node.value.get(index)
                        if node is not None and not isinstance(node.value, str):
                            types["non_text_quest_slot"] += 1
            if category == "gossip" and isinstance(record.node.value, Table):
                for key, entry in record.node.value.effective().items():
                    if type(key) is int:
                        hashes_count += 1
                    elif key == "!code" and isinstance(entry.value.value, Table):
                        code_entries += len(entry.value.value.effective())
                    else:
                        invalid["unexpected_gossip_key"] += 1
            if category == "object_text" and isinstance(record.node.value, Table):
                variants += sum(isinstance(e.value.value, Table) for e in record.node.value.effective().values())
            for leaf in record.fields.values():
                nils += leaf.node.value is None
                text_fields += isinstance(leaf.node.value, str)
                for finding in leaf.grammar:
                    if finding.status != "supported":
                        review_findings.append({"record_ref": record_ref, "category": category,
                                                "file": leaf.origin.file, "line": leaf.origin.line,
                                                "text_line_offset": finding.line_offset,
                                                "token_category": finding.category, "status": finding.status,
                                                "reason": finding.detail,
                                                "syntax_sha256": hashlib.sha256(finding.syntax.encode("utf-8")).hexdigest()})
                    grammar_categories[finding.category] += 1
                    grammar_status[finding.status] += 1
                    grammar_details[finding.detail] += 1
                    # Keep shapes, not literal gender-branch words or unknown template text.
                    parts = finding.syntax[1:-1].split(":")
                    if finding.category in ("player_name", "player_class", "player_race"):
                        shape = finding.category + (":" + parts[1] if len(parts) == 2 and parts[1] in {"н", "р", "д", "з", "о", "м", "к"} else ":default" if len(parts) == 1 else ":unknown")
                        if parts[0] != parts[0].lower():
                            shape += ":capitalized"
                    else:
                        shape = finding.category
                    grammar_forms[shape] += 1
        summaries[category] = {
            "effective_records": len(records), "effective_by_origin_layer": counts(inherited),
            "ai_marked_records": ai, "missing_positional_fields": counts(missing),
            "explicit_nil_fields": nils, "string_fields_including_metadata": text_fields,
            "unsupported_fields": counts(invalid), "invalid_field_types": counts(types),
            "gossip_hash_entries": hashes_count, "gossip_code_entries": code_entries,
            "object_namesake_variants": variants,
        }
    views, conflicts = dataset.faction_views()
    filtered, _ = dataset.faction_views(include_ai=False)
    replacements = Counter(row["category"] for row in dataset.replacements)
    raw = sorted(dataset.raw, key=lambda row: (row["category"], row["layer"]))
    return {
        "schema_version": 1,
        "source": {"repository": REPOSITORY, "revision": revision, "files": dict(sorted(hashes.items()))},
        "target": {"client": "WoW Forever", "language": "ukUA"},
        "scope": "ClassicUA source inventory; not Spoken mapping, display, or audio coverage",
        "loading_order": order,
        "raw_declarations": raw,
        "effective_categories": summaries,
        "replaced_records": counts(replacements),
        "replacement_events": dataset.replacements,
        "faction_views": {f: {"with_ai": len(views[f]), "without_ai": len(filtered[f]),
                              "ai_marked": sum(bool(r.ai) for r in views[f].values())} for f in views},
        "faction_shared_conflicts": conflicts,
        "grammar": {"categories": counts(grammar_categories), "statuses": counts(grammar_status),
                    "shapes": counts(grammar_forms), "review_reasons": counts(grammar_details)},
        "provenance": provenance,
        "grammar_review_findings": review_findings,
        "unsupported_constructs": [],
        "warnings": warnings + [
            {"code": "permissions_unresolved"},
            {"code": "inherited_sod_rows_require_forever_review"},
            {"code": "player_grammar_not_rendered_or_converted"},
        ],
        "errors": [],
    }


def audit_checkout(path, expected_hashes, revision=PINNED_REVISION):
    reader = GitSource(path, revision)
    dataset, order = load_dataset(reader, revision)
    for path in ("scripts/entries.lua", "scripts/utils.lua", "entries/class.lua", "entries/race.lua"):
        reader.read(path)
    if reader.hashes != expected_hashes:
        raise SourceError("<lock>", 1, "ClassicUA source file hashes or manifest set differ from sources.lock.json")
    report = metadata_report(dataset, reader.hashes, order, revision)
    return dataset, report


def report_json(report):
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
