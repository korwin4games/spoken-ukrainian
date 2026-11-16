#!/usr/bin/env python3
"""Stage 4A: offline pinned Spoken inventory → ordered source coverage dry-run.

Reads real public original wording, never guesses a ClassicUA→Spoken source ID.
No real reviewed joins exist yet: ClassicUA is intentionally unbound; Another
and Own Translator remain stub and mock. This report is not a pack or a real
translation coverage claim and exports only canonical IDs and summary metadata.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.spoken import PublicSource, build_index
from adapters.spoken.text_index import index_verified_originals
from adapters.translation_sources import (
    AlternativeSourceStub, ClassicUAProvider, OwnTranslatorMock, CLIENT_LOCALE,
    TranslationRequest, load_source_policy, resolve_spoken_batch,
)


def build_coverage(reader, inventory, policy, client_locale=None):
    """Verified English originals only. Never forge joins to ClassicUA.

    Source-identity binding requires separately accepted Stage 3 join evidence.
    Until that integration is independently reviewed, source_identity is None
    for every genuine target ID. No ClassicUA translation is therefore selected.
    """
    # Client-locale selection is independent of English-original availability.
    # Even a Places/Bosses target without a verified original gets the chosen
    # locale under [] / {}; no provider is called in that mode.
    if not policy.sources and (
            type(client_locale) is not str or not CLIENT_LOCALE.fullmatch(client_locale)):
        raise ValueError("client_locale_required_for_empty_source_policy")
    index = index_verified_originals(reader, inventory)
    requests = [
        TranslationRequest(None, text, identity, client_locale)
        for identity, text in sorted(index.original_english.items())
    ]
    registry = {
        "classicua": ClassicUAProvider({}),
        "another": AlternativeSourceStub(),
        "own_translator": OwnTranslatorMock(),
    }
    selection = resolve_spoken_batch(requests, policy, registry, inventory.targets)
    batch = selection.metadata()
    # Preserve missing-English evidence without suppressing client-locale
    # selection. No fabricated text or source ID is introduced here.
    unavailable = [
        {"canonical_spoken_id": identity,
         "status": "client_language" if not policy.sources else "public_original_not_verified",
         "source": "client_language" if not policy.sources else None,
         "field_sha256": None,
         "client_locale": client_locale if not policy.sources else None,
         "translated": False, "original_verified": False}
        for identity in index.unresolved
    ]
    eligible = [row | {"original_verified": True} for row in batch.pop("records")]
    combined = sorted(eligible + unavailable,
                      key=lambda row: row["canonical_spoken_id"])
    if len(combined) != len(inventory.targets) or len({
            row["canonical_spoken_id"] for row in combined}) != len(combined):
        raise ValueError("indexed_spoken_total_mismatch")
    report = {
        "schema_version": 1,
        "scope": "Stage 4A offline public-original dry-run, NOT reviewed translation coverage",
        "spoken_revision": inventory.revision,
        "public_files": inventory.files,
        "source_policy": list(policy.sources),
        "mapping_status": "no_reviewed_real_join_inputs",
        "coverage": {
            "total_spoken_identities": len(inventory.targets),
            "with_verified_public_original": len(requests),
            "without_verified_public_original": len(unavailable),
            "translation_candidates_pending_review": batch["translation_candidates_pending_review"],
            "approved_translations": 0,
            "without_approved_translation": len(inventory.targets),
            "original_english_selected": batch["original_english_fallback"],
            "client_language_selected": batch["client_language"] + (
                len(unavailable) if not policy.sources else 0),
            "untranslated_with_public_original": batch["untranslated_no_source"],
            "families": index.families,
        },
        "stages": batch["by_source"],
        "records": combined,
    }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spoken", type=Path, required=True,
                        help="Clean pinned Spoken checkout (no fetching)")
    parser.add_argument("--policy", type=Path, default=ROOT / "config/translation_sources.json")
    parser.add_argument("--client-locale", help="Actual client locale supplied by caller for [] / {}")
    parser.add_argument("--output", type=Path, default=ROOT / "build/stage4-source-coverage.json")
    args = parser.parse_args(argv)
    try:
        output = args.output.resolve()
        root = ROOT.resolve()
        allowed = root / "build"
        if (not output.is_relative_to(allowed)
                or output == allowed
                or not args.output.absolute().is_relative_to(allowed)
                or output.is_relative_to(args.spoken.resolve())):
            raise ValueError("coverage_output_must_be_under_build")
        policy = load_source_policy(args.policy)
        if not policy.sources and not args.client_locale:
            raise ValueError("client_locale_required_for_empty_source_policy")
        lock = json.loads((ROOT / "sources.lock.json").read_text())
        manifest = json.loads((ROOT / "tests/stage3_sources.json").read_text())
        if manifest["revision"] != lock["spoken"]["revision"]:
            raise ValueError("spoken_reference_revision_mismatch")
        reader = PublicSource(args.spoken, manifest)
        inventory = build_index(reader)
        report = build_coverage(reader, inventory, policy, args.client_locale)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(output.relative_to(root)),
                          "coverage": report["coverage"]}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError):
        # Never emit unreviewed original text, upstream file excerpts or input JSON.
        print("stage4_public_inventory_or_policy_validation_failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
