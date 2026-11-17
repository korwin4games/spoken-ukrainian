"""Private local review persistence. Bodies belong only in ignored build output.

Atomic replacement plus an advisory lock and optimistic conflict detection avoid
lost writes between tabs/processes. No authentication or publication is implied.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile


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
        if self._read() != self.baseline:
            raise ValueError("local_review_conflict_restart_and_reload")

    @contextmanager
    def locked(self):
        self._guard()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = self.path.with_name(self.path.name + ".lock")
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            self.check_unchanged()
            yield

    def save(self, data):
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
