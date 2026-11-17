"""Versioned external translation snapshots and explicit conflict resolution.

A source snapshot records *candidate* translations and is immutable. Human
decisions are append-only and active selections are separate from the
provider priority. No source candidate gains mapping, rights, publication
or build approval merely by being imported.
"""
from collections import defaultdict
from hashlib import sha256
import json
import re

from adapters.sqlite_translation_store import connection

SOURCES = ("classicua", "another", "own_translator")
DOMAINS = ("gossip", "quest")
CHECKS = ("text", "grammar", "ai", "rights", "all_contexts")
DECISIONS = ("approved", "rejected", "deferred")
HEX = re.compile(r"[0-9a-f]{64}\Z")
REV = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
MAX_TEXT = 60000
FIELDS = {"domain", "target_id", "english_sha256", "context_sha256",
          "ukrainian_text", "source_ref"}


def sha(text):
    return sha256(text.encode("utf-8")).hexdigest()


def digest(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")))


def exact(value):
    if type(value) is not dict:
        raise ValueError("invalid_source_snapshot")
    if set(value) != {"provider", "revision", "records"}:
        raise ValueError("invalid_source_snapshot_fields")
    provider, revision, records = value["provider"], value["revision"], value["records"]
    if (provider not in SOURCES or type(revision) is not str
            or not REV.fullmatch(revision) or type(records) is not list
            or len(records) > 50000):
        raise ValueError("invalid_source_snapshot_header")
    entries, seen = [], set()
    for row in records:
        if type(row) is not dict or set(row) != FIELDS:
            raise ValueError("invalid_source_candidate_fields")
        domain, target = row["domain"], row["target_id"]
        en, ctx = row["english_sha256"], row["context_sha256"]
        translated, ref = row["ukrainian_text"], row["source_ref"]
        if (domain not in DOMAINS or type(target) is not str or not target
                or len(target) > 256 or type(en) is not str or not HEX.fullmatch(en)
                or type(ctx) is not str or not HEX.fullmatch(ctx)
                or type(ref) is not str or not ref.strip() or len(ref) > 512
                or type(translated) is not str or not translated.strip()
                or len(translated) > MAX_TEXT):
            raise ValueError("invalid_source_candidate")
        key = domain, target, en, ctx
        if key in seen:
            raise ValueError("duplicate_source_candidate_context")
        seen.add(key)
        text_sha = sha(translated)
        identity = digest({"provider": provider, "revision": revision,
                           "domain": domain, "target": target,
                           "english_sha256": en, "context_sha256": ctx,
                           "text_sha256": text_sha, "source_ref": ref})
        entries.append({**row, "id": identity, "text_sha256": text_sha})
    entries.sort(key=lambda x: (x["domain"], x["target_id"],
                                x["english_sha256"], x["context_sha256"]))
    return provider, revision, entries


def _check_proof(entry, trusted):
    if trusted is None or (entry["domain"], entry["target_id"]) not in trusted:
        raise ValueError("source_candidate_target_not_verified")
    expected = trusted[entry["domain"], entry["target_id"]]
    if (expected["english_sha256"] != entry["english_sha256"]
            or expected["context_sha256"] != entry["context_sha256"]):
        raise ValueError("source_candidate_pinned_context_mismatch")


def _record(row):
    return {"id": row[0], "provider": row[1], "revision": row[2],
            "domain": row[3], "target_id": row[4],
            "english_sha256": row[5], "context_sha256": row[6],
            "ukrainian_text": row[7], "text_sha256": row[8],
            "source_ref": row[9]}


SELECT = """SELECT c.id, s.provider, s.revision, c.domain, c.target_id,
    c.english_sha256, c.context_sha256, c.ukrainian_text,
    c.text_sha256, c.source_ref FROM source_candidates c
    JOIN source_snapshots s ON s.id = c.snapshot_id"""


class SourceReviewStore:
    def __init__(self, db_path):
        self.db_path = db_path

    def ingest(self, snapshot, trusted):
        """One immutable full snapshot per (provider, revision). Fail closed."""
        provider, revision, entries = exact(snapshot)
        for entry in entries:
            _check_proof(entry, trusted)
        content_sha = digest({"provider": provider, "revision": revision,
                              "records": [dict((k, r[k]) for k in sorted(FIELDS))
                                          for r in entries]})
        with connection(self.db_path) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                old = db.execute("""SELECT id, content_sha256 FROM source_snapshots
                    WHERE provider = ? AND revision = ?""", (provider, revision)).fetchone()
                if old:
                    if old[1] != content_sha:
                        raise ValueError("source_snapshot_revision_is_immutable")
                    db.commit()
                    return {"provider": provider, "revision": revision,
                            "records": len(entries), "unchanged": True}
                cursor = db.execute("""INSERT INTO source_snapshots
                    (provider, revision, content_sha256) VALUES (?, ?, ?)""",
                    (provider, revision, content_sha))
                sid = cursor.lastrowid
                db.executemany("""INSERT INTO source_candidates
                    (id, snapshot_id, domain, target_id, english_sha256,
                     context_sha256, ukrainian_text, text_sha256, source_ref)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [(r["id"], sid, r["domain"], r["target_id"], r["english_sha256"],
                      r["context_sha256"], r["ukrainian_text"], r["text_sha256"],
                      r["source_ref"]) for r in entries])
                db.commit()
            except BaseException:
                db.rollback()
                raise
        return {"provider": provider, "revision": revision,
                "records": len(entries), "unchanged": False}

    def revisions(self):
        with connection(self.db_path) as db:
            rows = db.execute("""SELECT s.provider, s.revision, s.id,
                    COUNT(c.id) FROM source_snapshots s
                    LEFT JOIN source_candidates c ON c.snapshot_id = s.id
                    GROUP BY s.id ORDER BY s.id DESC""").fetchall()
        latest = {}
        for provider, rev, sid, count in rows:
            latest.setdefault(provider, sid)
        return [{"provider": p, "revision": rev, "record_count": count,
                 "latest": latest[p] == sid} for p, rev, sid, count in rows]

    def candidates(self, provider=None, revision=None):
        if provider is not None and provider not in SOURCES:
            raise ValueError("unknown_source_provider")
        with connection(self.db_path) as db:
            rows = db.execute(SELECT +
                """ WHERE (? IS NULL OR s.provider = ?)
                    AND (? IS NULL OR s.revision = ?)
                    ORDER BY s.id DESC, c.domain, c.target_id""",
                (provider, provider, revision, revision)).fetchall()
        return [_record(row) for row in rows]

    def compare(self, provider, before, after):
        if provider not in SOURCES or not all(type(x) is str and REV.fullmatch(x)
                                              for x in (before, after)):
            raise ValueError("invalid_source_comparison")
        with connection(self.db_path) as db:
            refs = [db.execute("""SELECT id FROM source_snapshots
                       WHERE provider = ? AND revision = ?""",
                       (provider, rev)).fetchone() for rev in (before, after)]
            if not all(refs):
                raise ValueError("unknown_source_snapshot_revision")
        a = {(r["domain"], r["target_id"], r["english_sha256"], r["context_sha256"]): r
             for r in self.candidates(provider, before)}
        b = {(r["domain"], r["target_id"], r["english_sha256"], r["context_sha256"]): r
             for r in self.candidates(provider, after)}
        change = []
        for key in sorted(set(a) | set(b)):
            old, new = a.get(key), b.get(key)
            kind = ("added" if old is None else "removed" if new is None
                    else "changed" if old["text_sha256"] != new["text_sha256"]
                    else "unchanged")
            change.append({"domain": key[0], "target_id": key[1],
                           "english_sha256": key[2], "context_sha256": key[3],
                           "change": kind, "before": old, "after": new})
        counts = {kind: sum(r["change"] == kind for r in change)
                  for kind in ("added", "removed", "changed", "unchanged")}
        return {"provider": provider, "before_revision": before,
                "after_revision": after, "counts": counts, "changes": change}

    @staticmethod
    def _status(db, candidate_id):
        row = db.execute("""SELECT decision FROM source_candidate_decisions
            WHERE candidate_id = ? ORDER BY id DESC LIMIT 1""",
            (candidate_id,)).fetchone()
        return row[0] if row else "pending"

    def decide(self, candidate_id, decision, reviewer, checks, trusted):
        if (type(candidate_id) is not str or not HEX.fullmatch(candidate_id)
                or decision not in DECISIONS or type(reviewer) is not str
                or not reviewer.strip() or len(reviewer) > 120
                or type(checks) is not dict or set(checks) != set(CHECKS)
                or any(type(v) is not bool for v in checks.values())
                or (decision == "approved" and not all(checks.values()))):
            raise ValueError("source_review_requires_explicit_attestations")
        with connection(self.db_path) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(SELECT + " WHERE c.id = ?", (candidate_id,)).fetchone()
                if row is None:
                    raise ValueError("unknown_source_review_candidate")
                _check_proof(_record(row), trusted)
                if self._status(db, candidate_id) == decision:
                    raise ValueError("duplicate_source_review_decision")
                db.execute("""INSERT INTO source_candidate_decisions
                    (candidate_id, decision, reviewer, checks_json)
                    VALUES (?, ?, ?, ?)""",
                    (candidate_id, decision, reviewer,
                     json.dumps(checks, sort_keys=True)))
                if decision != "approved":
                    db.execute("""DELETE FROM source_active_selections
                        WHERE candidate_id = ?""", (candidate_id,))
                db.commit()
            except BaseException:
                db.rollback()
                raise
        return {"candidate_id": candidate_id, "status": decision,
                "imported": False}

    def activate(self, candidate_id, reviewer, trusted):
        """Explicitly freeze a HUMAN-approved version; source changes do not replace it."""
        if (type(candidate_id) is not str or not HEX.fullmatch(candidate_id)
                or type(reviewer) is not str or not reviewer.strip()
                or len(reviewer) > 120):
            raise ValueError("invalid_source_selection")
        with connection(self.db_path) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(SELECT + " WHERE c.id = ?", (candidate_id,)).fetchone()
                if row is None:
                    raise ValueError("unknown_source_review_candidate")
                candidate = _record(row)
                _check_proof(candidate, trusted)
                if self._status(db, candidate_id) != "approved":
                    raise ValueError("source_selection_requires_human_approval")
                db.execute("""INSERT INTO source_active_selections
                    (domain, target_id, english_sha256, context_sha256, candidate_id, reviewer)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(domain, target_id, english_sha256, context_sha256)
                    DO UPDATE SET candidate_id = excluded.candidate_id,
                                  reviewer = excluded.reviewer,
                                  selected_at = CURRENT_TIMESTAMP""",
                    (candidate["domain"], candidate["target_id"],
                     candidate["english_sha256"], candidate["context_sha256"],
                     candidate_id, reviewer))
                db.commit()
            except BaseException:
                db.rollback()
                raise
        return {"candidate_id": candidate_id, "selected": True}

    def clear_selection(self, domain, target_id, reviewer, trusted):
        key = domain, target_id
        if (key not in trusted or type(reviewer) is not str
                or not reviewer.strip() or len(reviewer) > 120):
            raise ValueError("invalid_source_selection_clear")
        with connection(self.db_path) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("""DELETE FROM source_active_selections
                    WHERE domain = ? AND target_id = ?""", key)
                db.commit()
            except BaseException:
                db.rollback()
                raise
        return {"target_id": target_id, "selected": False}

    def active(self, trusted, domain=None):
        """Fail closed if any selected context or human approval has become stale."""
        if domain is not None and domain not in DOMAINS:
            raise ValueError("unknown_source_domain")
        with connection(self.db_path) as db:
            rows = db.execute(SELECT + """
                JOIN source_active_selections a ON a.candidate_id = c.id
                WHERE (? IS NULL OR c.domain = ?) ORDER BY c.domain, c.target_id""",
                (domain, domain)).fetchall()
            output = []
            for row in rows:
                candidate = _record(row)
                _check_proof(candidate, trusted)
                if self._status(db, candidate["id"]) != "approved":
                    raise ValueError("stale_source_selection")
                output.append(candidate)
        return output

    def conflicts(self, priority=None):
        """Latest imported revision per provider. Never silently select a winner."""
        ordered = list(priority or SOURCES)
        if any(p not in SOURCES for p in ordered) or len(set(ordered)) != len(ordered):
            raise ValueError("invalid_source_priority")
        with connection(self.db_path) as db:
            rows = db.execute(SELECT + """
                JOIN (SELECT provider, MAX(id) AS snapshot_id
                      FROM source_snapshots GROUP BY provider) latest
                  ON latest.snapshot_id = s.id
                ORDER BY c.domain, c.target_id, s.provider""").fetchall()
            groups = defaultdict(list)
            for row in rows:
                candidate = _record(row)
                candidate["status"] = self._status(db, candidate["id"])
                groups[(candidate["domain"], candidate["target_id"],
                        candidate["english_sha256"], candidate["context_sha256"])].append(candidate)
            active = {tuple(row[:4]): row[4] for row in db.execute(
                """SELECT domain, target_id, english_sha256,
                          context_sha256, candidate_id FROM source_active_selections""")}
            # Explicit old selections remain visible even when a provider
            # publishes a newer revision or removes the wording entirely.
            selected_old = {}
            for row in db.execute(SELECT + """
                JOIN source_active_selections a ON a.candidate_id = c.id"""):
                candidate = _record(row)
                candidate["status"] = self._status(db, candidate["id"])
                selected_old[candidate["id"]] = candidate
        result = []
        ranking = {p: i for i, p in enumerate(ordered)}
        for key, candidates in sorted(groups.items()):
            candidates.sort(key=lambda r: (ranking.get(r["provider"], len(ranking)),
                                           r["provider"], r["id"]))
            different = len({r["text_sha256"] for r in candidates}) > 1
            chosen = active.get(key)
            current_ids = {c["id"] for c in candidates}
            chosen_is_current = chosen in current_ids if chosen else None
            # Recommended, not activated: first approved source by policy,
            # but only when no conflicting text among simultaneously approved
            # variants. Manual selection always stays the actual selection.
            approved = [c for c in candidates if c["status"] == "approved"]
            recommended = (approved[0]["id"] if approved and
                           len({x["text_sha256"] for x in approved}) == 1 else None)
            shown = list(candidates)
            if chosen and chosen not in current_ids and chosen in selected_old:
                shown.append(selected_old[chosen])
            result.append({"domain": key[0], "target_id": key[1],
                           "english_sha256": key[2], "context_sha256": key[3],
                           "different": different, "candidates": shown,
                           "selected_candidate_id": chosen,
                           "selected_is_latest_source_revision": chosen_is_current,
                           "recommended_candidate_id": recommended})
        for key, chosen in active.items():
            if any((r["domain"], r["target_id"], r["english_sha256"],
                    r["context_sha256"]) == key for r in result):
                continue
            historical = selected_old.get(chosen)
            if historical:
                result.append({"domain": key[0], "target_id": key[1],
                               "english_sha256": key[2], "context_sha256": key[3],
                               "different": False, "candidates": [historical],
                               "selected_candidate_id": chosen,
                               "selected_is_latest_source_revision": False,
                               "recommended_candidate_id": None})
        result.sort(key=lambda r: (r["domain"], r["target_id"]))
        return {"conflicts": sum(r["different"] for r in result),
                "items": result}
