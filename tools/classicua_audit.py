"""Audit a separate pinned ClassicUA checkout; emit metadata only under ignored build/."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.classicua.lua import SourceError
from adapters.classicua.source import PINNED_REVISION, audit_checkout, report_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Clean ClassicUA checkout at the pinned Git revision")
    parser.add_argument("--output", type=Path, default=ROOT / "build/classicua-audit.json")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    build = (ROOT / "build").resolve()
    if not output.is_relative_to(build) or output == build:
        parser.error("Report output must be inside this project's ignored build/ directory")
    if output.is_relative_to(args.source.resolve()):
        parser.error("Report output must not be inside the ClassicUA source checkout")
    try:
        lock = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))
        if lock["classicua"]["revision"] != PINNED_REVISION:
            raise SourceError("<lock>", 1, "ClassicUA revision in sources.lock.json differs from the adapter pin")
        _, report = audit_checkout(args.source, lock["classicua"]["files"])
    except (SourceError, OSError, KeyError, ValueError) as error:
        if isinstance(error, SourceError):
            detail = {"file": error.file, "line": error.line, "message": error.message}
        else:
            detail = {"file": "<audit>", "line": 1, "message": "Unable to read source or lock metadata"}
        report = {"unsupported_constructs": [detail] if isinstance(error, SourceError) and error.kind == "syntax" else [], "errors": [detail]}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report_json(report), encoding="utf-8")
        print(f"Audit failed: {detail['file']}:{detail['line']}: {detail['message']}", file=sys.stderr)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report_json(report), encoding="utf-8")
    print(f"Metadata audit written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
