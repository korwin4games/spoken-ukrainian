"""Deterministic review and independent SQLite import history for private tests."""
from collections import Counter
from contextlib import contextmanager
import json
import re

from adapters.classicua.grammar import inventory
from adapters.source_revision_store import digest, sha
from adapters.sqlite_translation_store import connection

AGENT = "spoken-deterministic-v2"
MODULES = {"all": None, "quests": "quest", "gossip": "gossip"}
STATUSES = ("unreviewed", "agent_verified", "needs_human_review",
            "agent_reject_recommended", "agent_unavailable", "stale")
QUEST = re.compile(r"(q:[1-9][0-9]*:(?:accept|progress|complete))(?::.*)?\Z")
GOSSIP = re.compile(r"gossip:(common|[1-9][0-9]*):([1-9][0-9]*)\Z")
TOKENS = re.compile(r"\$[NnCcRrBbGg]|\|[cCrRhHtTaA]|%(?:\d+\$)?[sdif]|\{[^{}]*\}")
CLIENT_TOKENS = re.compile(r"\$[A-Za-z]|%(?:\d+\$)?[sdif]")
TEMPLATES = {"player_name": "$n", "player_class": "$c",
             "player_race": "$r", "player_gender": "$g"}
TERMS = {"Alliance": ("Альянс", "альянс"), "Horde": ("Орда", "орд")}


def candidate(*, domain, target_id, provider, revision, target_revision, original,
              text, context, provenance, rights=False, identity=False, ai=False,
              bindings=(), group_sha=None):
    row = {"domain": domain, "target_id": target_id, "provider": provider,
           "revision": revision, "target_revision": target_revision,
           "original_sha256": sha(original), "text_sha256": sha(text),
           "context_sha256": context, "provenance": provenance,
           "rights_evidence": rights, "identity_verified": identity,
           "ai_marked": ai, "bindings": list(bindings), "group_sha256": group_sha}
    return {**row, "id": digest(row), "original": original, "text": text}


def metadata(row):
    return {k: v for k, v in row.items() if k not in ("original", "text")}


def placeholders(text):
    templates = {f.syntax: TEMPLATES.get(f.category, f.syntax) for f in inventory(text)}
    return Counter(templates.get(token, token.lower()) for token in TOKENS.findall(text))


def model_notes(value, identity):
    if value is None:
        return None
    expected = {"candidate_id", "model_version", "status", "findings", "corrections"}
    if (type(value) is not dict or set(value) != expected or value["candidate_id"] != identity
            or value["status"] not in ("available", "unavailable")
            or type(value["model_version"]) is not str
            or not 0 < len(value["model_version"].strip()) <= 120):
        raise ValueError("invalid_model_assessment_use_exact_candidate_id_and_schema")
    for field in ("findings", "corrections"):
        notes = value[field]
        if (type(notes) is not list or len(notes) > 20
                or any(type(note) is not str or not 0 < len(note.strip()) <= 2000
                       or re.search(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", note) for note in notes)
                or (value["status"] == "unavailable" and notes)):
            raise ValueError("invalid_model_assessment_notes")
    return value


def assess(row, model=None):
    model = model_notes(model, row["id"])
    original, translated = row["original"], row["text"]
    english_tokens, ukrainian_tokens = placeholders(original), placeholders(translated)
    checks = {
        "canonical_context": row["identity_verified"],
        "local_test_rights_evidence": row["rights_evidence"],
        "source_provenance": bool(row["provenance"]),
        "translation_fingerprint": sha(translated) == row["text_sha256"],
        "original_fingerprint": sha(original) == row["original_sha256"],
        "placeholder_correspondence": english_tokens == ukrainian_tokens,
        "supported_templates": all(f.status == "supported" for f in inventory(translated)),
        "runtime_placeholders_supported": not CLIENT_TOKENS.search(translated),
        "safe_controls": not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", translated),
        "line_breaks": original.count("\n") == translated.count("\n"),
        "ukrainian_script_present": bool(re.search(r"[А-Яа-яІіЇїЄєҐґ]", translated)),
        "ukrainian_alphabet": not re.search(r"[ЫыЭэЪъЁё]", translated),
        "complex_markup_requires_inspection": not re.search(r"\|[cCrRhHtTaA]", original + translated),
        "translation_differs_from_original": original.strip().casefold() != translated.strip().casefold(),
        "source_ai_unmarked": not row["ai_marked"],
    }
    findings = ["Grammar, meaning and NPC/Quest dialogue nuance require human review."]
    corrections = []
    for english, (ukrainian, stem) in TERMS.items():
        if re.search(r"(?i)\b" + english + r"\b", original) and not re.search(
                r"(?i)\b" + stem, translated):
            findings.append(f"Check Warcraft terminology for {english}.")
            corrections.append(f"Verify whether {ukrainian} fits the context.")
    if english_tokens != ukrainian_tokens:
        corrections.append("Check the player variables and formatting markers against the English original.")
    if not checks["runtime_placeholders_supported"]:
        corrections.append("Replace raw client variables with supported local addon templates.")
    if not checks["ukrainian_alphabet"]:
        findings.append("Inspect characters outside the Ukrainian alphabet in the translation.")
    if not checks["complex_markup_requires_inspection"]:
        findings.append("Inspect the WoW markup and player-visible formatting.")
    missing = [key for key in ("canonical_context", "local_test_rights_evidence",
                               "source_provenance") if not checks[key]]
    hard = ("translation_fingerprint", "original_fingerprint", "placeholder_correspondence",
            "supported_templates", "runtime_placeholders_supported", "safe_controls")
    if not all(checks[key] for key in hard):
        status = "agent_reject_recommended"
    elif model and model["status"] == "unavailable":
        status = "agent_unavailable"
    elif missing or not all(checks.values()) or corrections or model:
        status = "needs_human_review"
    else:
        status = "agent_verified"
    return {"candidate": metadata(row), "agent": AGENT, "status": status,
            "model_version": model["model_version"] if model else None,
            "model_notes": model, "checks": checks, "findings": findings,
            "corrections": corrections, "missing_evidence": missing}


def runtime_key(domain, target):
    if domain == "quest" and (match := QUEST.fullmatch(target)):
        return match.group(1)
    if domain == "gossip" and GOSSIP.fullmatch(target):
        return target
    return None


def protected(db):
    """Read current human state under the same SQLite transaction as imports."""
    from adapters.local_review_store import strict_json
    from adapters.translation_approvals import _validate_ledger
    from tools.gossip_translation_review import validate_ledger

    targets, groups = set(), set()
    documents = dict(db.execute("SELECT ledger_name, payload FROM ledger_documents"))
    if "translation-reviews.json" in documents:
        quest = _validate_ledger(strict_json(documents["translation-reviews.json"]))
        targets.update(runtime_key("quest", r["target_id"]) for r in quest["versions"]
                       if r["kind"] == "manual" or r["decisions"])
    if "stage4b-decisions.json" in documents:
        decisions = strict_json(documents["stage4b-decisions.json"])
        targets.update(runtime_key("quest", r["target_id"]) for r in decisions["decisions"])
    if "gossip-translation-reviews.json" in documents:
        gossip = validate_ledger(strict_json(documents["gossip-translation-reviews.json"]))
        groups.update(r["english_sha256"] for r in gossip["versions"])
    source = db.execute("""SELECT domain, target_id FROM source_active_selections
        UNION SELECT c.domain, c.target_id FROM source_candidates c
        JOIN source_candidate_decisions d ON d.candidate_id=c.id""")
    targets.update(runtime_key(domain, target) for domain, target in source)
    return targets, groups


def blocked(row, protections):
    targets, groups = protections
    key = runtime_key(row["domain"], row["target_id"])
    if key is None:
        return "unsupported_runtime_identity"
    if key in targets or row["group_sha256"] in groups:
        return "existing_manual_decision_or_source_selection"
    if row["domain"] == "gossip" and key.startswith("gossip:common:"):
        suffix = ":" + key.rsplit(":", 1)[1]
        if any(t and t.startswith("gossip:") and t.endswith(suffix) for t in targets):
            return "common_fallback_would_overlap_source_review"
    return None


class TranslationAgent:
    def __init__(self, db_path, evidence):
        self.db_path = db_path
        self.evidence = evidence

    @contextmanager
    def transaction(self, write):
        with connection(self.db_path) as db:
            if write:
                db.execute("BEGIN IMMEDIATE")
            else:
                db.execute("BEGIN")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def run(self, action, *, module="all", candidate_ids=(), limit=25, offset=0,
            status=None, dry_run=False, confirm=False, model=None):
        if (module not in MODULES or type(limit) is not int or not 1 <= limit <= 100
                or type(offset) is not int or offset < 0 or status not in (None, *STATUSES)
                or type(dry_run) is not bool or type(confirm) is not bool):
            raise ValueError("invalid_agent_options_check_module_status_limit_offset")
        if (type(candidate_ids) not in (tuple, list) or len(candidate_ids) > limit
                or any(type(i) is not str or not re.fullmatch("[0-9a-f]{64}", i) for i in candidate_ids)
                or len(set(candidate_ids)) != len(candidate_ids)):
            raise ValueError("invalid_agent_candidate_selection")
        if action not in ("status", "report", "history", "one", "batch", "pending", "import-verified"):
            raise ValueError("invalid_agent_action")
        if model is not None and action != "one":
            raise ValueError("model_assessment_requires_one_selected_candidate")
        if ((action == "one" and len(candidate_ids) != 1)
                or (action == "batch" and not candidate_ids)):
            raise ValueError("select_candidates_for_agent_review")
        if action == "pending" and candidate_ids:
            raise ValueError("pending_review_selects_only_unassessed_candidates")
        if action == "import-verified" and not dry_run and not confirm:
            raise ValueError("confirm_private_bulk_import_or_use_dry_run")
        if action == "import-verified" and (status not in (None, "agent_verified") or offset):
            raise ValueError("bulk_import_uses_module_or_explicit_candidate_selection")
        rows = {r["id"]: r for r in self.evidence()}
        if candidate_ids and action in ("one", "batch") and any(
                i not in rows or MODULES[module] not in (None, rows[i]["domain"]) for i in candidate_ids):
            raise ValueError("candidate_missing_or_stale_refresh_agent_status")
        write = not dry_run and action in ("one", "batch", "pending", "import-verified")
        with self.transaction(write) as db:
            latest = {r["candidate"]["id"]: r for r in assessment_rows(db, latest=True)}
            if write:
                record_staleness(db, latest, rows)
            stale = stale_ids(db)
            domain = MODULES[module]
            scoped = lambda r: domain is None or r["domain"] == domain
            if action == "import-verified":
                return self._import(db, rows, latest, stale, domain, dry_run, candidate_ids)
            if action in ("status", "report", "history"):
                if action == "history":
                    results = assessment_rows(db)
                else:
                    results = list(latest.values()) + [
                        {"candidate": metadata(row), "status": "unreviewed"}
                        for key, row in rows.items() if key not in latest]
                results = [{**r, "status": "stale" if (r["candidate"]["id"] not in rows
                            or r["candidate"]["id"] in stale
                            or r.get("agent", AGENT) != AGENT) else r["status"],
                            "assessed_status": r["status"]} for r in results
                           if scoped(r["candidate"])
                           and (not candidate_ids or r["candidate"]["id"] in candidate_ids)]
                counts = Counter(r["status"] for r in results)
                results = [r for r in results if status is None or r["status"] == status]
                page = results[offset:offset + limit]
                if action == "history":
                    ids = {r["assessment_id"] for r in page}
                    events = [{"candidate_id": key, "assessment_id": reference, "action": verb,
                               "reason": reason, "at": timestamp}
                              for key, reference, verb, reason, timestamp in db.execute("""
                                  SELECT candidate_id, assessment_id, action, reason, imported_at
                                  FROM agent_imports ORDER BY id DESC""") if reference in ids]
                    return {"counts": dict(counts), "total": len(results), "items": page,
                            "import_events": events}
                return {"counts": dict(counts), "total": len(results), "items": page}
            selected = [rows[i] for i in candidate_ids] if candidate_ids else [
                r for r in rows.values() if scoped(r) and r["id"] not in latest]
            if status is not None:
                selected = [r for r in selected if (
                    "stale" if r["id"] in stale or latest.get(r["id"], {}).get("agent", AGENT) != AGENT
                    else latest.get(r["id"], {}).get("status", "unreviewed")) == status]
            results = [assess(r, model) for r in selected[offset:offset + limit]]
            if write:
                db.executemany("""INSERT INTO agent_assessments(candidate_id, status, payload)
                    VALUES (?, ?, ?)""", [(r["candidate"]["id"], r["status"], json.dumps(r, ensure_ascii=False))
                                          for r in results if r["candidate"]["id"] in stale or r != {
                                              k: v for k, v in latest.get(r["candidate"]["id"], {}).items()
                                              if k not in ("assessment_id", "assessed_at")}])
                db.executemany("DELETE FROM agent_stale_evidence WHERE candidate_id=?",
                               [(r["candidate"]["id"],) for r in results])
            return {"reviewed": len(results), "dry_run": dry_run, "items": results}

    def _import(self, db, rows, latest, stale, domain, dry_run, candidate_ids):
        protections = protected(db)
        current = {a["candidate_id"]: a for a in import_rows(db)}
        selected = [(i, a) for i, a in latest.items() if (domain is None or a["candidate"]["domain"] == domain)
                    and (not candidate_ids or i in candidate_ids)]
        counts = verified_targets(latest, stale, rows)
        result = dict(eligible=0, imported=0, already_imported=0, skipped=0,
                      conflict=0, would_import=0, reasons=[], dry_run=dry_run)
        selected_ids = {identity for identity, _ in selected}
        for identity in candidate_ids:
            if identity not in selected_ids:
                result["skipped"] += 1
                result["reasons"].append({"candidate_id": identity,
                    "reason": "assessment_missing" if identity in rows and
                    domain in (None, rows[identity]["domain"]) else "candidate_not_in_selected_scope"})
        for identity, assessment in selected:
            row = None if identity in stale else rows.get(identity)
            reason = eligibility(row, assessment, protections, counts)
            if reason:
                result["skipped"] += 1
                result["conflict"] += reason in ("multiple_verified_versions",
                                                  "existing_manual_decision_or_source_selection",
                                                  "common_fallback_would_overlap_source_review")
                result["reasons"].append({"candidate_id": identity, "reason": reason})
                if identity in current and not dry_run:
                    invalidate(db, current[identity], reason)
                continue
            result["eligible"] += 1
            if identity in current and current[identity]["assessment_id"] == assessment["assessment_id"]:
                result["already_imported"] += 1
            else:
                result["would_import"] += 1
                if not dry_run:
                    db.execute("INSERT INTO agent_imports(candidate_id, assessment_id) VALUES (?, ?)",
                               (identity, assessment["assessment_id"]))
                    result["imported"] += 1
        return result

    def effective_imports(self):
        rows = {r["id"]: r for r in self.evidence()}
        with self.transaction(True) as db:
            latest = {r["candidate"]["id"]: r for r in assessment_rows(db, latest=True)}
            record_staleness(db, latest, rows)
            stale = stale_ids(db)
            protections = protected(db)
            counts = verified_targets(latest, stale, rows)
            result = []
            for entry in import_rows(db):
                identity = entry["candidate_id"]
                assessment = latest.get(identity)
                reason = ("assessment_superseded" if not assessment or
                          assessment["assessment_id"] != entry["assessment_id"] else
                          eligibility(None if identity in stale else rows.get(identity),
                                      assessment, protections, counts))
                if reason:
                    invalidate(db, entry, reason)
                else:
                    result.append(rows[identity])
            return result


def eligibility(row, assessment, protections, counts):
    if row is None or metadata(row) != assessment["candidate"] or assessment["agent"] != AGENT:
        return "stale_evidence"
    if assessment["status"] != "agent_verified" or assess(row)["status"] != "agent_verified":
        return "assessment_not_verified"
    reason = blocked(row, protections)
    if reason:
        return reason
    if counts[runtime_key(row["domain"], row["target_id"])] > 1:
        return "multiple_verified_versions"
    return None


def verified_targets(latest, stale, evidence_ids):
    return Counter(runtime_key(row["candidate"]["domain"], row["candidate"]["target_id"])
                   for identity, row in latest.items()
                   if identity in evidence_ids and identity not in stale
                   and row["agent"] == AGENT and row["status"] == "agent_verified")


def record_staleness(db, assessments, current):
    missing = assessments.keys() - current.keys()
    db.executemany("INSERT OR IGNORE INTO agent_stale_evidence(candidate_id) VALUES (?)",
                   [(identity,) for identity in missing])
    if missing:
        for entry in import_rows(db):
            if entry["candidate_id"] in missing:
                invalidate(db, entry, "stale_evidence")


def stale_ids(db):
    return {row[0] for row in db.execute("SELECT candidate_id FROM agent_stale_evidence")}


def assessment_rows(db, latest=False):
    where = "WHERE id IN (SELECT MAX(id) FROM agent_assessments GROUP BY candidate_id)" if latest else ""
    return [{**json.loads(payload), "assessment_id": identity, "assessed_at": timestamp}
            for identity, timestamp, payload in db.execute(
                f"SELECT id, assessed_at, payload FROM agent_assessments {where} ORDER BY id DESC")]


def import_rows(db):
    return [{"candidate_id": candidate_id, "assessment_id": assessment_id, "imported_at": timestamp}
            for candidate_id, assessment_id, timestamp in db.execute("""
                SELECT i.candidate_id, i.assessment_id, i.imported_at FROM agent_imports i
                WHERE i.action='import'
                  AND i.id IN (SELECT MAX(id) FROM agent_imports GROUP BY candidate_id)
                ORDER BY i.id""")]


def invalidate(db, entry, reason):
    db.execute("""INSERT INTO agent_imports(candidate_id, assessment_id, action, reason)
        VALUES (?, ?, 'invalidate', ?)""", (entry["candidate_id"], entry["assessment_id"], reason))


def has_imports(db_path):
    with connection(db_path) as db:
        return bool(import_rows(db))


def recorded_imports(db):
    imports = import_rows(db)
    if not imports:
        return
    stale = stale_ids(db)
    protection = protected(db)
    latest = {a["candidate"]["id"]: a for a in assessment_rows(db, latest=True)}
    counts = verified_targets(latest, stale, latest)
    for entry in imports:
        assessment = latest.get(entry["candidate_id"])
        if (entry["candidate_id"] not in stale and assessment and assessment["agent"] == AGENT
                and assessment["assessment_id"] == entry["assessment_id"]
                and assessment["status"] == "agent_verified"
                and not blocked(assessment["candidate"], protection)
                and counts[runtime_key(assessment["candidate"]["domain"],
                                       assessment["candidate"]["target_id"])] == 1):
            yield assessment["candidate"]
