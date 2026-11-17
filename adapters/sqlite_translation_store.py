"""Durable local SQLite translation ledgers, compatible with existing JSON validators.

SQLite is the writable source of truth once enabled. Each exact legacy JSON
ledger is migrated once and retained untouched as an import backup. Normalized
translation_memory provides cross-revision text reuse without auto-approval.
"""
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import sqlite3

LEDGER_NAMES = frozenset({
    "stage4b-decisions.json",
    "stage3-ui-reviews.json",
    "translation-reviews.json",
    "machine-one-to-one.json",
    "gossip-translation-reviews.json",
})
DB_ENV = "SPOKEN_TRANSLATION_DB"


def default_db_path():
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "spoken-ukrainian" / "translations.sqlite3"


def protected_path(value):
    path = Path(value).expanduser().absolute()
    if path.is_dir() or any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("sqlite_translation_db_symlink_or_directory_forbidden")
    return path


@contextmanager
def enable_sqlite(path=None):
    """Opt-in for a CLI's lifetime, without altering test-library defaults."""
    chosen = protected_path(path or default_db_path())
    old = os.environ.get(DB_ENV)
    os.environ[DB_ENV] = str(chosen)
    try:
        yield chosen
    finally:
        if old is None:
            os.environ.pop(DB_ENV, None)
        else:
            os.environ[DB_ENV] = old


@contextmanager
def connection(path):
    path = protected_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # New local database and sqlite temporary files are private by default.
    old_umask = os.umask(0o077)
    try:
        db = sqlite3.connect(path, timeout=10, isolation_level=None)
    finally:
        os.umask(old_umask)
    try:
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS ledger_documents (
                ledger_name TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK (revision >= 1),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS translation_memory (
                version_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL CHECK(domain IN ('gossip', 'quest')),
                english_sha256 TEXT NOT NULL,
                ukrainian_text TEXT NOT NULL,
                review_status TEXT NOT NULL,
                provider TEXT NOT NULL,
                target_id TEXT NOT NULL,
                context_sha256 TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_translation_memory_original
                ON translation_memory(domain, english_sha256, review_status);
            INSERT OR IGNORE INTO schema_migrations(version) VALUES (1);
        """)
        os.chmod(path, 0o600)
        yield db
    finally:
        db.close()


def _memory_versions(db, name, data):
    if name not in ("gossip-translation-reviews.json", "translation-reviews.json"):
        return
    domain = "gossip" if name.startswith("gossip") else "quest"
    # Incremental index: don't rewrite every translation on each decision.
    incoming = [row["id"] for row in data["versions"]]
    if incoming:
        db.execute(
            "DELETE FROM translation_memory WHERE domain = ? AND version_id NOT IN ("
            + ",".join("?" for _ in incoming) + ")",
            (domain, *incoming))
    else:
        db.execute("DELETE FROM translation_memory WHERE domain = ?", (domain,))
    for row in data["versions"]:
        status = row["decisions"][-1]["decision"] if row["decisions"] else "pending"
        english_sha = row["english_sha256"] if domain == "gossip" else row["original_sha256"]
        context_sha = row["context_sha256"] if domain == "gossip" else row["target_context_sha256"]
        provider = row["provider"] if domain == "gossip" else row["kind"]
        target = row["group_id"] if domain == "gossip" else row["target_id"]
        db.execute(
            """INSERT INTO translation_memory
                (version_id, domain, english_sha256, ukrainian_text,
                 review_status, provider, target_id, context_sha256)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(version_id) DO UPDATE SET
                   review_status = excluded.review_status
               WHERE translation_memory.review_status != excluded.review_status""",
            (row["id"], domain, english_sha, row["text"], status,
             provider, target, context_sha),
        )


class SQLiteDocument:
    """Drop-in backend for LocalFile, with optimistic concurrency and validation."""

    def __init__(self, db_path, ledger_path, empty, validate):
        self.db_path = protected_path(db_path)
        self.ledger_path = Path(ledger_path).absolute()
        self.name = self.ledger_path.name
        if self.name not in LEDGER_NAMES:
            raise ValueError("sqlite_unknown_review_ledger")
        self.validate = validate
        self.empty = empty
        with connection(self.db_path) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT payload FROM ledger_documents WHERE ledger_name = ?",
                                 (self.name,)).fetchone()
                if row is None:
                    # First run: import existing ignored JSON, do not delete it.
                    if self.ledger_path.exists():
                        legacy = self.ledger_path.read_text(encoding="utf-8")
                        from adapters.local_review_store import strict_json
                        data = self.validate(strict_json(legacy))
                    else:
                        data = self.validate(empty)
                    payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
                    db.execute(
                        """INSERT INTO ledger_documents(ledger_name, payload, revision)
                           VALUES(?, ?, 1)""", (self.name, payload))
                    _memory_versions(db, self.name, data)
                else:
                    payload = row[0]
                    from adapters.local_review_store import strict_json
                    data = self.validate(strict_json(payload))
                db.commit()
            except BaseException:
                db.rollback()
                raise
        self.baseline, self.data = payload, data

    def check_unchanged(self):
        with connection(self.db_path) as db:
            row = db.execute("SELECT payload FROM ledger_documents WHERE ledger_name = ?",
                             (self.name,)).fetchone()
        if row is None or row[0] != self.baseline:
            raise ValueError("local_review_conflict_restart_and_reload")

    def save(self, data):
        checked = self.validate(data)
        payload = json.dumps(checked, ensure_ascii=False, sort_keys=True)
        with connection(self.db_path) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT payload FROM ledger_documents WHERE ledger_name = ?",
                                 (self.name,)).fetchone()
                if row is None or row[0] != self.baseline:
                    raise ValueError("local_review_conflict_restart_and_reload")
                if payload != self.baseline:
                    db.execute(
                        """UPDATE ledger_documents
                           SET payload = ?, revision = revision + 1,
                               updated_at = CURRENT_TIMESTAMP
                           WHERE ledger_name = ?""", (payload, self.name))
                    _memory_versions(db, self.name, checked)
                db.commit()
            except BaseException:
                db.rollback()
                raise
        self.baseline, self.data = payload, checked
        return checked


def backup_database(db_path, destination):
    """Consistent online SQLite snapshot (including schema and all review ledgers)."""
    original = protected_path(db_path)
    output = protected_path(destination)
    if original == output or not original.is_file():
        raise ValueError("sqlite_backup_source_or_target_invalid")
    if output.exists():
        raise ValueError("sqlite_backup_target_already_exists")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(original) as source, sqlite3.connect(output) as target:
        source.backup(target)
    os.chmod(output, 0o600)
    return output


def memory_suggestions(db_path, domain, original_hashes):
    """Text reuse is a *suggestion*; never auto-approve/re-import for new contexts."""
    if domain not in ("gossip", "quest"):
        raise ValueError("unknown_translation_memory_domain")
    hashes = set(original_hashes)
    if not hashes:
        return {}
    suggestions = {}
    with connection(db_path) as db:
        for english_sha in sorted(hashes):
            rows = db.execute(
                """SELECT DISTINCT ukrainian_text FROM translation_memory
                   WHERE domain = ? AND english_sha256 = ?
                     AND review_status = 'approved'""",
                (domain, english_sha),
            ).fetchall()
            if len(rows) == 1:
                suggestions[english_sha] = rows[0][0]
    return suggestions
