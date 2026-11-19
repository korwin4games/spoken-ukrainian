"""Private local review persistence. Bodies belong only in ignored build output.

Atomic replacement plus an advisory lock and optimistic conflict detection avoid
lost writes between tabs/processes. No authentication or publication is implied.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile


@contextmanager
def file_lock(path, *, blocking=True):
    """Exclusive advisory lock used by the JSON store and private builder."""
    if path.is_symlink():
        raise ValueError("unsafe_local_lock_path")
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "r+b") as handle:
        if path.is_symlink() or not os.path.samestat(path.stat(), os.fstat(fd)):
            raise ValueError("unsafe_local_lock_path")
        if os.name == "nt":
            import errno
            import msvcrt
            try:
                msvcrt.locking(fd, msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                if not blocking and exc.errno == errno.EACCES:
                    raise BlockingIOError from exc
                raise
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        yield


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs)


class LocalFile:
    def __init__(self, path, allowed_directory, empty, validate):
        self.path = Path(path).absolute()
        self.allowed = Path(allowed_directory).resolve()
        self.empty, self.validate = empty, validate
        self._guard()
        self.sqlite = None
        # Only explicitly selected review ledgers move to SQLite. Unrelated
        # local files still use the historical safe JSON storage.
        from adapters.sqlite_translation_store import DB_ENV, LEDGER_NAMES, SQLiteDocument
        db_path = os.environ.get(DB_ENV)
        if db_path and self.path.name in LEDGER_NAMES:
            self.sqlite = SQLiteDocument(db_path, self.path, empty, validate)
            self.baseline, self.data = self.sqlite.baseline, self.sqlite.data
            return
        self.baseline = self._read()
        self.data = validate(strict_json(self.baseline)) if self.baseline is not None else validate(empty)

    def _guard(self):
        if (self.path == self.allowed or not self.path.is_relative_to(self.allowed)
                or any(p.is_symlink() for p in (self.path, *self.path.parents))
                or not self.path.resolve().is_relative_to(self.allowed)):
            raise ValueError("local_review_path_must_be_under_build_without_symlinks")

    def _read(self):
        self._guard()
        return self.path.read_text(encoding="utf-8") if self.path.exists() else None

    def check_unchanged(self):
        if self.sqlite is not None:
            return self.sqlite.check_unchanged()
        if self._read() != self.baseline:
            raise ValueError("local_review_conflict_restart_and_reload")

    @contextmanager
    def locked(self):
        self._guard()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = self.path.with_name(self.path.name + ".lock")
        with file_lock(lock):
            self.check_unchanged()
            yield

    def save(self, data):
        if self.sqlite is not None:
            checked = self.sqlite.save(data)
            self.baseline, self.data = self.sqlite.baseline, checked
            return checked
        checked = self.validate(data)
        content = json.dumps(checked, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with self.locked():
            if content != self.baseline:
                name = None
                try:
                    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent,
                                                     prefix=".review-", delete=False) as out:
                        name = out.name
                        os.chmod(name, 0o600)
                        out.write(content)
                        out.flush()
                        os.fsync(out.fileno())
                    self._guard()
                    os.replace(name, self.path)
                    if hasattr(os, "O_DIRECTORY"):
                        directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                        try:
                            os.fsync(directory)
                        finally:
                            os.close(directory)
                finally:
                    if name and os.path.exists(name):
                        os.unlink(name)
            self.baseline, self.data = content, checked
        return checked
