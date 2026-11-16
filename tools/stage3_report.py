#!/usr/bin/env python3
"""Opt-in offline Stage 3 inventory/diff; outputs metadata under ignored build/ only."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.classicua.source import audit_checkout
from adapters.classicua.evidence import from_audit
from adapters.crosswalk import effective_units, metadata_json
from adapters.mapping import coverage_report, extraction_exclusions, load_reviews
from adapters.spoken import PublicSource, build_index


def reviewed_source(path, manifest, *, return_report=False):
    """Candidate revisions must have a separately supplied reviewed full file manifest."""
    if (set(manifest) != {'revision', 'files', 'review_by'}
            or type(manifest['review_by']) is not str or not manifest['review_by'].strip()):
        raise ValueError('independent_source_manifest_review_required')
    audited = audit_checkout(path, manifest['files'], manifest['revision'])
    return audited if return_report else audited[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--classicua', type=Path, required=True)
    parser.add_argument('--spoken', type=Path, required=True)
    parser.add_argument('--reviews', type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--candidate-manifest', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/stage3-report.json')
    args = parser.parse_args()
    try:
        output = args.output.resolve()
        if not output.is_relative_to((ROOT / 'build').resolve()) or output == (ROOT / 'build').resolve():
            raise ValueError('report_output_must_be_under_build')
        # Do not allow a symlinked build directory to redirect writes outside this repository.
        if not output.is_relative_to(ROOT.resolve() / 'build'):
            raise ValueError('report_output_must_be_under_build')
        for source in (args.classicua, args.spoken, args.candidate):
            if source and output.is_relative_to(source.resolve()):
                raise ValueError('report_must_not_modify_input_checkout')
        lock = json.loads((ROOT / 'sources.lock.json').read_text())
        manifest = json.loads((ROOT / 'tests/stage3_sources.json').read_text())
        if manifest['revision'] != lock['spoken']['revision']:
            raise ValueError('spoken_reference_revision_mismatch')
        inventory = build_index(PublicSource(args.spoken, manifest))
        baseline, audit = audit_checkout(args.classicua, lock['classicua']['files'])
        source_inventory = from_audit(baseline, audit)
        source_inventories = {source_inventory.revision: source_inventory}
        dataset = baseline
        if bool(args.candidate) != bool(args.candidate_manifest):
            raise ValueError('candidate_checkout_and_reviewed_manifest_required_together')
        if args.candidate:
            candidate_manifest = json.loads(args.candidate_manifest.read_text())
            dataset, candidate_audit = reviewed_source(args.candidate, candidate_manifest, return_report=True)
            candidate_inventory = from_audit(dataset, candidate_audit)
            source_inventories[candidate_inventory.revision] = candidate_inventory
        reviews = load_reviews(json.loads(args.reviews.read_text()),
                               source_inventories=source_inventories) if args.reviews else []
        evidence = {r.decision.source_id: r.decision.source_evidence_sha256 for r in reviews}
        old = effective_units(baseline, evidence) if args.candidate else None
        units = effective_units(dataset, evidence)
        report = coverage_report(units, inventory, reviews, old, source_inventories=source_inventories)
        report['source_raw_declarations'] = sum(r['declarations'] for r in audit['raw_declarations'])
        if args.candidate:
            report['source_raw_declarations'] = None  # Baseline is not candidate coverage.
        report['extraction_exclusions'] = extraction_exclusions(dataset)
        report['source_inputs'] = {'baseline': audit['source']}
        if args.candidate:
            before = audit['source']['files']
            after = candidate_manifest['files']
            report['source_inputs']['candidate'] = candidate_manifest
            drift = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
            report['source_file_drift'] = drift
            report['source_drift_without_effective_unit_change'] = bool(drift) and all(
                row['change'] == 'unchanged' for row in report['effective_diff'])
        report['source_ai_disabled_units'] = len(effective_units(dataset, include_ai=False))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(metadata_json(report), encoding='utf-8')
        print(json.dumps({'output': str(output.relative_to(ROOT)), 'coverage': report['coverage']}, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        # Never echo arbitrary source, JSON values, translated keys, or parser excerpts.
        print('stage3_input_or_review_validation_failed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
