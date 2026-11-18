#!/usr/bin/env python3
"""Review pinned Quest and Gossip translations for private local testing."""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.auto_one_to_one import machine_candidates
from adapters.gossip_machine import candidates as gossip_candidates
from adapters.local_review_store import strict_json
from adapters.source_revision_store import SourceReviewStore, digest, sha
from adapters.sqlite_translation_store import DB_ENV, default_db_path, enable_sqlite
from adapters.translation_agent import MODULES, STATUSES, TranslationAgent, candidate

RIGHTS = "docs/CLASSICUA_PERMISSION.md#classicua-permission-record"


def evidence(state, spoken, db_path, *, revalidate=True):
    from tools.build_ukrainian import local_gossip_texts
    from adapters.crosswalk import digest as spoken_digest
    from adapters.mapping import target_context
    from tools.gossip_coverage import classicua_hash, read_pinned_corpus
    from adapters.local_review_store import LocalFile
    from tools.gossip_translation_review import EMPTY, LEDGER, normalized, validate_ledger
    from tools.source_revision_review import trusted_inventory

    if revalidate:
        state.revalidate_inputs()
    LocalFile(state.allowed_directory / LEDGER.name, state.allowed_directory, EMPTY, validate_ledger)
    lines = read_pinned_corpus(spoken, state.inventory.revision)
    trusted = trusted_inventory(state, lines)
    target_revision = state.inventory.revision
    rows = []
    mapped = set()
    joins = {review.decision.target_id: review.decision.source_evidence_sha256
             for review in state.reviews}
    for observation in state.translation_observations():
        row = observation.row()
        provenance = row["provenance"][0]
        if provenance["provider"] != "classicua":
            continue
        if not state.policy.stores("classicua"):
            continue
        target = row["target_id"]
        mapped.add(target)
        rows.append(candidate(domain="quest", target_id=target, provider="classicua",
            revision=state.source.revision, target_revision=target_revision,
            original=observation.original, text=row["text"],
            context=digest([row["target_context_sha256"], row["source_context_sha256"],
                            row["source_id"], row["grammar_sha256"], joins[target]]),
            provenance={**provenance, "rights_ref": RIGHTS, "mapping_evidence": joins[target],
                        "target_file_sha256": state.inventory.targets[target].evidence_sha256},
            identity=True,
            rights=row["rights_status"] == "reviewed"))
    if "classicua" in state.policy.sources and state.policy.stores("classicua"):
        # Quest 1:1 hints are reviewable, but require a Stage 3 join for import.
        for row in machine_candidates(state.dataset, state.source, state.inventory,
                state.original_index, state._hints,
                allow_ai_transations=state.policy.allows_ai_transations("classicua")):
            if row["target_id"] in mapped:
                continue
            rows.append(candidate(domain="quest", target_id=row["target_id"], provider="classicua",
                revision=state.source.revision, target_revision=target_revision,
                original=state.original_index.original_english[row["target_id"]],
                text=row["text"], context=digest([row["target_context_sha256"],
                                                row["source_context_sha256"]]),
                provenance={k: row[k] for k in ("source_id", "source_file", "source_file_sha256",
                                                "source_layer", "field_sha256")} |
                           {"rights_ref": RIGHTS}, rights=True,
                ai=state.source.units[row["source_id"]].ai))
        gossip, _, _ = gossip_candidates(state, lines, local_gossip_texts(state))
        canonical = defaultdict(set)
        for line in lines:
            moment = line.get("lineId")
            original = line.get("originalText")
            npc = line.get("npcId")
            if line.get("source") != "gossip" or not isinstance(original, str):
                continue
            target = state.inventory.targets.get(moment)
            if (target and target.family == "gossip" and any(
                    context["npc_id"] == npc and context["npc_type"] == line.get("npcType")
                    and context["wording_sha256"] == spoken_digest(original)
                    for context in state.inventory.contexts.get(moment, ()))):
                canonical[npc, classicua_hash(original)].add(moment)
        for row in gossip:
            hashed = row["target_id"].rsplit(":", 1)[1]
            originals = [trusted["gossip", f"gossip:{npc}:{hashed}"]["english_original"]
                         for npc in row["bindings"]]
            contexts = {str(npc): sorted(canonical[npc, int(hashed)]) for npc in row["bindings"]}
            moments = {moment: target_context(state.inventory, moment)
                       for matches in contexts.values() for moment in matches}
            groups = {sha(normalized(original)) for original in originals}
            if len(groups) != 1:
                continue
            rows.append(candidate(domain="gossip", target_id=row["target_id"], provider="classicua",
                revision=row["source_revision"], target_revision=target_revision,
                original=originals[0], text=row["text"],
                context=digest([row["context_sha256"], contexts, moments]),
                provenance={"origin": row["source_provenance"], "overrides": row["source_overrides"],
                            "canonical_moments": contexts, "rights_ref": RIGHTS},
                rights=True, identity=all(contexts.values()), ai=row["ai"],
                bindings=row["bindings"], group_sha=next(iter(groups))))
    # Captured external versions can be assessed against Spoken, but an uploaded
    # source_ref is neither independently audited provenance nor rights evidence.
    store = SourceReviewStore(db_path)
    for ref in store.revisions():
        provider = ref["provider"]
        if provider == "classicua" or provider not in state.policy.sources or not ref["latest"]:
            continue
        for row in store.candidates(provider, ref["revision"]):
            proof = trusted.get((row["domain"], row["target_id"]))
            if not proof or any(row[k] != proof[k] for k in ("context_sha256", "english_sha256")):
                continue
            if sha(row["ukrainian_text"]) != row["text_sha256"]:
                continue
            rows.append(candidate(domain=row["domain"], target_id=row["target_id"],
                provider=provider, revision=row["revision"], target_revision=target_revision,
                original=proof["english_original"], text=row["ukrainian_text"],
                context=row["context_sha256"], provenance={"declared_source_ref": row["source_ref"]},
                identity=True, group_sha=proof["english_sha256"] if row["domain"] == "gossip" else None))
    return sorted(rows, key=lambda r: (r["domain"], r["target_id"], r["provider"], r["id"]))


def load_service(classicua, spoken, db_path):
    from tools.review_ui_server import build_state, validate_source_paths
    validate_source_paths(classicua, spoken)
    state = build_state(classicua, spoken, ROOT / "build/stage4b-decisions.json",
                        None, ROOT / "build/stage3-ui-reviews.json",
                        ROOT / "build/translation-reviews.json")
    return TranslationAgent(db_path, lambda: evidence(state, spoken, db_path, revalidate=False))


def execute(service, args):
    model = None
    if args.model_assessment:
        from tools.source_revision_review import _private
        path = _private(args.model_assessment)
        if path.stat().st_size > 65536:
            raise ValueError("model_assessment_file_exceeds_64_kib")
        model = strict_json(path.read_bytes())
    return service.run(args.mode if args.action == "review" else args.action,
                       module=args.module, candidate_ids=args.candidate or (),
                       status=args.status, limit=args.limit, offset=args.offset,
                       dry_run=args.dry_run, confirm=args.confirm, model=model)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "report", "history", "review", "import-verified"))
    parser.add_argument("mode", nargs="?", choices=("one", "batch", "pending"))
    parser.add_argument("--classicua", type=Path, required=True)
    parser.add_argument("--spoken", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=os.environ.get(DB_ENV) or default_db_path())
    parser.add_argument("--module", choices=MODULES, default="all")
    parser.add_argument("--candidate", action="append", help="Exact ID from status, repeat for batch")
    parser.add_argument("--status", choices=STATUSES)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm", action="store_true", help="Confirm imports for private local tests")
    parser.add_argument("--model-assessment", type=Path, help="Optional advisory JSON under build/")
    parser.add_argument("--json", action="store_true", help="Emit JSON for automation")
    args = parser.parse_args(argv)
    if (args.action == "review") != bool(args.mode):
        parser.error("review needs one, batch or pending")
    try:
        with enable_sqlite(args.db) as db_path:
            result = execute(load_service(args.classicua, args.spoken, db_path), args)
    except (ValueError, OSError, RuntimeError, sqlite3.Error, KeyError, TypeError) as error:
        from tools.review_ui_server import _reason
        print(f"Translation review failed ({_reason(error)}). Check pinned sources, input and --help.",
              file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for key, value in result.items():
            if key not in ("items", "reasons"):
                print(f"{key.replace('_', ' ').capitalize()}: {value}")
        for row in result.get("items", ()):
            item = row["candidate"]
            print(f"{item['target_id']}  {row['status']}  {item['id']}")
            failed = [key for key, passed in row.get("checks", {}).items() if not passed]
            if failed:
                print("  Check: " + ", ".join(failed))
            for message in row.get("findings", []) + row.get("corrections", []):
                print(f"  {message}")
        for row in result.get("reasons", ()):
            print(f"{row['candidate_id']}  {row['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
