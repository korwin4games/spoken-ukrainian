#!/usr/bin/env python3
"""Local-only source revision capture, comparison, conflict and selection CLI.

Never mutates public repositories or source locks. Importing a provider's
candidate is not content approval; selecting it requires explicit human
review, verified pinned Spoken context, and later local test build.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.crosswalk import digest
from adapters.mapping import target_context
from adapters.local_review_store import strict_json
from adapters.sqlite_translation_store import DB_ENV, default_db_path, enable_sqlite
from adapters.source_revision_store import SourceReviewStore, CHECKS, FIELDS, SOURCES, sha
from tools.gossip_coverage import gossip_evidence, read_pinned_corpus
from tools.gossip_translation_review import normalized

HEX40 = re.compile(r"[0-9a-f]{40}\Z")


def gossip_contexts(lines):
    """Independent exact NPC/English-hash proof from a pinned Spoken corpus."""
    trusted = {}
    evidence, _, unsafe, ambiguous_common, _ = gossip_evidence(lines)
    for row, npc, hash_num in evidence:
        if (npc, hash_num) in unsafe:
            continue
        english = row["originalText"]
        text = normalized(english)
        target = f"gossip:{npc}:{hash_num}"
        english_sha = sha(text)
        context_sha = digest({"npc_id": npc, "english_hash": hash_num,
                              "english_sha256": english_sha})
        key = "gossip", target
        proof = {"english_sha256": english_sha, "context_sha256": context_sha,
                 "english_original": english, "npc_id": npc, "english_hash": hash_num,
                 "common_safe": hash_num not in ambiguous_common}
        previous = trusted.get(key)
        if previous and (previous["english_sha256"] != english_sha
                         or previous["context_sha256"] != context_sha):
            raise ValueError("ambiguous_source_gossip_hash_collision")
        trusted[key] = proof
    return trusted


def quest_contexts(state):
    trusted = {}
    for target, english in state.original_index.original_english.items():
        if target not in state.inventory.targets:
            raise ValueError("unverified_source_quest_target")
        if state.inventory.targets[target].family != "quest":
            continue
        proof = {"english_sha256": sha(english),
                 "context_sha256": target_context(state.inventory, target),
                 "english_original": english}
        trusted["quest", target] = proof
    return trusted


def trusted_inventory(state, lines):
    return gossip_contexts(lines) | quest_contexts(state)


def classicua_snapshot(state, trusted, gossip):
    """Verified pinned ClassicUA text: Quest needs approved Stage 3 mapping."""
    records = []
    for (domain, target), proof in sorted(trusted.items()):
        if domain != "gossip":
            continue
        npc, hash_num = proof["npc_id"], proof["english_hash"]
        explicit = gossip["byNpc"].get(npc, {})
        if hash_num in explicit:
            value, provenance = explicit[hash_num], f"classicua:npc:{npc}:{hash_num}"
        elif hash_num in gossip["common"] and proof.get("common_safe", True):
            value, provenance = gossip["common"][hash_num], f"classicua:common:{hash_num}"
        else:
            continue
        records.append({"domain": "gossip", "target_id": target,
                        "english_sha256": proof["english_sha256"],
                        "context_sha256": proof["context_sha256"],
                        "ukrainian_text": value, "source_ref": provenance})
    # Quest proposals require an independently approved source -> Spoken
    # Stage 3 join; numeric quest equality is never sufficient proof.
    for observation in state.translation_observations():
        row = observation.row()
        if row["kind"] != "provider":
            continue
        provenance = row["provenance"][0]
        if provenance["provider"] != "classicua":
            continue
        key = "quest", row["target_id"]
        proof = trusted.get(key)
        if not proof:
            continue
        if (proof["english_sha256"] != row["original_sha256"]
                or proof["context_sha256"] != row["target_context_sha256"]):
            raise ValueError("source_quest_mapping_evidence_changed")
        records.append({"domain": "quest", "target_id": row["target_id"],
                        "english_sha256": proof["english_sha256"],
                        "context_sha256": proof["context_sha256"],
                        "ukrainian_text": row["text"],
                        "source_ref": provenance["source_ref"]})
    return {"provider": "classicua", "revision": state.source.revision,
            "records": records}


def local_evidence(classicua, spoken):
    from tools.review_ui_server import build_state
    from tools.build_ukrainian import local_gossip_texts, validate_source_paths
    validate_source_paths(classicua, spoken)
    state = build_state(classicua, spoken,
                        ROOT / "build/stage4b-decisions.json",
                        None, ROOT / "build/stage3-ui-reviews.json",
                        ROOT / "build/translation-reviews.json",
                        ROOT / "config/translation_sources.json")
    lock = strict_json((ROOT / "sources.lock.json").read_text(encoding="utf-8"))
    if (state.source.revision != lock["classicua"]["revision"]
            or state.inventory.revision != lock["spoken"]["revision"]):
        raise ValueError("source_review_pinned_revision_mismatch")
    lines = read_pinned_corpus(spoken, state.inventory.revision)
    return state, trusted_inventory(state, lines), local_gossip_texts(state)


def _private(path):
    path = Path(path).absolute()
    build = (ROOT / "build").resolve()
    if (path == build or not path.resolve().is_relative_to(build)
            or any(p.is_symlink() for p in (path, *path.parents))):
        raise ValueError("source_review_file_must_be_in_private_build")
    return path


def read_private_snapshot(path, trusted):
    data = strict_json(_private(path).read_text(encoding="utf-8"))
    if type(data) is not dict or set(data) != {"provider", "revision", "records"}:
        raise ValueError("invalid_source_review_import_file")
    # Never let an arbitrary external file impersonate the audited ClassicUA
    # checkout. ClassicUA enters only through the pinned capture command.
    if data["provider"] == "classicua":
        raise ValueError("classicua_source_requires_verified_capture")
    # Templates include English for human inspection, but the provider cannot
    # supply the proof: compare its English body against pinned Spoken.
    rows = []
    for row in data["records"]:
        if type(row) is not dict or set(row) not in (FIELDS, FIELDS | {"english_original"}):
            raise ValueError("invalid_source_review_import_entry")
        proof = trusted.get((row["domain"], row["target_id"]))
        if proof is None:
            raise ValueError("source_review_import_target_unverified")
        if "english_original" in row and row["english_original"] != proof["english_original"]:
            raise ValueError("source_review_import_english_modified")
        if row["ukrainian_text"] == "":
            continue  # Human/model has not provided a candidate for this record.
        if row["source_ref"] == "provide-audited-reference":
            raise ValueError("source_review_requires_real_provenance")
        rows.append({k: row[k] for k in FIELDS})
    # A blank new template must never irreversibly reserve a provider/revision
    # as an empty immutable snapshot, preventing the actual import later.
    if not rows:
        raise ValueError("source_review_import_contains_no_translations")
    return {"provider": data["provider"], "revision": data["revision"],
            "records": rows}


def write_template(trusted, output, provider, revision, offset, limit):
    from adapters.source_revision_store import REV
    if (provider not in SOURCES or type(revision) is not str
            or not REV.fullmatch(revision)
            or offset < 0 or not 1 <= limit <= 1000):
        raise ValueError("invalid_source_template_options")
    path = _private(output)
    if path.exists() or path.is_symlink():
        raise ValueError("source_review_template_already_exists")
    rows = []
    for (domain, target), proof in sorted(trusted.items())[offset:offset + limit]:
        rows.append({"domain": domain, "target_id": target,
                     "english_sha256": proof["english_sha256"],
                     "context_sha256": proof["context_sha256"],
                     "english_original": proof["english_original"],
                     "ukrainian_text": "", "source_ref": "provide-audited-reference"})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump({"provider": provider, "revision": revision, "records": rows},
                  handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.chmod(path, 0o600)
    return len(rows)


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "template", "ingest",
        "revisions", "diff", "compare-providers", "conflicts", "review", "activate", "clear", "active",
        "selection-history"))
    parser.add_argument("--classicua", type=Path)
    parser.add_argument("--spoken", type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--provider", choices=SOURCES, default="another")
    parser.add_argument("--other-provider", choices=SOURCES)
    parser.add_argument("--change", choices=("all", "added", "removed", "changed", "unchanged"),
                        default="all")
    parser.add_argument("--revision")
    parser.add_argument("--before")
    parser.add_argument("--after")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--candidate")
    parser.add_argument("--decision", choices=("approved", "rejected", "deferred"))
    parser.add_argument("--reviewer")
    parser.add_argument("--domain", choices=("gossip", "quest"))
    parser.add_argument("--target")
    for key in CHECKS:
        parser.add_argument("--checked-" + key.replace("_", "-"), action="store_true")
    args = parser.parse_args(argv)
    if args.action in ("capture", "template", "ingest", "review", "activate", "clear", "active"):
        if not args.classicua or not args.spoken:
            raise ValueError("source_review_needs_pinned_checkouts")
    store = SourceReviewStore(args.db or os.environ.get(DB_ENV) or default_db_path())
    trusted = None
    if args.classicua and args.spoken:
        state, trusted, gossip = local_evidence(args.classicua, args.spoken)
    if args.action == "capture":
        result = store.ingest(classicua_snapshot(state, trusted, gossip), trusted)
    elif args.action == "template":
        if not args.output or not args.revision:
            raise ValueError("source_template_needs_output_and_revision")
        result = {"created_records": write_template(trusted, args.output, args.provider,
                                                   args.revision, args.offset,
                                                   40 if args.limit is None else args.limit)}
    elif args.action == "ingest":
        if not args.input:
            raise ValueError("source_review_needs_private_input")
        result = store.ingest(read_private_snapshot(args.input, trusted), trusted)
    elif args.action == "revisions":
        result = {"revisions": store.revisions()}
    elif args.action in ("diff", "compare-providers"):
        if not args.before or not args.after:
            raise ValueError("source_diff_needs_two_revisions")
        same_provider = args.action == "diff"
        if same_provider == bool(args.other_provider):
            raise ValueError("other_provider_required_only_for_compare_providers")
        result = store.compare_snapshots(
            args.provider, args.before, args.other_provider or args.provider, args.after,
            mode="revision" if same_provider else "providers", change_filter=args.change,
            offset=args.offset, limit=(40 if not same_provider and args.limit is None else args.limit))
    elif args.action == "conflicts":
        priority = [p["name"] for p in strict_json(
            (ROOT / "config/translation_sources.json").read_text(encoding="utf-8"))["sources"]]
        result = store.conflicts(priority=[p for p in priority if p in SOURCES])
    elif args.action == "review":
        if not args.candidate or not args.decision or not args.reviewer:
            raise ValueError("source_review_needs_candidate_decision_reviewer")
        checks = {k: getattr(args, "checked_" + k) for k in CHECKS}
        result = store.decide(args.candidate, args.decision, args.reviewer, checks, trusted)
    elif args.action == "activate":
        if not args.candidate or not args.reviewer:
            raise ValueError("source_selection_needs_candidate_and_reviewer")
        result = store.activate(args.candidate, args.reviewer, trusted)
    elif args.action == "clear":
        if not args.domain or not args.target or not args.reviewer:
            raise ValueError("source_selection_clear_needs_identity")
        result = store.clear_selection(args.domain, args.target, args.reviewer, trusted)
    elif args.action == "selection-history":
        if not args.domain or not args.target:
            raise ValueError("source_selection_history_needs_identity")
        result = {"history": store.selection_history(args.domain, args.target)}
    else:
        result = {"selected": store.active(trusted, domain=args.domain)}
    # Only snapshot data and review decisions; no secret credentials or Git writes.
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    # --db must apply to BOTH the new source revision tables and the existing
    # Quest/Gossip review ledgers built by local_evidence. Without this, --db
    # could silently split linked review provenance between two databases.
    preflight = argparse.ArgumentParser(add_help=False)
    preflight.add_argument("--db", type=Path)
    selected, _ = preflight.parse_known_args(argv)
    with enable_sqlite(selected.db or os.environ.get(DB_ENV)):
        try:
            return run(argv)
        except (ValueError, TypeError, KeyError, OSError, RuntimeError) as error:
            detail = str(error)
            if not re.fullmatch(r"[a-z0-9_]{2,100}", detail):
                detail = type(error).__name__
            print("source_review_failed:", detail, file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
