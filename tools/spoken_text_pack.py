"""Private Spoken 3.10.1 text-pack export for existing audited Quest and Gossip choices.

Text packs are independent of audio. The runtime text language is selected in
Spoken settings; none of these candidates imply human approval or publication.
"""
from collections import defaultdict
import re

QUEST_PARTS = ("accept", "progress", "complete")
CODE = re.compile(r"\\{([^{}]+)\\}")
PLAYER_CODES = {
    "ім'я": "$N",
    "клас": "$C",
    "раса": "$R",
}


def text_pack_words(value):
    """Convert only supported local placeholders to Spoken's native player tokens.

    Inflected cases cannot be represented by Spoken's $N/$C/$R tokens.
    Reject these rather than displaying raw {..} in Compendium.
    """
    if type(value) is not str or not value.strip():
        return None

    def replace(match):
        code = match.group(1)
        if code in PLAYER_CODES:
            return PLAYER_CODES[code]
        if code.startswith("стать:"):
            branches = code.split(":")
            if (len(branches) == 3 and all(branches[1:]) and
                    not any(ch in branches[1] + branches[2] for ch in ";{}")):
                return "$G" + branches[1] + ":" + branches[2] + ";"
        raise ValueError("unsupported_text_pack_placeholder")

    try:
        result = CODE.sub(replace, value)
    except ValueError:
        return None
    if "{" in result or "}" in result:
        return None
    return result


def quest_payload(preview):
    """Use Quest IDs and vetted, unambiguous imported moment values."""
    titles, lines = {}, {}
    for quest, data in sorted(preview.items()):
        if type(quest) is not int or quest < 1 or type(data) is not dict:
            raise ValueError("invalid_quest_text_pack_data")
        if not any(part in data for part in QUEST_PARTS):
            continue
        if title := text_pack_words(data.get("title")):
            titles[quest] = title
        for part in QUEST_PARTS:
            row = data.get(part)
            if type(row) is not dict:
                continue
            text = text_pack_words(row.get("text"))
            if text:
                lines[f"q:{quest}:{part}"] = text
    return titles, lines


def gossip_payload(rows):
    """Project canonical Spoken gossip IDs, excluding competing NPC translations.

    Unlike ClassicUA's NPC/32-bit hash runtime key, Spoken's line ID is
    canonical across NPCs. A conflict at that ID blocks the text-pack entry.
    """
    by_id = defaultdict(set)
    for row in rows:
        if row.get("status") == "stale" or not row.get("selection"):
            continue
        selection = row["selection"]
        text = text_pack_words(selection.get("text"))
        if not text:
            continue
        for context in row.get("contexts", ()):
            key = context.get("lineId")
            if type(key) is str and key.startswith("g:"):
                by_id[key].add(text)
    return {key: next(iter(texts)) for key, texts in sorted(by_id.items()) if len(texts) == 1}


def render_spoken_text_pack(titles=None, lines=None):
    """Generate a guarded text-only registration for official Spoken 3.10.1."""
    from tools.build_ukrainian import lua_quote

    sections = []
    for name, values in (("titles", titles or {}), ("lines", lines or {})):
        sections.append("    " + name + " = {")
        for key, value in sorted(values.items(), key=lambda item: str(item[0])):
            if type(key) is int:
                serialized = f"[{key}]"
            elif type(key) is str and re.fullmatch(r"[qgf]:[A-Za-z0-9_:\\-]+", key):
                serialized = "[" + lua_quote(key) + "]"
            else:
                raise ValueError("invalid_spoken_text_pack_id")
            if type(value) is not str or not value.strip():
                raise ValueError("invalid_spoken_text_pack_value")
            sections.append(f"        {serialized} = {lua_quote(value)},")
        sections.append("    },")
    return ("-- GENERATED private local-test text pack. No voice files, no human approval.\\n"
            "if SpokenUkrainian and SpokenUkrainian.RegisterTextPack then\\n"
            "    SpokenUkrainian:RegisterTextPack(\\\"quests\\\", {\\n"
            + "\\n".join(sections) + "\\n    })\\nend\\n").encode("utf-8")
