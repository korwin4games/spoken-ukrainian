"""Synthetic persistent content review and inert import tests; no source bodies."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest

from adapters.local_review_store import strict_json
from adapters.translation_approvals import (TranslationApprovals, ReviewCandidate,
    CHECKS, EMPTY, text_sha, validate_ledger)
from adapters.translation_sources import (SourcePolicy, TranslationCandidate,
    CandidateState)


def observation(text="Вигаданий текст.", provider="classicua", revision="a" * 40,
                original="Invented original.", **changes):
    candidate = TranslationCandidate(text, provider, "invented/source.lua", revision,
        "b" * 64, text_sha(text), "reviewed", CandidateState.NEEDS_REVIEW)
    return replace(ReviewCandidate("q:42:accept", "quest:horde:42:accept", original,
                                  "c" * 64, "d" * 64, "e" * 64, candidate), **changes)


class TranslationApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / "build"
        self.path = self.base / "translations.json"
        self.store = TranslationApprovals(self.path, self.base)
        self.policy = SourcePolicy(("classicua", "another", "original_english"))
        self.obs = [observation()]
        self.checks = dict.fromkeys(CHECKS, True)

    def collect(self, obs=None, policy=None):
        self.store.observe(self.obs if obs is None else obs, policy or self.policy)
        return self.store.file.data["versions"][0]["id"]

    def decide(self, identity, decision="approved", obs=None, checks=None):
        self.store.decide(identity, decision, "Invented content reviewer",
                          self.checks if checks is None else checks,
                          self.obs if obs is None else obs, self.policy)

    def test_approval_and_import_are_separate_persistent_and_idempotent(self):
        identity = self.collect()
        self.assertEqual(self.store.import_approved(self.obs, self.policy)["imported"], 0)
        self.decide(identity)
        self.assertEqual(self.store.file.data["imports"], [])
        reopened = TranslationApprovals(self.path, self.base)
        self.assertEqual(reopened.page(self.obs, self.policy)["versions"][0]["status"], "approved")
        self.assertTrue(reopened.import_approved(self.obs, self.policy)["changed"])
        disk = self.path.read_bytes()
        mtime = self.path.stat().st_mtime_ns
        self.assertFalse(reopened.import_approved(self.obs, self.policy)["changed"])
        self.assertEqual(self.path.read_bytes(), disk)
        self.assertEqual(self.path.stat().st_mtime_ns, mtime)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(reopened.page(self.obs, self.policy)["versions"][0]["imported"])

    def test_approval_requires_all_explicit_checks_and_named_reviewer(self):
        identity = self.collect()
        for check in CHECKS:
            with self.subTest(check=check), self.assertRaises(ValueError):
                self.decide(identity, checks=self.checks | {check: False})
        with self.assertRaises(ValueError):
            self.store.decide(identity, "approved", "", self.checks, self.obs, self.policy)
        self.assertEqual(self.store.file.data["versions"][0]["decisions"], [])

    def test_revision_and_file_only_changes_preserve_approval_and_provenance(self):
        identity = self.collect()
        self.decide(identity)
        changed = [replace(self.obs[0], candidate=replace(self.obs[0].candidate,
                    source_revision="f" * 40, source_file_sha256="1" * 64))]
        self.store.observe(changed, self.policy)
        self.assertEqual(len(self.store.file.data["versions"]), 1)
        self.assertEqual(len(self.store.file.data["versions"][0]["provenance"]), 2)
        self.assertEqual(self.store.import_approved(changed, self.policy)["imported"], 1)
        self.store.observe(changed, self.policy)
        self.assertEqual(len(self.store.file.data["versions"][0]["provenance"]), 2)

    def test_changed_translation_creates_pending_version_and_stales_old(self):
        identity = self.collect()
        self.decide(identity)
        changed = [observation("Інший вигаданий текст.")]
        self.store.observe(changed, self.policy)
        rows = self.store.page(changed, self.policy)["versions"]
        self.assertEqual({r["status"] for r in rows}, {"stale", "pending"})
        self.assertEqual(self.store.import_approved(changed, self.policy)["imported"], 0)
        with self.assertRaises(ValueError):
            self.decide(identity, obs=changed)

    def test_original_context_grammar_and_missing_evidence_invalidate(self):
        identity = self.collect()
        self.decide(identity)
        for changed in ([], [observation(original="Changed invented original.")],
                        [observation(source_context_sha256="1" * 64)],
                        [observation(target_context_sha256="2" * 64)],
                        [observation(grammar_sha256="3" * 64)],
                        [observation(target_id="q:43:accept")]):
            with self.subTest(changed=changed):
                self.assertEqual(self.store.page(changed, self.policy)["versions"][0]["status"], "stale")
                self.assertEqual(self.store.import_approved(changed, self.policy)["imported"], 0)

    def test_manual_edits_create_history_and_survive_source_refresh(self):
        identity = self.collect()
        self.decide(identity)
        manual = self.store.edit(identity, "Вигадане ручне редагування.", "Invented editor", self.obs, self.policy)
        self.assertEqual(len(self.store.file.data["versions"]), 2)
        self.assertEqual(next(r for r in self.store.file.data["versions"] if r["id"] == manual)["decisions"], [])
        self.decide(manual)
        self.store.observe(self.obs, self.policy)
        self.assertEqual(self.store.eligible(self.obs, self.policy)[0]["version_id"], manual)
        self.store.observe([observation("Changed invented upstream.")], self.policy)
        manual_row = next(r for r in self.store.page([observation("Changed invented upstream.")], self.policy)["versions"] if r["id"] == manual)
        self.assertEqual(manual_row["text"], "Вигадане ручне редагування.")
        self.assertEqual(manual_row["status"], "stale")

    def test_conflicting_manual_edits_fail_closed(self):
        identity = self.collect()
        for text in ("Invented edit A", "Invented edit B"):
            manual = self.store.edit(identity, text, "Invented editor", self.obs, self.policy)
            self.decide(manual)
        with self.assertRaisesRegex(ValueError, "conflicting_approved_manual"):
            self.store.import_approved(self.obs, self.policy)

    def test_reject_defer_reapprove_revoke_and_duplicate_decisions(self):
        identity = self.collect()
        for decision in ("rejected", "deferred", "approved"):
            self.decide(identity, decision)
            self.assertEqual(self.store.page(self.obs, self.policy)["versions"][0]["status"], decision)
        self.store.import_approved(self.obs, self.policy)
        self.decide(identity, "rejected")
        self.assertEqual(self.store.file.data["imports"], [])
        self.assertEqual(self.store.import_approved(self.obs, self.policy)["imported"], 0)
        with self.assertRaises(ValueError):
            self.decide(identity, "rejected")
        self.assertEqual(len(self.store.file.data["versions"][0]["decisions"]), 4)

    def test_equivalent_provider_content_reuses_approval_preserves_provenance(self):
        identity = self.collect()
        self.decide(identity)
        obs = [observation(provider="another")]
        self.store.observe(obs, self.policy)
        self.assertEqual(len(self.store.file.data["versions"]), 1)
        self.assertEqual({p["provider"] for p in self.store.file.data["versions"][0]["provenance"]}, {"classicua", "another"})
        self.assertEqual(self.store.import_approved(obs, self.policy)["imported"], 1)

    def test_unapproved_higher_priority_does_not_replace_approved_lower(self):
        lower = [observation("Invented lower priority", provider="another")]
        identity = self.collect(lower)
        self.decide(identity, obs=lower)
        obs = self.obs + lower
        self.store.observe(obs, self.policy)
        self.assertEqual(self.store.eligible(obs, self.policy)[0]["version_id"], identity)
        high = next(r["id"] for r in self.store.file.data["versions"] if r["id"] != identity)
        self.decide(high, obs=obs)
        self.assertEqual(self.store.eligible(obs, self.policy)[0]["version_id"], high)
        reverse = SourcePolicy(("another", "classicua"))
        self.assertEqual(self.store.eligible(obs, reverse)[0]["version_id"], identity)

    def test_provider_storage_disabled_and_empty_policy(self):
        disabled = SourcePolicy.from_mapping({"schema_version": 1, "sources": ["classicua"],
                                               "store_locally": {"classicua": False}})
        self.store.observe(self.obs, disabled)
        self.assertEqual(self.store.file.data["versions"], [])
        identity = self.collect()
        self.decide(identity)
        for policy in (disabled, SourcePolicy(()), SourcePolicy(("original_english",))):
            self.assertEqual(self.store.import_approved(self.obs, policy)["imported"], 0)

    def auto_policy(self):
        return SourcePolicy.from_mapping({"schema_version": 2, "sources": [
            {"name": "classicua", "save_translations": True,
             "auto_approve_one_to_one": True},
            {"name": "original_english", "save_translations": False},
        ]})

    def test_auto_approve_one_to_one_saves_private_version_not_runtime(self):
        policy = self.auto_policy()
        report = self.store.observe(self.obs, policy)
        self.assertEqual(report, {"auto_approved": 1, "saved": True})
        row = self.store.file.data["versions"][0]
        self.assertEqual(row["decisions"], [{
            "decision": "auto_approved_1to1",
            "reviewer": "policy:verified_one_to_one",
            "checks": {"text": False, "grammar": False, "ai": True, "rights": True},
        }])
        self.assertEqual(self.store.page(self.obs, policy)["versions"][0]["status"],
                         "auto_approved_1to1")
        self.assertEqual(self.store.file.data["imports"], [])
        self.assertIn("Вигаданий текст.", self.path.read_text(encoding="utf-8"))
        self.assertEqual(self.store.observe(self.obs, policy)["auto_approved"], 0)
        result = self.store.import_approved(self.obs, policy)
        self.assertEqual(result["imported"], 1)
        self.assertFalse(result["activated"])
        self.assertTrue(self.store.page(self.obs, policy)["versions"][0]["imported"])
        # Toggling off auto approval removes eligibility even if the private
        # ledger remembers the auditable automatic decision.
        disabled = SourcePolicy(("classicua", "original_english"))
        self.assertEqual(self.store.import_approved(self.obs, disabled)["imported"], 0)
        self.assertFalse(self.store.page(self.obs, disabled)["versions"][0]["imported"])

    def test_one_to_one_ambiguity_and_rights_do_not_auto_approve(self):
        policy = self.auto_policy()
        another_target = [self.obs[0], replace(self.obs[0], target_id="q:43:accept")]
        self.assertEqual(self.store.observe(another_target, policy)["auto_approved"], 0)
        self.assertTrue(all(not r["decisions"] for r in self.store.file.data["versions"]))
        self.assertEqual(self.store.import_approved(another_target, policy)["imported"], 0)
        self.assertEqual(self.store.page(another_target, policy)["versions"][0]["status"], "pending")
        # Another candidate for same target, from a different source identity,
        # means this is not a one-to-one pair.
        with tempfile.TemporaryDirectory() as d:
            store = TranslationApprovals(Path(d) / "build" / "translations.json", Path(d) / "build")
            same_target = [self.obs[0], replace(self.obs[0], source_id="quest:horde:43:accept")]
            self.assertEqual(store.observe(same_target, policy)["auto_approved"], 0)
            self.assertEqual(store.import_approved(same_target, policy)["imported"], 0)
        # A private provider candidate with rights still pending cannot be
        # promoted by the automatic pathway.
        with tempfile.TemporaryDirectory() as d:
            store = TranslationApprovals(Path(d) / "build" / "translations.json", Path(d) / "build")
            pending = [replace(self.obs[0], candidate=replace(self.obs[0].candidate,
                                   rights_status="pending"))]
            self.assertEqual(store.observe(pending, policy)["auto_approved"], 0)
            self.assertEqual(store.import_approved(pending, policy)["imported"], 0)

    def test_auto_approval_does_not_override_manual_or_changed_source(self):
        policy = self.auto_policy()
        self.store.observe(self.obs, policy)
        edited = self.store.edit(self.store.file.data["versions"][0]["id"],
                                 "Власна редакція.", "Invented editor",
                                 self.obs, policy)
        self.assertEqual(next(r for r in self.store.file.data["versions"]
                              if r["id"] == edited)["decisions"], [])
        changed = [observation("Новий текст від джерела.")]
        self.assertEqual(self.store.observe(changed, policy)["auto_approved"], 0)
        states = {r["status"] for r in self.store.page(changed, policy)["versions"]}
        self.assertEqual(states, {"stale", "pending"})
        self.assertEqual(self.store.import_approved(changed, policy)["imported"], 0)

    def test_auto_approval_record_cannot_claim_human_checks(self):
        policy = self.auto_policy()
        self.store.observe(self.obs, policy)
        base = deepcopy(self.store.file.data)
        for change in ({"reviewer": "fake human"},
                       {"checks": dict.fromkeys(CHECKS, True)},
                       {"decision": "approved"}):
            row = deepcopy(base)
            row["versions"][0]["decisions"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_ledger(row)

    def test_atomic_conflict_and_corrupt_duplicate_unknown_schema_fail_closed(self):
        identity = self.collect()
        other = TranslationApprovals(self.path, self.base)
        self.decide(identity)
        with self.assertRaisesRegex(ValueError, "conflict"):
            other.import_approved(self.obs, self.policy)
        valid = deepcopy(self.store.file.data)
        bad_rows = [valid | {"schema_version": 2}, valid | {"extra": True},
                    valid | {"versions": valid["versions"] * 2},
                    valid | {"imports": [{"target_id": "q:99:accept", "version_id": identity}]}]
        changed = deepcopy(valid)
        changed["versions"][0]["text"] = "corrupted invented wording"
        bad_rows.append(changed)
        for bad in bad_rows:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_ledger(bad)
        with self.assertRaises(ValueError):
            strict_json('{"schema_version":1,"schema_version":1}')
        self.path.write_text('{broken', encoding="utf-8")
        with self.assertRaises(ValueError):
            TranslationApprovals(self.path, self.base)

    def test_failed_atomic_replace_keeps_previous_ledger_and_memory(self):
        identity = self.collect()
        disk = self.path.read_bytes()
        with patch("adapters.local_review_store.os.replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                self.decide(identity)
        self.assertEqual(self.path.read_bytes(), disk)
        self.assertEqual(self.store.file.data["versions"][0]["decisions"], [])
        self.assertEqual(list(self.base.glob(".review-*")), [])

    def test_import_records_new_revision_provenance_without_reapproval(self):
        identity = self.collect()
        self.decide(identity)
        changed = [observation(revision="f" * 40)]
        self.assertEqual(self.store.import_approved(changed, self.policy)["imported"], 1)
        self.assertEqual(len(self.store.file.data["versions"][0]["provenance"]), 2)
        self.assertEqual(len(self.store.file.data["versions"][0]["decisions"]), 1)

    def test_rights_state_change_requires_new_review(self):
        identity = self.collect()
        self.decide(identity)
        pending = [replace(self.obs[0], candidate=replace(self.obs[0].candidate, rights_status="pending"))]
        self.store.observe(pending, self.policy)
        self.assertEqual(self.store.import_approved(pending, self.policy)["imported"], 0)
        self.assertEqual({r["status"] for r in self.store.page(pending, self.policy)["versions"]}, {"stale", "pending"})

    def test_symlink_and_outside_storage_refused(self):
        with self.assertRaises(ValueError):
            TranslationApprovals(self.base.parent / "outside.json", self.base)
        self.base.mkdir(exist_ok=True)
        link = self.base / "link.json"
        link.symlink_to(self.base.parent / "outside.json")
        with self.assertRaises(ValueError):
            TranslationApprovals(link, self.base)

    def test_mock_ai_and_invalid_storage_policies_refused(self):
        for candidate in (replace(self.obs[0].candidate, state=CandidateState.MOCK_ONLY),
                          replace(self.obs[0].candidate, ai_marked=True)):
            with self.assertRaises(ValueError):
                self.store.observe([replace(self.obs[0], candidate=candidate)], self.policy)
        for storage in ({"unknown": True}, {"classicua": 1}, [], {"classicua": "false"}):
            with self.assertRaises(ValueError):
                SourcePolicy.from_mapping({"schema_version": 1, "sources": ["classicua"], "store_locally": storage})


if __name__ == "__main__":
    unittest.main()
