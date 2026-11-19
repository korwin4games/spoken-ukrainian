"""Verified English originals for the public, pinned Spoken target inventory.

Original wording exists in the pinned Quests/Gossip corpus and Readables pages.
The canonical inventory intentionally does not export text bodies. Keep these
texts *in memory only*, and use them only after checking the pinned inventory's
stored wording digests. Places/Bosses are excluded until original story text
is verified under a separately reviewed public input contract.
"""
from dataclasses import dataclass, field
from collections import Counter
import gzip
import json

from adapters.crosswalk import TARGET_PATTERNS, digest, quest_moment
from adapters.spoken import literal_data


@dataclass(frozen=True)
class TextIndex:
    original_english: dict
    unresolved: tuple
    families: dict
    variants: dict = field(default_factory=dict)

    def metadata(self):
        return {
            "indexed_with_verified_original_english": len(self.original_english),
            "unresolved_public_original": len(self.unresolved),
            "families": self.families,
        }


def ambiguous_quest_moments(index):
    return {quest_moment(identity) for identity, variants in getattr(index, "variants", {}).items()
            if TARGET_PATTERNS["quest"].fullmatch(identity) and len(variants) > 1}


def index_verified_originals(reader, inventory, *, corpus=None):
    """Find actual public originals, with no fabricated text or guessed joins.

    The reader is a pinned PublicSource in production. Its read() independently
    validates the file SHA-256; the inventory ties canonical IDs and evidence.
    """
    observed = {}

    def add(identity, family, text):
        target = inventory.targets.get(identity)
        if target is None or target.family != family or type(text) is not str or not text:
            return
        word_sha = digest(text)
        # Some IDs have multiple variants. Every accepted wording must occur in
        # the actual pinned target context. Different verified wordings remain
        # ambiguous rather than selecting an arbitrary original.
        if not any(context.get("wording_sha256") == word_sha
                   for context in inventory.contexts.get(identity, ())):
            raise ValueError("public_original_context_mismatch")
        observed.setdefault(identity, set()).add(text)

    path = "pipelines/quests/corpus/corpus.json.gz"
    if corpus is None:
        corpus = json.loads(gzip.decompress(reader.read(path)))
    for row in corpus["lines"]:
        source = row["source"]
        if source in ("accept", "progress", "complete", "gossip"):
            add(row["lineId"], "gossip" if source == "gossip" else "quest",
                row.get("originalText"))

    books = literal_data(reader.read("addons/Spoken_Readables/Data/Books.lua"),
                         "SpokenReadablesData")
    for page, row in books["pages"].items():
        add(f"b:{page}", "readable", row.get("text"))

    originals = {identity: next(iter(values)) for identity, values in sorted(observed.items())
                 if len(values) == 1}
    unresolved = tuple(sorted(set(inventory.targets) - set(originals)))
    families = {}
    for identity, target in sorted(inventory.targets.items()):
        family = target.family
        counter = families.setdefault(family, {"total": 0, "with_original": 0,
                                               "without_verified_original": 0})
        counter["total"] += 1
        counter["with_original" if identity in originals else "without_verified_original"] += 1
    if len(originals) + len(unresolved) != len(inventory.targets):
        raise ValueError("original_index_total_mismatch")
    return TextIndex(originals, unresolved, dict(sorted(families.items())),
                     {identity: tuple(sorted(words)) for identity, words in sorted(observed.items())})
