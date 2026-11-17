#!/usr/bin/env python3
"""Opt-in, one-batch Codex translator. Drafts only; NEVER approves or imports.

Codex runs read-only and returns schema-constrained JSON into ignored build/.
The Python driver validates exact pinned group identities and source integrity,
preserves existing drafts, and only fills previously blank Ukrainian fields.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.local_review_store import strict_json

BUILD = ROOT / "build"
QUEUE = BUILD / "gossip-translation-queue.json"
TOKENS = re.compile(r"\$[A-Za-z][A-Za-z0-9]*|<(?:(?:name|class|race|gender|player|npc|"
                    r"Name|Class|Race|Gender)|[^<>\n]{0,30}:[^<>\n]{0,50})>"
                    r"|\{[^{}\n]{1,100}\}|\|[cC][0-9a-fA-F]{8}|\|[rR]")
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "group_id": {"type": "string"},
                    "ukrainian_text": {"type": "string"},
                },
                "required": ["group_id", "ukrainian_text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["translations"],
    "additionalProperties": False,
}


def under_private_build(path):
    path = Path(path).absolute()
    base = BUILD.resolve()
    if path == base or not path.is_relative_to(base):
        raise ValueError("gossip_codex_path_must_be_under_private_build")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("unsafe_gossip_codex_symlink")
    if not path.resolve().is_relative_to(base):
        raise ValueError("unsafe_gossip_codex_path")
    return path


def pending_rows(batch, queue, lock):
    if (type(batch) is not dict or set(batch) !=
            {"schema_version", "spoken_revision", "classicua_revision", "entries"}
            or batch["schema_version"] != 1
            or type(batch["entries"]) is not list
            or not 0 < len(batch["entries"]) <= 100
            or type(queue) is not dict
            or type(queue.get("groups")) is not list
            or type(lock) is not dict):
        raise ValueError("invalid_gossip_codex_batch")
    if (batch["spoken_revision"] != lock["spoken"]["revision"]
            or batch["classicua_revision"] != lock["classicua"]["revision"]
            or queue.get("spoken_revision") != batch["spoken_revision"]
            or queue.get("classicua_revision") != batch["classicua_revision"]):
        raise ValueError("stale_gossip_codex_source_revisions")
    groups = {g["group_id"]: g for g in queue["groups"]}
    if len(groups) != len(queue["groups"]):
        raise ValueError("duplicate_gossip_codex_queue_groups")
    missing, seen = [], set()
    for item in batch["entries"]:
        if (type(item) is not dict or set(item) !=
                {"group_id", "english_sha256", "context_sha256", "english_original",
                 "occurrence_count", "ukrainian_text"}):
            raise ValueError("invalid_gossip_codex_entry")
        key = item["group_id"]
        group = groups.get(key) if type(key) is str else None
        if key in seen or group is None or any((
                item["english_sha256"] != group["english_sha256"],
                item["context_sha256"] != group["context_sha256"],
                item["english_original"] != group["english"],
                item["occurrence_count"] != group["occurrence_count"])):
            raise ValueError("stale_or_duplicate_gossip_codex_context")
        seen.add(key)
        if type(item["ukrainian_text"]) is not str:
            raise ValueError("invalid_gossip_codex_existing_draft")
        if not item["ukrainian_text"].strip():
            missing.append({
                "group_id": key, "english_original": item["english_original"],
                "npc_contexts": [{
                    "npc_id": c["npc_id"], "npc_name": c["npc_name"]
                } for c in group["contexts"]],
            })
    return missing


def prompt_for_rows(rows):
    return (
        "Return strictly a JSON object matching the supplied output schema. "
        "Translate exactly these World of Warcraft: Forever English NPC Gossip "
        "utterances into natural Ukrainian. Do not use Russian localization. "
        "Preserve game variables ($N, <name>, {tokens}), formatting, "
        "semantic meaning and Ukrainian proper nouns. Translation must suit "
        "ALL listed NPCs, including any gender. If uncertain, set ukrainian_text "
        "to an empty string for human handling; do not invent context. "
        "Each input group_id must occur exactly once in translations. "
        "Do not edit source files, call external tools, or claim human approval.\n\n"
        + json.dumps({"entries": rows}, ensure_ascii=False, sort_keys=True)
    )


def accepted_translations(rows, reply):
    if type(reply) is not dict or set(reply) != {"translations"} \
            or type(reply["translations"]) is not list:
        raise ValueError("invalid_gossip_codex_response_schema")
    expected = {x["group_id"]: x for x in rows}
    received = {}
    for r in reply["translations"]:
        if type(r) is not dict or set(r) != {"group_id", "ukrainian_text"}:
            raise ValueError("invalid_gossip_codex_response_fields")
        group, text = r["group_id"], r["ukrainian_text"]
        if (type(group) is not str or group not in expected or group in received
                or type(text) is not str or len(text) > 60000):
            raise ValueError("unexpected_gossip_codex_translation")
        if text.strip():
            if Counter(TOKENS.findall(expected[group]["english_original"])) \
                    != Counter(TOKENS.findall(text)):
                raise ValueError("gossip_codex_placeholder_mismatch")
            if any(ord(x) < 32 and x not in "\n\r\t" for x in text):
                raise ValueError("invalid_gossip_codex_control_character")
        received[group] = text
    if set(received) != set(expected):
        raise ValueError("incomplete_gossip_codex_result")
    return received


def apply_to_batch(batch, translations):
    result = json.loads(json.dumps(batch, ensure_ascii=False))
    filled = 0
    for row in result["entries"]:
        translation = translations.get(row["group_id"])
        if translation and not row["ukrainian_text"].strip():
            row["ukrainian_text"] = translation
            filled += 1
    return result, filled


def translate(batch_path, apply=False, executable="codex", runner=None):
    path = under_private_build(batch_path)
    original = path.read_bytes()
    if len(original) > 2_000_000:
        raise ValueError("gossip_codex_input_too_large")
    batch = strict_json(original.decode("utf-8"))
    queue_path = under_private_build(QUEUE)
    queue = strict_json(queue_path.read_text(encoding="utf-8"))
    lock = strict_json((ROOT / "sources.lock.json").read_text(encoding="utf-8"))
    rows = pending_rows(batch, queue, lock)
    if not rows:
        return {"pending": 0, "translated_now": 0, "skipped": 0, "applied": False}
    if not apply:
        return {"pending": len(rows), "translated_now": 0, "skipped": 0, "applied": False}
    if runner is None and not shutil.which(executable):
        raise ValueError("codex_cli_not_installed_or_unavailable")
    BUILD.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gossip-codex-", dir=BUILD) as temp:
        schema_path = Path(temp) / "schema.json"
        message_path = Path(temp) / "result.json"
        schema_path.write_text(json.dumps(RESPONSE_SCHEMA), encoding="utf-8")
        cmd = [executable, "exec", "--sandbox", "read-only",
               "--output-schema", str(schema_path), "--output-last-message",
               str(message_path), "-"]
        if runner is None:
            outcome = subprocess.run(
                cmd, input=prompt_for_rows(rows), text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=ROOT, timeout=900, check=False)
        else:
            outcome = runner(cmd, prompt_for_rows(rows), message_path)
        if outcome.returncode:
            raise ValueError("codex_gossip_translation_failed")
        if not message_path.is_file() or message_path.stat().st_size > 1_000_000:
            raise ValueError("missing_or_oversized_gossip_codex_response")
        reply = strict_json(message_path.read_text(encoding="utf-8"))
        translations = accepted_translations(rows, reply)
        updated, count = apply_to_batch(batch, translations)
        if path.read_bytes() != original:
            raise ValueError("gossip_codex_batch_changed_during_translation")
        if count:
            # Atomic local replacement; only blank fields change.
            with tempfile.NamedTemporaryFile(
                    "w", encoding="utf-8", dir=path.parent, prefix=".gossip-draft-",
                    delete=False) as output:
                temp_path = Path(output.name)
                try:
                    os.chmod(temp_path, 0o600)
                    json.dump(updated, output, ensure_ascii=False, indent=2)
                    output.write("\n")
                    output.flush()
                    os.fsync(output.fileno())
                except BaseException:
                    temp_path.unlink(missing_ok=True)
                    raise
            try:
                if path.read_bytes() != original:
                    raise ValueError("gossip_codex_batch_changed_during_translation")
                under_private_build(path)
                os.replace(temp_path, path)
            finally:
                temp_path.unlink(missing_ok=True)
        return {"pending": len(rows), "translated_now": count,
                "skipped": len(rows) - count, "applied": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path,
                        help="ONE ignored build/gossip-batches/batch-NNNN.json file")
    parser.add_argument("--apply", action="store_true",
                        help="Explicitly invoke Codex and use its output; may consume model quota")
    args = parser.parse_args(argv)
    try:
        report = translate(args.input, apply=args.apply)
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError,
            UnicodeError, subprocess.TimeoutExpired) as err:
        # Do not print raw user/model text, prompts, credentials or stderr.
        value = str(err)
        reason = value if re.fullmatch("[a-z0-9_]{2,90}", value) else type(err).__name__
        print("gossip_codex_failed:", reason, file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    print("DRAFT ONLY. Review all Ukrainian proposals and every NPC context; "
          "no approval, import, audio or release was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
