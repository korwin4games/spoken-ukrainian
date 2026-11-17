"""Reusable offline content review; identity evidence is supplied by audited adapters.

An approval is local text/grammar/AI/rights attestation, never runtime or audio
approval. Import writes an inert snapshot in the same transaction as the ledger.
"""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256

from adapters.crosswalk import digest
from adapters.local_review_store import LocalFile
from adapters.translation_sources import CandidateState, TranslationCandidate, HEX64

CHECKS = ("text", "grammar", "ai", "rights")
AUTO_DECISION = "auto_approved_1to1"
AUTO_REVIEWER = "policy:verified_one_to_one"
# Automatic approval is NOT a human quality/grammar attestation.
AUTO_CHECKS = {"text": False, "grammar": False, "ai": True, "rights": True}
BINDING = {"target_id", "source_id", "original_sha256", "source_context_sha256",
           "target_context_sha256", "grammar_sha256"}
KEY_FIELDS = BINDING | {"text_sha256", "base_sha256", "kind", "rights_status"}
PROVENANCE = {"provider", "source_id", "source_ref", "revision", "file_sha256", "field_sha256"}
VERSION_FIELDS = KEY_FIELDS | {"id", "number", "text", "editor", "provenance", "decisions"}
EMPTY = {"schema_version": 1, "versions": [], "imports": []}


def text_sha(text):
    return sha256(text.encode("utf-8")).hexdigest()


def nonblank(value, maximum=512):
    return type(value) is str and bool(value.strip()) and len(value) <= maximum


def fields(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("invalid_translation_approval_fields")


def version_id(row):
    return digest({k: row[k] for k in sorted(KEY_FIELDS)})


def _validate_ledger(data):
    fields(data, EMPTY)
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("unsupported_translation_approval_schema")
    if type(data["versions"]) is not list or type(data["imports"]) is not list:
        raise ValueError("invalid_translation_approval_lists")
    seen, numbers = {}, set()
    for row in data["versions"]:
        fields(row, VERSION_FIELDS)
        if (any(not nonblank(row[k]) for k in ("target_id", "source_id"))
                or any(type(row[k]) is not str or not HEX64.fullmatch(row[k])
                       for k in KEY_FIELDS - {"target_id", "source_id", "kind", "rights_status"})
                or row["kind"] not in ("provider", "manual")
                or row["rights_status"] not in ("pending", "reviewed")
                or type(row["number"]) is not int or row["number"] < 1 or row["number"] in numbers
                or not nonblank(row["text"], 60000)
                or row["text_sha256"] != text_sha(row["text"])
                or row["id"] != version_id(row) or row["id"] in seen
                or (row["kind"] == "manual" and not nonblank(row["editor"], 120))
                or (row["kind"] == "provider" and (row["editor"] != "" or row["base_sha256"] != row["text_sha256"]))
                or type(row["provenance"]) is not list or not row["provenance"]
                or type(row["decisions"]) is not list):
            raise ValueError("invalid_or_duplicate_translation_version")
        provenance_seen = set()
        for p in row["provenance"]:
            fields(p, PROVENANCE)
            if (p["provider"] not in ("classicua", "another")
                    or any(not nonblank(p[k]) for k in ("source_id", "source_ref", "revision"))
                    or p["source_id"] != row["source_id"]
                    or any(type(p[k]) is not str or not HEX64.fullmatch(p[k])
                           for k in ("file_sha256", "field_sha256"))
                    or p["field_sha256"] != row["base_sha256"] or digest(p) in provenance_seen):
                raise ValueError("invalid_or_duplicate_translation_provenance")
            provenance_seen.add(digest(p))
        for d in row["decisions"]:
            fields(d, {"decision", "reviewer", "checks"})
            if (d["decision"] not in ("approved", "rejected", "deferred", AUTO_DECISION)
                    or not nonblank(d["reviewer"], 120) or type(d["checks"]) is not dict
                    or set(d["checks"]) != set(CHECKS)
                    or any(type(v) is not bool for v in d["checks"].values())
                    or (d["decision"] == "approved" and not all(d["checks"].values()))
                    or (d["decision"] == AUTO_DECISION and
                        (row["kind"] != "provider" or row["rights_status"] != "reviewed"
                         or d["reviewer"] != AUTO_REVIEWER or d["checks"] != AUTO_CHECKS))
                    or (d["decision"] != AUTO_DECISION and d["reviewer"] == AUTO_REVIEWER)):
                raise ValueError("explicit_content_attestation_required")
        seen[row["id"]] = row
        numbers.add(row["number"])
    if numbers != set(range(1, len(numbers) + 1)):
        raise ValueError("invalid_translation_version_sequence")
    imported_targets = set()
    for item in data["imports"]:
        fields(item, {"target_id", "version_id"})
        row = seen.get(item["version_id"]) if type(item["version_id"]) is str else None
        if (row is None or item["target_id"] != row["target_id"]
                or row["target_id"] in imported_targets
                or status(row) not in ("approved", AUTO_DECISION)):
            raise ValueError("invalid_or_duplicate_translation_import")
        imported_targets.add(row["target_id"])
    return deepcopy(data)


def validate_ledger(data):
    try:
        return _validate_ledger(data)
    except (KeyError, TypeError, AttributeError):
        raise ValueError("malformed_translation_approval_record") from None


def status(row):
    return row["decisions"][-1]["decision"] if row["decisions"] else "pending"


@dataclass(frozen=True)
class ReviewCandidate:
    """Trusted current binding from a content-specific audited identity bridge."""
    target_id: str
    source_id: str
    original: str
    source_context_sha256: str
    target_context_sha256: str
    grammar_sha256: str
    candidate: TranslationCandidate

    def row(self):
        c = self.candidate
        if (not isinstance(c, TranslationCandidate) or c.state != CandidateState.NEEDS_REVIEW
                or c.ai_marked or c.provider not in ("classicua", "another")
                or not nonblank(self.original, 60000)):
            raise ValueError("audited_real_candidate_required")
        row = {"target_id": self.target_id, "source_id": self.source_id,
               "original_sha256": text_sha(self.original),
               "source_context_sha256": self.source_context_sha256,
               "target_context_sha256": self.target_context_sha256,
               "grammar_sha256": self.grammar_sha256,
               "text_sha256": c.field_sha256, "base_sha256": c.field_sha256,
               "kind": "provider", "rights_status": c.rights_status, "number": 1,
               "editor": "", "text": c.text_uk,
               "provenance": [{"provider": c.provider, "source_id": self.source_id,
                               "source_ref": c.source_ref, "revision": c.source_revision,
                               "file_sha256": c.source_file_sha256, "field_sha256": c.field_sha256}],
               "decisions": []}
        row["id"] = version_id(row)
        validate_ledger({"schema_version": 1, "versions": [row], "imports": []})
        return row


class TranslationApprovals:
    def __init__(self, path, allowed_directory):
        self.file = LocalFile(path, allowed_directory, EMPTY, validate_ledger)

    def _save(self, data):
        for row in data["versions"]:
            row["provenance"].sort(key=digest)
        data["versions"].sort(key=lambda r: (r["target_id"], r["id"]))
        data["imports"].sort(key=lambda r: r["target_id"])
        self.file.save(data)

    @staticmethod
    def _unique_one_to_one(row, observations, policy):
        """Fail closed on shared source, target or alternate provider candidates.

        The caller (LocalReviewState) MUST have obtained observations by
        revalidating human-approved Stage 3 joins with approved_quest_bindings.
        Cardinality alone is never evidence of mapping identity.
        """
        if row["kind"] != "provider" or row["rights_status"] != "reviewed":
            return False
        related = [observation.row() for observation in observations
                   if observation.target_id == row["target_id"]
                   or observation.source_id == row["source_id"]]
        if len(related) != 1 or related[0]["id"] != row["id"]:
            return False
        provider = related[0]["provenance"][0]["provider"]
        return (policy.auto_approves_one_to_one(provider)
                and policy.stores(provider)
                and provider == "classicua")

    def observe(self, observations, policy):
        """Store reviewed-identity candidates; optionally auto-approve unique 1:1.

        Only *new* provider versions may be auto-approved. A changed upstream
        text, existing manual version, previous rejection or ambiguity leaves
        the newly observed version pending for a human.
        """
        data = deepcopy(self.file.data)
        rows = {r["id"]: r for r in data["versions"]}
        approved = 0
        for observation in observations:
            row = observation.row()
            provider = row["provenance"][0]["provider"]
            if provider not in policy.sources or not policy.stores(provider):
                continue
            if row["id"] not in rows:
                if (not any(prior["target_id"] == row["target_id"]
                            for prior in data["versions"])
                        and self._unique_one_to_one(row, observations, policy)):
                    row["decisions"].append({"decision": AUTO_DECISION,
                                             "reviewer": AUTO_REVIEWER,
                                             "checks": dict(AUTO_CHECKS)})
                    approved += 1
                row["number"] = len(data["versions"]) + 1
                data["versions"].append(row)
                rows[row["id"]] = row
            else:
                for p in row["provenance"]:
                    if p not in rows[row["id"]]["provenance"]:
                        rows[row["id"]]["provenance"].append(p)
        self.merge_provenance(data, observations, policy)
        self._save(data)
        return {"auto_approved": approved, "saved": True}

    def matching_observations(self, row, observations, policy):
        result = []
        for observation in observations:
            now = observation.row()
            provider = now["provenance"][0]["provider"]
            if (provider in policy.sources and policy.stores(provider)
                    and all(row[k] == now[k] for k in BINDING | {"base_sha256", "rights_status"})):
                result.append(now)
        return result

    def current(self, row, observations, policy):
        return bool(self.matching_observations(row, observations, policy))

    def merge_provenance(self, data, observations, policy):
        for row in data["versions"]:
            for now in self.matching_observations(row, observations, policy):
                for provenance in now["provenance"]:
                    if provenance not in row["provenance"]:
                        row["provenance"].append(provenance)

    def edit(self, identity, text, reviewer, observations, policy):
        data = deepcopy(self.file.data)
        original = next((r for r in data["versions"] if r["id"] == identity), None)
        if (original is None or not self.current(original, observations, policy)
                or not nonblank(text, 60000) or not nonblank(reviewer, 120)):
            raise ValueError("current_version_text_and_editor_required")
        row = deepcopy(original)
        row.update(text=text, text_sha256=text_sha(text), kind="manual", editor=reviewer, decisions=[])
        row["id"] = version_id(row)
        if row["id"] in {r["id"] for r in data["versions"]}:
            raise ValueError("duplicate_translation_edit")
        row["number"] = len(data["versions"]) + 1
        data["versions"].append(row)
        self._save(data)
        return row["id"]

    def decide(self, identity, decision, reviewer, checks, observations, policy):
        data = deepcopy(self.file.data)
        row = next((r for r in data["versions"] if r["id"] == identity), None)
        if row is None or not self.current(row, observations, policy):
            raise ValueError("current_reviewed_identity_required")
        entry = dict(decision=decision, reviewer=reviewer, checks=checks)
        if row["decisions"] and row["decisions"][-1] == entry:
            raise ValueError("duplicate_translation_decision")
        row["decisions"].append(entry)
        self.merge_provenance(data, observations, policy)
        # Revocation immediately removes inert imported references.
        data["imports"] = [i for i in data["imports"] if i["version_id"] != identity]
        self._save(data)

    def eligible(self, observations, policy):
        eligible = {}
        rank = {p: i for i, p in enumerate(policy.sources)}
        for row in self.file.data["versions"]:
            decision = status(row)
            if (decision not in ("approved", AUTO_DECISION)
                    or not self.current(row, observations, policy)):
                continue
            if decision == AUTO_DECISION and not self._unique_one_to_one(row, observations, policy):
                continue
            eligible.setdefault(row["target_id"], []).append(row)
        result = []
        for target, rows in sorted(eligible.items()):
            # Explicitly reviewed manual versions have precedence. Ambiguous
            # competing manual edits require reject/defer before import.
            manual = [r for r in rows if r["kind"] == "manual"]
            if len(manual) > 1:
                raise ValueError("conflicting_approved_manual_versions")
            if manual:
                chosen = manual[0]
            else:
                def priority(r):
                    return min(rank[now["provenance"][0]["provider"]] for now in
                               self.matching_observations(r, observations, policy))
                rows.sort(key=lambda r: (priority(r), r["id"]))
                if len(rows) > 1 and priority(rows[0]) == priority(rows[1]):
                    raise ValueError("conflicting_approved_provider_versions")
                chosen = rows[0]
            result.append({"target_id": target, "version_id": chosen["id"]})
        return result

    def import_approved(self, observations, policy):
        data = deepcopy(self.file.data)
        self.merge_provenance(data, observations, policy)
        data["imports"] = self.eligible(observations, policy)
        changed = data != self.file.data
        self._save(data)
        return {"imported": len(data["imports"]), "changed": changed, "activated": False}

    def page(self, observations, policy):
        result = []
        try:
            eligible = self.eligible(observations, policy)
            import_conflict = False
        except ValueError:
            eligible, import_conflict = [], True
        for row in self.file.data["versions"]:
            current = self.current(row, observations, policy)
            original = next((o.original for o in observations
                             if o.target_id == row["target_id"] and text_sha(o.original) == row["original_sha256"]), None)
            result.append(deepcopy(row) | {"status": status(row) if current else "stale",
                                         "current": current, "english_original": original,
                                         "imported": current and {"target_id": row["target_id"], "version_id": row["id"]}
                                         in self.file.data["imports"] and {"target_id": row["target_id"], "version_id": row["id"]} in eligible})
        return {"schema_version": 1, "versions": result, "activation": False,
                "import_conflict": import_conflict}
