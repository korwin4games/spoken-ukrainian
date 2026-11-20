"""Incremental private Quest ZIP: preserve prior imported moments verbatim.

The existing Quest ZIP is authoritative for already published Quest ID/event
texts. Only the manager's current 'ready_to_import' moments may be added or
replaced. This never changes Gossip packs or the provenance of retained units.
"""
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

from adapters.spoken import literal_data
from adapters.sqlite_translation_store import connection
from tools.quest_source_compatibility import matching_snapshot_revision


EVENTS = ("accept", "progress", "complete")
FIELDS = ("title", "objective")
ASSIGNMENT = b"\nSpokenUkrainian.QuestTranslations = "


def previous_snapshot(db_path, archive, spoken_revision, classicua_revision):
    """Read a verifiable previous ZIP with its exact per-moment build metadata."""
    archive = Path(archive)
    with connection(db_path) as db:
        record = db.execute("""SELECT s.id, s.artifact_sha256, s.spoken_revision,
            s.classicua_revision FROM module_build_heads h
            JOIN build_import_snapshots s ON s.id = h.snapshot_id
            WHERE h.module = 'Spoken_Quest_UA' AND s.module = h.module""").fetchone()
        if record is None:
            if archive.exists() or archive.is_symlink():
                raise ValueError("manager_quest_existing_zip_untracked")
            return {}, {}
        snapshot_id, checksum, spoken, classicua = record
        rows = {(key, domain): (source, route, fingerprint)
                for domain, key, source, route, fingerprint in db.execute(
                    """SELECT domain, unit_key, source, route, text_sha256
                       FROM build_import_units WHERE snapshot_id=?""", (snapshot_id,))}
    if (not matching_snapshot_revision(spoken, spoken_revision) or classicua != classicua_revision
            or not archive.is_file() or archive.is_symlink()
            or sha256(archive.read_bytes()).hexdigest() != checksum):
        raise ValueError("manager_quest_existing_zip_changed")
    try:
        with ZipFile(archive) as bundle:
            raw = bundle.read("Spoken_Quest_UA/Translations.lua")
        _, marker, body = raw.partition(ASSIGNMENT)
        if not marker:
            raise ValueError("manager_quest_existing_zip_invalid")
        parsed = literal_data(b"SpokenUkrainian.QuestTranslations = " + body,
                              "SpokenUkrainian.QuestTranslations")
    except (OSError, KeyError, UnicodeError, ValueError, TypeError) as exc:
        raise ValueError("manager_quest_existing_zip_invalid") from None
    if type(parsed) is not dict:
        raise ValueError("manager_quest_existing_zip_invalid")
    previous = {}
    found = set()
    for quest, record in parsed.items():
        if type(quest) is not int or quest <= 0 or type(record) is not dict:
            raise ValueError("manager_quest_existing_zip_invalid")
        row = {}
        for field in FIELDS:
            if field in record:
                if type(record[field]) is not str:
                    raise ValueError("manager_quest_existing_zip_invalid")
                row[field] = record[field]
        for event in EVENTS:
            if event not in record:
                continue
            entry = record[event]
            key = f"{quest}:{event}"
            provenance = rows.get((key, "quests"))
            if (type(entry) is not dict or type(entry.get("text")) is not str
                    or type(entry.get("reviewed")) is not bool
                    or type(entry.get("quick", False)) is not bool
                    or provenance is None
                    or sha256(entry["text"].encode("utf-8")).hexdigest() != provenance[2]):
                raise ValueError("manager_quest_existing_zip_invalid")
            found.add(key)
            row[event] = dict(entry, preserved_source=provenance[0],
                              preserved_route=provenance[1])
        previous[quest] = row
    expected = {key for key, domain in rows if domain == "quests"}
    if found != expected:
        raise ValueError("manager_quest_existing_zip_invalid")
    return previous, rows


def merge_ready(previous, generated, ready):
    """Carry all imported Quest texts, replacing only explicit ready moments."""
    merged = {quest: {key: value.copy() if isinstance(value, dict) else value
                      for key, value in events.items()}
              for quest, events in previous.items()}
    missing = []
    for moment in sorted(ready):
        parts = moment.split(":")
        if (len(parts) != 3 or parts[0] != "q" or
                parts[1].strip("0123456789") or int(parts[1]) < 1 or
                parts[2] not in EVENTS):
            raise ValueError("manager_invalid_quest_ready_selection")
        quest, event = int(parts[1]), parts[2]
        value = generated.get(quest, {}).get(event)
        if type(value) is not dict or type(value.get("text")) is not str:
            missing.append(moment)
            continue
        target = merged.setdefault(quest, {})
        target[event] = dict(value)
        for key in FIELDS:
            if key not in target and type(generated.get(quest, {}).get(key)) is str:
                target[key] = generated[quest][key]
    if missing:
        raise ValueError("manager_quest_ready_translation_missing")
    return merged
