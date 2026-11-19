"""Durable local SQLite translation ledgers, compatible with existing JSON validators.

SQLite is the writable source of truth once enabled. Each exact legacy JSON
ledger is migrated once and retained untouched as an import backup. Normalized
translation_memory provides cross-revision text reuse without auto-approval.
"""
from contextlib import closing, contextmanager
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
    "gossip-machine-one-to-one.json",
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
            CREATE TABLE IF NOT EXISTS source_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL CHECK (provider IN
                    ('classicua', 'another', 'own_translator')),
                revision TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider, revision)
            );
            CREATE TABLE IF NOT EXISTS source_candidates (
                id TEXT PRIMARY KEY,
                snapshot_id INTEGER NOT NULL REFERENCES source_snapshots(id),
                domain TEXT NOT NULL CHECK (domain IN ('gossip', 'quest')),
                target_id TEXT NOT NULL,
                english_sha256 TEXT NOT NULL,
                context_sha256 TEXT NOT NULL,
                ukrainian_text TEXT NOT NULL,
                text_sha256 TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                UNIQUE(snapshot_id, domain, target_id, english_sha256, context_sha256)
            );
            CREATE INDEX IF NOT EXISTS idx_source_candidates_context
                ON source_candidates(domain, target_id, english_sha256, context_sha256);
            CREATE TABLE IF NOT EXISTS source_candidate_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT NOT NULL REFERENCES source_candidates(id),
                decision TEXT NOT NULL CHECK (decision IN
                    ('approved', 'rejected', 'deferred')),
                reviewer TEXT NOT NULL,
                checks_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_source_decisions_version
                ON source_candidate_decisions(candidate_id, id);
            CREATE TABLE IF NOT EXISTS source_active_selections (
                domain TEXT NOT NULL,
                target_id TEXT NOT NULL,
                english_sha256 TEXT NOT NULL,
                context_sha256 TEXT NOT NULL,
                candidate_id TEXT NOT NULL REFERENCES source_candidates(id),
                reviewer TEXT NOT NULL,
                selected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (domain, target_id, english_sha256, context_sha256)
            );
            CREATE TABLE IF NOT EXISTS source_selection_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                target_id TEXT NOT NULL,
                english_sha256 TEXT NOT NULL,
                context_sha256 TEXT NOT NULL,
                candidate_id TEXT NOT NULL REFERENCES source_candidates(id),
                action TEXT NOT NULL CHECK (action IN ('activate', 'clear')),
                reviewer TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_source_selection_history
                ON source_selection_events(domain, target_id, id);
            INSERT OR IGNORE INTO schema_migrations(version) VALUES (1);
            INSERT OR IGNORE INTO schema_migrations(version) VALUES (2);
            CREATE TABLE IF NOT EXISTS build_import_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                artifact_sha256 TEXT NOT NULL,
                spoken_revision TEXT NOT NULL,
                classicua_revision TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS build_import_units (
                snapshot_id INTEGER NOT NULL REFERENCES build_import_snapshots(id),
                domain TEXT NOT NULL,
                unit_key TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                source TEXT NOT NULL,
                route TEXT NOT NULL,
                PRIMARY KEY (snapshot_id, domain, unit_key)
            );
            CREATE INDEX IF NOT EXISTS idx_build_import_source
                ON build_import_units(snapshot_id, domain, source);
            INSERT OR IGNORE INTO schema_migrations(version) VALUES (3);
            INSERT OR IGNORE INTO schema_migrations(version) VALUES (4);
            CREATE TABLE IF NOT EXISTS agent_assessments (
                id INTEGER PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('agent_verified', 'needs_human_review',
                    'agent_reject_recommended', 'agent_unavailable')),
                payload TEXT NOT NULL,
                assessed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS agent_assessments_candidate
                ON agent_assessments(candidate_id, id);
            CREATE TABLE IF NOT EXISTS agent_stale_evidence (
                candidate_id TEXT PRIMARY KEY,
                detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS agent_imports (
                id INTEGER PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                assessment_id INTEGER NOT NULL REFERENCES agent_assessments(id),
                action TEXT NOT NULL DEFAULT 'import' CHECK(action IN ('import', 'invalidate')),
                reason TEXT,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS agent_imports_candidate ON agent_imports(candidate_id, id);
        """)
        db.execute("BEGIN IMMEDIATE")
        try:
            if "text_sha256" not in {r[1] for r in db.execute("PRAGMA table_info(build_import_units)")}:
                db.execute("ALTER TABLE build_import_units ADD COLUMN text_sha256 TEXT NOT NULL DEFAULT ''")
            db.execute("""CREATE TABLE IF NOT EXISTS build_import_head (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                snapshot_id INTEGER NOT NULL REFERENCES build_import_snapshots(id))""")
            db.execute("""INSERT OR IGNORE INTO build_import_head(singleton, snapshot_id)
                SELECT 1, MAX(id) FROM build_import_snapshots
                WHERE NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version=5)
                HAVING COUNT(*) > 0""")
            db.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (5)")
            db.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (6)")
            columns = {r[1] for r in db.execute("PRAGMA table_info(build_import_snapshots)")}
            if "module" not in columns:
                db.execute("ALTER TABLE build_import_snapshots ADD COLUMN module TEXT")
            db.execute("""CREATE TABLE IF NOT EXISTS module_build_heads (
                module TEXT PRIMARY KEY CHECK(module IN ('Spoken_Quest_UA', 'Spoken_Gossip_UA')),
                snapshot_id INTEGER NOT NULL REFERENCES build_import_snapshots(id))""")
            db.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (7)")
            db.execute("""CREATE TABLE IF NOT EXISTS quest_runtime_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                moment TEXT NOT NULL,
                candidate TEXT NOT NULL,
                evidence TEXT NOT NULL,
                text TEXT NOT NULL,
                decision TEXT NOT NULL CHECK(decision IN ('pending', 'approved', 'withdrawn')),
                reviewer TEXT NOT NULL,
                checks_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            db.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (8)")
            db.commit()
        except BaseException:
            db.rollback()
            raise
        os.chmod(path, 0o600)
        yield db
    finally:
        db.close()


def _memory_versions(db, name, data):
    if name not in ("gossip-translation-reviews.json", "translation-reviews.json"):
        return
    domain = "gossip" if name.startswith("gossip") else "quest"
    # Incremental index: don't rewrite every translation on each decision.
    incoming = {row["id"] for row in data["versions"]}
    # Avoid one SQL bind variable per translation. SQLite builds differ in
    # SQLITE_MAX_VARIABLE_NUMBER, and real history can exceed 32,766 rows.
    known = {row[0] for row in db.execute(
        "SELECT version_id FROM translation_memory WHERE domain = ?", (domain,))}
    stale = sorted(known - incoming)
    if stale:
        db.executemany("DELETE FROM translation_memory WHERE version_id = ?",
                       [(version_id,) for version_id in stale])
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
                row = db.execute("SELECT payload, revision FROM ledger_documents WHERE ledger_name = ?",
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
                    revision = 1
                else:
                    payload, revision = row
                    from adapters.local_review_store import strict_json
                    data = self.validate(strict_json(payload))
                db.commit()
            except BaseException:
                db.rollback()
                raise
        self.baseline, self.revision, self.data = payload, revision, data

    def check_unchanged(self):
        with connection(self.db_path) as db:
            row = db.execute("SELECT payload, revision FROM ledger_documents WHERE ledger_name = ?",
                             (self.name,)).fetchone()
        if row != (self.baseline, self.revision):
            raise ValueError("local_review_conflict_restart_and_reload")

    def save(self, data):
        checked = self.validate(data)
        payload = json.dumps(checked, ensure_ascii=False, sort_keys=True)
        with connection(self.db_path) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT payload, revision FROM ledger_documents WHERE ledger_name = ?",
                                 (self.name,)).fetchone()
                if row != (self.baseline, self.revision):
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
        if payload != self.baseline:
            self.revision += 1
        self.baseline, self.data = payload, checked
        return checked


def backup_database(db_path, destination):
    """Consistent online SQLite snapshot (including schema and all review ledgers)."""
    # Check symlinks before resolving aliases such as directory/../database.
    original = protected_path(db_path).resolve()
    output = protected_path(destination).resolve()
    if not original.is_file():
        raise ValueError("sqlite_backup_source_missing")
    if original == output:
        raise ValueError("sqlite_backup_same_path")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # O_EXCL prevents an existing or concurrently created backup being
    # overwritten. O_NOFOLLOW blocks symlink swaps at the destination.
    try:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        raise ValueError("sqlite_backup_target_already_exists") from None
    except OSError:
        raise ValueError("sqlite_backup_create_failed") from None
    os.close(fd)
    try:
        # Never create a source that disappears after validation, or initialize
        # or migrate the source schema as a side effect of backing it up.
        with (
            closing(sqlite3.connect(original.as_uri() + "?mode=ro", uri=True)) as source,
            closing(sqlite3.connect(output)) as target,
        ):
            source.backup(target)
        os.chmod(output, 0o600)
    except BaseException:
        output.unlink(missing_ok=True)
        raise
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
            # Prefer a unique human-approved wording. If there is none,
            # a unique existing PENDING proposal is reusable as a draft too.
            # Rejected/deferred text and ambiguous conflicts are never reused.
            for review_status in ("approved", "pending"):
                rows = db.execute(
                    """SELECT DISTINCT ukrainian_text FROM translation_memory
                       WHERE domain = ? AND english_sha256 = ?
                         AND review_status = ?""",
                    (domain, english_sha, review_status),
                ).fetchall()
                if rows:
                    if len(rows) == 1:
                        suggestions[english_sha] = rows[0][0]
                    break
    return suggestions
