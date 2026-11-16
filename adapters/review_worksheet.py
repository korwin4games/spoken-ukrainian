"""Metadata-only, spreadsheet-safe Quest identity-review worksheet.

A worksheet is a review aid, never trusted evidence and never an approval file.
It contains no English or Ukrainian content bodies, only the same pinned source
and target metadata already exposed by the Stage 4B review queue.
"""
import csv
from io import StringIO


COLUMNS = (
    "source_id", "target_id", "source_revision", "spoken_revision",
    "source_reference", "source_blob_sha256", "source_field_sha256",
    "source_context_sha256", "target_reference", "target_blob_sha256",
    "target_context_sha256", "candidate_reason",
    "quest_id", "event", "npc_id", "npc_type", "voice", "faction",
    "player_gender", "wording_sha256",
    "manual_decision", "manual_reason",
    "review_check", "human_notes",
)


def _cell(value):
    """Prevent CSV formula injection in common spreadsheet clients."""
    if value is None:
        return ""
    if type(value) not in (str, bool, int, float):
        raise ValueError("unsupported_worksheet_cell")
    text = str(value)
    if text and (text[0] in "=+-@" or text[0] in "\t\r\n"):
        return "'" + text
    return text


def worksheet_csv(report):
    """One row for each source/target/voice variant in the current review page.

    This exporter MUST NOT infer a real approved mapping from matching IDs.
    It may read only the metadata-only Stage 4B queue created from pinned inputs.
    """
    if (type(report) is not dict or report.get("schema_version") != 1
            or report.get("family") != "quest"
            or report.get("scope") !=
            "Stage 4B metadata-only human review workbench; NO automatic mappings"
            or type(report.get("queue")) is not list
            or report.get("summary", {}).get("new_identity_approvals_created") != 0
            or report.get("summary", {}).get("translation_content_approvals_created") != 0):
        raise ValueError("stage4b_metadata_only_report_required")
    io = StringIO(newline="")
    writer = csv.DictWriter(io, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for record in report["queue"]:
        if type(record) is not dict or record.get("status") != "identity_review_required":
            raise ValueError("unreviewed_quest_record_required")
        for option in record["target_options"]:
            if type(option) is not dict or not option.get("variants"):
                raise ValueError("target_variant_evidence_required")
            for variant in option["variants"]:
                if type(variant) is not dict:
                    raise ValueError("invalid_target_variant")
                fields = {
                    "source_id": record["source_id"],
                    "target_id": option["target_id"],
                    "source_revision": record["source_revision"],
                    "spoken_revision": report["spoken_revision"],
                    "source_reference": record["source_reference"],
                    "source_blob_sha256": record["source_blob_sha256"],
                    "source_field_sha256": record["field_sha256"],
                    "source_context_sha256": record["source_context_sha256"],
                    "target_reference": option["target_reference"],
                    "target_blob_sha256": option["target_blob_sha256"],
                    "target_context_sha256": option["target_context_sha256"],
                    "candidate_reason": record["candidate_reason"],
                    "quest_id": variant.get("quest_id"),
                    "event": variant.get("source"),
                    "npc_id": variant.get("npc_id"),
                    "npc_type": variant.get("npc_type"),
                    "voice": variant.get("voice"),
                    "faction": variant.get("faction"),
                    "player_gender": variant.get("player_gender"),
                    "wording_sha256": variant.get("wording_sha256"),
                    "manual_decision": option.get("manual_decision"),
                    "manual_reason": option.get("manual_reason"),
                    "review_check": "requires_independent_context_verification",
                    "human_notes": "",
                }
                writer.writerow({key: _cell(fields[key]) for key in COLUMNS})
    return io.getvalue()
