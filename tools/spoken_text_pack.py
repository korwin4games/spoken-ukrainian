"""Private, text-only Spoken 3.10.1 export from verified Ukrainian selections.

Spoken line IDs are shared across NPCs and wording variants. Native client
Quest/Gossip translation keys are NOT interchangeable with Spoken line IDs.
Never export a translation without a safe canonical identity and context.
"""
from collections import defaultdict
import re

QUEST_PARTS = ("accept", "progress", "complete")
QUEST_ID = re.compile(r"q:([1-9][0-9]*):(accept|progress|complete)(?::.*)?\Z")
GOSSIP_ID = re.compile(r"g:(?:[0-9a-f]{32}|b[0-9]+-[A-Za-z0-9_-]+|[a-z]{2}[A-Z]{2}-[0-9a-f]+)\Z")
CODE = re.compile(r"\{([^{}]+)\}")
TOKEN = re.compile(r"\$[A-Za-z]")
GENDER_TOKEN = re.compile(r"\$G([^:;{}]+):([^:;{}]+);")
PLAYER_CODES = {
    "ім'я": "$N", "Ім'я": "$N",
    "клас": "$C", "Клас": "$C",
    "раса": "$R", "Раса": "$R",
}


def text_pack_words(value):
    """Convert safe local placeholders, rejecting unsupported grammatical cases.

    The public Spoken text API expects Blizzard player tokens, not the local
    declined forms expanded by Spoken_Ukrainian for native quest frames.
    """
    if type(value) is not str or not value.strip() or len(value) > 60000:
        return None
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value):
        return None

    def replace(match):
        code = match.group(1)
        if code in PLAYER_CODES:
            return PLAYER_CODES[code]
        if code.startswith("стать:"):
            branches = code.split(":")
            if (len(branches) == 3 and all(branches[1:])
                    and not any(c in branches[1] + branches[2] for c in ";{}$")):
                return "$G" + branches[1] + ":" + branches[2] + ";"
        raise ValueError("unsupported_text_pack_placeholder")

    try:
        result = CODE.sub(replace, value)
    except ValueError:
        return None
    if "{" in result or "}" in result:
        return None
    # Never publish an unknown/malformed player token; validate each $G's
    # complete branches rather than accepting a stray $G.
    genders = list(GENDER_TOKEN.finditer(result))
    if len(genders) != sum(m[0] == "$G" for m in TOKEN.finditer(result)):
        return None
    if any(m[0] not in ("$N", "$C", "$R", "$B", "$G") for m in TOKEN.finditer(result)):
        return None
    return result


def quest_source_moments(state):
    """List every audited English wording for each Quest ID/event.

    The native Quest preview only selects by ID/event and cannot prove an
    individual -wN or gendered file. More than one wording blocks the base
    Spoken key instead of translating an unrelated voice/wording variant.
    """
    result = defaultdict(set)
    index = state.original_index
    targets = getattr(state.inventory, "targets", None)
    if not isinstance(targets, dict):
        return result  # Synthetic/incomplete state: never infer canonical IDs.
    for target, item in targets.items():
        if item.family != "quest":
            continue
        match = QUEST_ID.fullmatch(target)
        if not match:
            continue
        options = index.variants.get(target, ()) if hasattr(index, "variants") else ()
        if not options:
            options = (index.original_english.get(target),)
        for text in options:
            if type(text) is str and text.strip():
                result[int(match[1]), match[2]].add(text)
    return result


def quest_payload(preview, *, source_moments=None, faction_titles=None):
    """Use only unambiguous, pinned, event-scoped Quest translations.

    The full Spoken corpus is checked before emitting a *base* q:ID:event key.
    Without per-wording proofs, never guess -wN or :m/:f targets. The official
    runtime tries :m/:f and then the base key automatically.
    """
    titles, lines = {}, {}
    for quest, data in sorted(preview.items()):
        if type(quest) is not int or quest < 1 or type(data) is not dict:
            raise ValueError("invalid_quest_text_pack_data")
        if not any(part in data for part in QUEST_PARTS):
            continue
        candidates = set()
        if isinstance(data.get("title"), str) and data["title"].strip():
            candidates.add(data["title"])
        for titles_for_faction in (faction_titles or {}).values():
            title = titles_for_faction.get(quest)
            if type(title) is str and title.strip():
                candidates.add(title)
        # Never mix faction-specific conflicting titles into one global ID.
        if len(candidates) == 1:
            title = text_pack_words(next(iter(candidates)))
            if title:
                titles[quest] = title
        for part in QUEST_PARTS:
            row = data.get(part)
            if type(row) is not dict:
                continue
            if source_moments is not None and len(source_moments.get((quest, part), ())) != 1:
                continue
            text = text_pack_words(row.get("text"))
            if text:
                lines[f"q:{quest}:{part}"] = text
    return titles, lines


def gossip_payload(rows, *, corpus_lines=None):
    """Export a shared canonical g: key only when *every* context is safe.

    A verified native NPC/hash selection is not automatically a global Spoken
    translation. In particular, a second untranslated NPC must block the key.
    """
    grouped = defaultdict(list)
    for row in rows:
        for context in row.get("contexts", ()):
            key = context.get("lineId")
            if type(key) is str and GOSSIP_ID.fullmatch(key):
                grouped[key].append((row, context))

    # Cross-check against the complete pinned corpus, including unsupported
    # gameobject/non-NPC contexts which the native editor never lists.
    expected, blocked = defaultdict(set), set()
    if corpus_lines is not None:
        from tools.gossip_coverage import classicua_hash
        for line in corpus_lines:
            if line.get("source") != "gossip":
                continue
            key = line.get("lineId")
            if type(key) is not str or not GOSSIP_ID.fullmatch(key):
                continue
            npc, english = line.get("npcId"), line.get("originalText")
            hashed = classicua_hash(english)
            if (line.get("npcType") not in ("creature", "vehicle") or
                    type(npc) is not int or npc <= 0 or not hashed):
                blocked.add(key)
                continue
            expected[key].add((npc, hashed, english, line.get("npcType"),
                               line.get("voice"), line.get("playerGender")))

    exported = {}
    for key, entries in sorted(grouped.items()):
        if key in blocked:
            continue
        actual = {(row.get("npc_id"), row.get("english_hash"), context.get("originalText"),
                   context.get("npcType"), context.get("voice"), context.get("playerGender"))
                  for row, context in entries}
        if corpus_lines is not None and actual != expected.get(key, set()):
            continue
        originals = {context.get("originalText") for _, context in entries}
        if len(originals) != 1 or not all(type(text) is str and text.strip() for text in originals):
            continue
        choices = set()
        for row, context in entries:
            if (not row.get("review_binding") or row.get("status") == "stale"
                    or context.get("originalText") not in row.get("originals", ())
                    or not row.get("selection")):
                break
            text = text_pack_words(row["selection"].get("text"))
            if text is None:
                break
            choices.add(text)
        else:
            if len(choices) == 1:
                exported[key] = next(iter(choices))
    return exported


def render_spoken_text_pack(titles=None, lines=None):
    """Render a public API registration. Never register voice or audio data."""
    from tools.build_ukrainian import lua_quote

    sections = []
    for name, values in (("titles", titles or {}), ("lines", lines or {})):
        sections.append("    " + name + " = {")
        for key, value in sorted(values.items(), key=lambda item: str(item[0])):
            if type(key) is int and key > 0:
                serialized = f"[{key}]"
            elif type(key) is str and (
                    QUEST_ID.fullmatch(key) or GOSSIP_ID.fullmatch(key) or
                    re.fullmatch(r"f:[A-Za-z0-9_:-]+", key)):
                serialized = "[" + lua_quote(key) + "]"
            else:
                raise ValueError("invalid_spoken_text_pack_id")
            if type(value) is not str or not value.strip():
                raise ValueError("invalid_spoken_text_pack_value")
            sections.append(f"        {serialized} = {lua_quote(value)},")
        sections.append("    },")
    return ("-- GENERATED private local-test text pack. No voice files, no human approval.\n"
            "if SpokenUkrainian and SpokenUkrainian.RegisterTextPack then\n"
            "    SpokenUkrainian:RegisterTextPack(\"quests\", {\n"
            + "\n".join(sections) + "\n    })\nend\n").encode("utf-8")
