"""Priority for verified Gossip greetings, independent of source acquisition."""
from collections import defaultdict

PRIORITY = ("ua_forever", "classicua")
UA_REVISION = "0bbc033be68b6e48b098f0891eaca1b974b2d954"
UA_GOSSIP_PATH = "entries/forever/cliend_db/gossip.lua"
UA_GOSSIP_SHA256 = "c82bb04345aefee86cc43020ccd7c092344c3863df5d87455e269bf4e3565db5"

EXPLICIT = "explicit_selection"
PRIORITY_WIN = "higher_priority_provider"
IDENTICAL = "identical_provider_translations"
UNIQUE = "unique_provider_candidate"
FALLBACK = "classicua_fallback"
AMBIGUOUS = "provider_ambiguous"
ENGLISH = "english_fallback"
STALE = "stale_selection"
UNSAFE = "unsafe_context"


def load_ua_forever_candidates(state):
    """Return eligible pinned input only after documented rights and attribution.

    Production has no UA Forever adapter or authorization. A subsequent adapter
    must enforce the documented grant and verify blobs before supplying records.
    Synthetic tests substitute this acquisition boundary.
    """
    return {}


def resolve_provider(choices, *, ambiguous=()):
    """Choose the first provider with one distinct eligible translation."""
    by_provider = defaultdict(dict)
    for choice in choices:
        if choice["provider"] in PRIORITY:
            by_provider[choice["provider"]].setdefault(choice["sha256"], choice)
    for provider in PRIORITY:
        offered = by_provider[provider]
        if provider in ambiguous or len(offered) > 1:
            return None, provider, AMBIGUOUS
        if offered:
            fingerprint, choice = next(iter(offered.items()))
            lower = by_provider["classicua"] if provider == "ua_forever" else {}
            if set(lower) - {fingerprint}:
                reason = PRIORITY_WIN
            elif fingerprint in lower:
                reason = IDENTICAL
            else:
                reason = FALLBACK if provider == "classicua" else UNIQUE
            return choice, provider, reason
    return None, "original_english", ENGLISH


def provenance(choice):
    return {key: choice[key] for key in ("provider", "revision", "reference", "file_sha256", "sha256")
            if choice.get(key) is not None}


def deduplicate(choices, preferred):
    by_text = defaultdict(list)
    for choice in choices:
        by_text[choice["sha256"]].append(choice)
    result = []
    for duplicates in by_text.values():
        representative = preferred if preferred in duplicates else duplicates[0]
        origins = [provenance(choice) for choice in duplicates]
        result.append(representative | {"provenance": origins})
    return result
