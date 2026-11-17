#!/usr/bin/env python3
"""Inspect or back up the persistent Spoken Ukrainian SQLite translation store."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import os
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.sqlite_translation_store import (
    default_db_path, protected_path, backup_database, connection, DB_ENV,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "backup", "imports"))
    parser.add_argument("--db", type=Path, default=os.environ.get(DB_ENV) or default_db_path())
    parser.add_argument("--output", type=Path,
                        help="Private backup destination (backup action only)")
    args = parser.parse_args(argv)
    try:
        path = protected_path(args.db)
        if args.action == "status":
            if not path.is_file():
                print(json.dumps({"database_exists": False, "path": str(path)}))
                return 0
            with connection(path) as db:
                ledgers = dict(db.execute(
                    "SELECT ledger_name, revision FROM ledger_documents ORDER BY ledger_name"))
                counts = dict(db.execute(
                    "SELECT domain, COUNT(*) FROM translation_memory GROUP BY domain"))
            print(json.dumps({"database_exists": True, "path": str(path),
                              "ledgers": ledgers, "translation_versions": counts},
                             ensure_ascii=False, indent=2))
        elif args.action == "imports":
            from adapters.import_statistics import report
            print(json.dumps(report(path), ensure_ascii=False, indent=2))
        else:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            output = args.output or path.parent / "backups" / f"translations-{stamp}.sqlite3"
            backup_database(path, output)
            print("SQLite backup created:", output)
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        reason = str(exc)
        safe = reason if reason.replace("_", "").isalnum() else type(exc).__name__
        print("sqlite_store_error:", safe, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
