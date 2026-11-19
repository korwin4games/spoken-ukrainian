#!/usr/bin/env bash
set -euo pipefail

case "${1:-tests}" in
    tests|db-status) ;;
    *) echo "Expected tests or db-status." >&2; exit 2 ;;
esac

if [[ ! -f /input/source.tar ]]; then
    echo "Mount a Git source archive at /input/source.tar." >&2
    exit 1
fi

mkdir /workspace/spoken-ukrainian
tar -xf /input/source.tar -C /workspace/spoken-ukrainian
cd /workspace/spoken-ukrainian
uv sync --locked

if [[ ${1:-tests} == db-status ]]; then
    : "${SPOKEN_TRANSLATION_DB:?Set SPOKEN_TRANSLATION_DB to the mounted database path.}"
    exec uv run --locked python tools/translation_db.py status
fi
unset SPOKEN_TRANSLATION_DB

revision=$(uv run --locked python -c '
import json
from pathlib import Path
import re

revision = json.loads(Path("sources.lock.json").read_text(encoding="utf-8"))["spoken"]["revision"]
if not re.fullmatch(r"[0-9a-f]{40}", revision):
    raise SystemExit("Invalid Spoken revision in sources.lock.json")
print(revision)
')
git config --global --add safe.directory "$SPOKEN_SOURCE"
if [[ $(git -C "$SPOKEN_SOURCE" rev-parse HEAD) != "$revision" ]]; then
    echo "Mount a Spoken checkout at /input/spoken-wow matching sources.lock.json." >&2
    exit 1
fi

uv run --locked python tools/version.py check
uv run --locked python tools/build.py
node --test tests/manager_frontend.test.cjs
uv run --locked python -m unittest discover -s tests -v
