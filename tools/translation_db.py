#!/usr/bin/env python3
"""Initialize, inspect or back up the private Spoken Ukrainian SQLite translation store."""
import argparse
from contextlib import closing
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
    parser.add_argument("action", choices=("init", "status", "backup", "imports"))
    parser.add_argument("--db", type=Path, default=os.environ.get(DB_ENV) or default_db_path())
    parser.add_argument("--output", type=Path,
                        help="Private backup destination (backup action only)")
    args = parser.parse_args(argv)
    path = args.db.expanduser().absolute()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or path.parent / "backups" / f"translations-{stamp}.sqlite3"
    try:
        if args.action == "backup":
            output = backup_database(path, output)
            print("SQLite backup created:", output)
            return 0
        path = protected_path(path).resolve()
        if args.action == "init":
            with connection(path):
                pass
            print("SQLite database initialized:", path)
        elif args.action == "status":
            if not path.is_file():
                print(json.dumps({"database_exists": False, "path": str(path)}))
                return 0
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
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
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        reason = str(exc)
        safe = reason if reason.replace("_", "").isalnum() else type(exc).__name__
        print("sqlite_store_error:", safe, file=sys.stderr)
        if args.action == "backup":
            explanations = {
                "sqlite_backup_source_missing":
                    "Source database does not exist. Check --db or SPOKEN_TRANSLATION_DB. "
                    "To recover existing reviews, locate or restore their database. "
                    "For a new store only, explicitly run translation_db.py init.",
                "sqlite_backup_same_path":
                    "Source and destination are the same path. Choose a different --output file.",
                "sqlite_backup_target_already_exists":
                    "Destination already exists and was not overwritten. Choose an unused --output file.",
                "sqlite_translation_db_symlink_or_directory_forbidden":
                    "Symlinks (including parent directories) and directory file paths are forbidden. "
                    "Use direct database and destination file paths without symlinks.",
                "sqlite_backup_create_failed":
                    "Cannot create the backup file. Check destination directory permissions and free space.",
            }
            print(explanations.get(reason,
                  "Backup failed. Check that the source is a readable SQLite database and the "
                  "destination directory is writable with enough free space."), file=sys.stderr)
            # Quote paths to prevent control characters from being rendered;
            # omit database contents and raw SQLite/OS exception messages.
            print("Source:", json.dumps(str(path)), file=sys.stderr)
            print("Destination:", json.dumps(str(Path(output).expanduser().absolute())), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
