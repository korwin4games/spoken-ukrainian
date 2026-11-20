"""Read-only Quest evidence compatibility for the audited Spoken 3.9.0 -> 3.10.1 upgrade.

Do not rewrite SQLite approvals/selections or treat a revision change alone
as proof of compatibility. The full Stage 3 source file checksum inventory is
frozen for both commits; all files must match, including the Quest corpus and
its factions and aliases. The active checkout is validated separately by the
existing source reader before Quest evidence is evaluated.
"""
from functools import lru_cache
import json
from pathlib import Path

from adapters.crosswalk import digest

ROOT = Path(__file__).resolve().parents[1]
LEGACY_REVISION = "3c896874e27ec9e07d51a3578c0b9fa8545c9ac7"
CURRENT_REVISION = "db5669b0a39815dd38568f0e871f4ced82bc9229"
QUEST_CORPUS = "pipelines/quests/corpus/corpus.json.gz"
QUEST_FACTIONS = "pipelines/quests/corpus/factions.json"
GOSSIP_ALIASES = "pipelines/quests/corpus/gossip_aliases.json"


@lru_cache(maxsize=1)
def _verified_upgrade():
    """Return the compatible old revision only for this *exact* audited pin pair."""
    current = json.loads((ROOT / "tests/stage3_sources.json").read_text(encoding="utf-8"))
    old = json.loads((ROOT / "tests/stage3_390_sources.json").read_text(encoding="utf-8"))
    pinned = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))
    files = current.get("files")
    if (current.get("revision") != CURRENT_REVISION
            or old.get("revision") != LEGACY_REVISION
            or pinned["spoken"]["revision"] != CURRENT_REVISION
            or not isinstance(files, dict)
            or not all(files.get(path) for path in (QUEST_CORPUS, QUEST_FACTIONS, GOSSIP_ALIASES))
            or files != old.get("files")):
        return None
    return LEGACY_REVISION


def matching_evidence(stored, current):
    """Compare full evidence (including ClassicUA, every ID and every context).

    A historical 3.9.0 decision remains valid for 3.10.1 only when the audited
    source files are byte-identical and the sole difference is Spoken's Git SHA.
    """
    if stored == current:
        return True
    if not isinstance(stored, dict) or not isinstance(current, dict):
        return False
    if current.get("spoken") != CURRENT_REVISION or _verified_upgrade() is None:
        return False
    return stored == {**current, "spoken": LEGACY_REVISION}


def matching_selection(stored_digest, current):
    """Check a stored quick-choice digest, which has no raw historical evidence."""
    if type(stored_digest) is not str or not isinstance(current, dict):
        return False
    if stored_digest == digest(current):
        return True
    if current.get("spoken") != CURRENT_REVISION or _verified_upgrade() is None:
        return False
    return stored_digest == digest({**current, "spoken": LEGACY_REVISION})


def matching_snapshot_revision(stored_revision, active_revision):
    """Preserve only checksum-verified old ZIP imports under the audited upgrade."""
    return (stored_revision == active_revision
            or (stored_revision == LEGACY_REVISION
                and active_revision == CURRENT_REVISION
                and _verified_upgrade() is not None))
