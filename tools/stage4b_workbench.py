#!/usr/bin/env python3
"""Stage 4B: audited, offline Quest mapping review queue. NEVER auto-approves."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.classicua.source import audit_checkout
from adapters.classicua.evidence import from_audit
from adapters.mapping import candidates, load_reviews
from adapters.review_worksheet import worksheet_csv
from adapters.review_workbench import (approve_explicit_join, build_workbench,
                                       empty_decisions, record_decision)
from adapters.spoken import PublicSource, build_index


def protected_output(path, inputs=()):
    """All writes stay in ignored build/, away from source checkouts and symlinks."""
    target = path.resolve()
    root = ROOT.resolve()
    allowed = root / "build"
    if (not target.is_relative_to(allowed) or target == allowed
            or not path.absolute().is_relative_to(allowed)
            or any(target.is_relative_to(p.resolve()) for p in inputs if p is not None)):
        raise ValueError("stage4b_output_must_be_under_build")
    return target


def workbench_main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classicua", type=Path, required=True,
                        help="Clean pinned ClassicUA checkout")
    parser.add_argument("--spoken", type=Path, required=True,
                        help="Clean pinned Spoken checkout")
    parser.add_argument("--reviews", type=Path,
                        help="Stage 3 review_file JSON; output path when approving")
    parser.add_argument("--approve-request", type=Path,
                        help="Independently attested, explicit two-reviewer JoinProof JSON; requires --reviews")
    parser.add_argument("--decisions", type=Path,
                        default=ROOT / "build/stage4b-decisions.json",
                        help="Manual reject/defer-only metadata JSON (created on first decision)")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "build/stage4b-review-queue.json")
    parser.add_argument("--worksheet-output", type=Path,
                        default=ROOT / "build/stage4b-review-worksheet.csv",
                        help="Metadata-only CSV for human review; never an approval file")
    parser.add_argument("--faction", choices=("alliance", "horde"),
                        default="horde")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--offset", type=int, default=0)
    group = parser.add_argument_group("Record a human rejection or deferral (NOT approval)")
    group.add_argument("--source-id")
    group.add_argument("--target-id")
    group.add_argument("--decision", choices=("rejected", "deferred"))
    group.add_argument("--reason", choices=("insufficient_evidence", "wrong_speaker",
                       "faction_conflict", "wording_mismatch", "wrong_event",
                       "ambiguous_variant", "source_not_applicable", "other"))
    group.add_argument("--reviewer")
    args = parser.parse_args(argv)
    try:
        record_args = (args.source_id, args.target_id, args.decision,
                       args.reason, args.reviewer)
        wants_record = any(x is not None for x in record_args)
        wants_approval = args.approve_request is not None
        if (wants_record and not all(x is not None for x in record_args)
                or wants_record and wants_approval):
            raise ValueError("complete_exclusive_decision_fields_required")
        if wants_approval and not args.reviews:
            raise ValueError("approval_requires_reviews_output")
        output = protected_output(args.output, [args.classicua, args.spoken])
        worksheet_output = protected_output(args.worksheet_output,
                                           [args.classicua, args.spoken])
        if worksheet_output == output or worksheet_output == args.decisions.resolve():
            raise ValueError("worksheet_file_must_be_distinct")
        if wants_approval:
            reviews_output = protected_output(
                args.reviews, [args.classicua, args.spoken, args.approve_request])
            if (reviews_output == output or reviews_output == worksheet_output
                    or reviews_output == args.decisions.resolve()):
                raise ValueError("review_output_must_be_distinct")
        if wants_record:
            decision_output = protected_output(args.decisions, [args.classicua, args.spoken])
            if decision_output == output or decision_output == worksheet_output:
                raise ValueError("decision_file_must_differ_from_queue_report")
        lock = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))
        manifest = json.loads((ROOT / "tests/stage3_sources.json").read_text(encoding="utf-8"))
        if manifest["revision"] != lock["spoken"]["revision"]:
            raise ValueError("spoken_reference_revision_mismatch")
        spoken = build_index(PublicSource(args.spoken, manifest))
        dataset, audit = audit_checkout(args.classicua, lock["classicua"]["files"])
        source = from_audit(dataset, audit)
        if source.revision != lock["classicua"]["revision"]:
            raise ValueError("classicua_source_revision_mismatch")
        reviews = (
            load_reviews(json.loads(args.reviews.read_text(encoding="utf-8")),
                         source_inventories={source.revision: source})
            if args.reviews and args.reviews.is_file() else ()
        )
        if args.reviews and not wants_approval and not args.reviews.is_file():
            raise ValueError("review_file_required_when_reading")
        decisions = (json.loads(args.decisions.read_text(encoding="utf-8"))
                     if args.decisions.is_file() else empty_decisions())
        if wants_record:
            decisions = record_decision(
                decisions, candidates(source.units, spoken), source, spoken,
                source_id=args.source_id, target_id=args.target_id,
                decision=args.decision, reason=args.reason, reviewer=args.reviewer)
        approved_json = None
        if wants_approval:
            approved_json = approve_explicit_join(
                source, spoken, json.loads(args.approve_request.read_text(encoding="utf-8")),
                existing_reviews=reviews, decisions=decisions)
            reviews = load_reviews(approved_json,
                                   source_inventories={source.revision: source})
        report = build_workbench(source, spoken, decisions=decisions, reviews=reviews,
                                 limit=args.limit, offset=args.offset, faction=args.faction)
        csv_content = worksheet_csv(report)
        if approved_json is not None:
            reviews_output.parent.mkdir(parents=True, exist_ok=True)
            reviews_output.write_text(
                json.dumps(approved_json, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
        if wants_record:
            decision_output.parent.mkdir(parents=True, exist_ok=True)
            decision_output.write_text(
                json.dumps(decisions, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
        worksheet_output.parent.mkdir(parents=True, exist_ok=True)
        worksheet_output.write_text(csv_content, encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(output.relative_to(ROOT.resolve())),
                          "summary": report["summary"]}, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, UnicodeError,
            json.JSONDecodeError):
        # Do not print private translation bodies, untrusted reviewer text or paths.
        print("stage4b_source_or_review_validation_failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(workbench_main())
