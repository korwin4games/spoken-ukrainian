"""End-to-end synthetic independent mapping → content review → inert import."""
from copy import deepcopy
from dataclasses import asdict, replace
from contextlib import redirect_stdout
from io import StringIO
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from unittest.mock import patch
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from test_stage3 import Fixture, reviewed
from adapters.review_ui import LocalReviewState
from adapters.spoken.text_index import TextIndex
from adapters.mapping import review_file, load_reviews
from adapters.translation_sources import SourcePolicy, TranslationCandidate, CandidateState
from adapters.sqlite_translation_store import enable_sqlite
from tools.review_ui_server import create_handler
from tools import build_ukrainian, review_ui_server

CHECKS = dict(text=True, grammar=True, ai=True, rights=True)


class ReviewApprovalUITests(unittest.TestCase):
    def setUp(self):
        self.inventory, self.unit, self.review, proof, self.source = reviewed()
        self.dataset = Fixture().add("quest_both", "classic", '{[42]={nil,"invented wording"}}').dataset
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / "build"
        self.originals = TextIndex({"q:42:accept": "invented wording"}, (), {})
        self.state = self.new_state()
        self.request = {"schema_version": 1, "source_id": self.unit.source_id,
                        "target_id": "q:42:accept", "mapping_reviewer": "Invented mapping reviewer",
                        "proof": asdict(proof)}

    def new_state(self, **kwargs):
        return LocalReviewState(self.dataset, self.source, self.inventory, self.originals,
                                 self.base / "decisions.json", self.base, **kwargs)

    def unique_one_to_one_state(self, **kwargs):
        # The default quest_both test inventory has Horde and Alliance variants
        # pointing to the same Spoken target: that is NOT globally 1:1.
        # Restrict a separate synthetic audited source inventory to one faction
        # for the positive auto-import test only. Never fabricate a mapping.
        unique_source = replace(self.source, units={
            self.unit.source_id: self.source.units[self.unit.source_id]})
        return LocalReviewState(self.dataset, unique_source,
                                self.inventory, self.originals,
                                self.base / "decisions.json", self.base, **kwargs)

    def approve_and_collect(self):
        self.state.approve_mapping(self.request)
        self.state.translation_action("refresh", {})
        return self.state.translation_page()["versions"][0]["id"]

    def test_mapping_decisions_block_every_automatic_entry_point(self):
        policy = SourcePolicy.from_mapping({"schema_version": 2, "sources": [
            {"name": "classicua", "save_translations": True, "auto_approve_one_to_one": True}]})
        payload = {"source": "classicua"}
        for decision in ("rejected", "deferred"):
            with self.subTest(decision=decision), enable_sqlite(self.base.parent / (decision + ".sqlite3")):
                state = LocalReviewState(self.dataset, self.source, self.inventory, self.originals,
                    self.base / "stage4b-decisions.json", self.base, policy=policy)
                self.assertEqual(state.translation_action("auto_import_one_to_one", payload)["machine_imported"], 1)
                state.decide(self.unit.source_id, "q:42:accept", decision, "wrong_speaker", "Fixture reviewer")
                self.assertEqual(build_ukrainian.current_quest_texts(state)[0], {})
                reasons = []
                self.assertEqual(state.translation_action("auto_import_one_to_one", payload,
                                                         skipped=reasons)["machine_imported"], 0)
                self.assertIn(("q:42:accept", "quest_mapping_rejected_or_deferred"), reasons)
                with patch.object(review_ui_server, "build_state", return_value=state), patch.object(
                        review_ui_server, "validate_source_paths"), redirect_stdout(StringIO()):
                    self.assertEqual(review_ui_server.main(["--classicua", "invented-classicua", "--spoken",
                        "invented-spoken", "--auto-import-one-to-one"]), 0)
                reopened = LocalReviewState(self.dataset, self.source, self.inventory, self.originals,
                    self.base / "stage4b-decisions.json", self.base, policy=policy)
                self.assertEqual(reopened.machine_imports.current_import_targets(), set())
                self.assertEqual(len(reopened.machine_imports.file.data["versions"]), 1)
                self.assertEqual(reopened.decisions["decisions"][0]["decision"], decision)

    def test_defer_blocks_content_import_and_preserves_previous_approval(self):
        identity = self.approve_and_collect()
        self.state.translation_action("decide", {"identity": identity, "decision": "approved",
            "reviewer": "Fixture content reviewer", "checks": CHECKS})
        self.assertEqual(self.state.translation_action("import", {})["imported"], 1)
        before = deepcopy(self.state.translations.file.data["versions"])
        self.state.decide(self.unit.source_id, "q:42:accept", "deferred", "wrong_speaker",
                          "Fixture mapping reviewer")
        self.assertEqual(build_ukrainian.current_quest_texts(self.state)[0], {})
        self.assertEqual(self.state.translation_action("import", {})["imported"], 0)
        self.assertEqual(self.state.translations.file.data["versions"], before)
        self.assertEqual(len(self.state.reviews), 1)

    def test_full_mapping_edit_review_import_restart_workflow(self):
        self.assertEqual(self.state.translation_page()["versions"], [])
        identity = self.approve_and_collect()
        self.assertEqual(self.state.page()["summary"]["human_stage3_approved_joins"], 1)
        approved_page = self.state.page()
        self.assertEqual(approved_page["approved_mappings"], [{
            "source_id": self.unit.source_id,
            "target_id": "q:42:accept",
            "mapping_status": "approved",
        }])
        self.assertFalse(any(item["source_id"] == self.unit.source_id
                             for item in approved_page["items"]))
        self.assertFalse(self.state.translation_page()["versions"][0]["imported"])
        edited = self.state.translation_action("edit", {"identity": identity,
                    "text": "Вигаданий переклад.", "reviewer": "Invented editor"})["version_id"]
        self.state.translation_action("decide", {"identity": edited, "decision": "approved",
                                     "reviewer": "Invented content reviewer", "checks": CHECKS})
        self.assertEqual(self.state.translations.file.data["imports"], [])
        self.assertEqual(self.state.translation_action("import", {})["imported"], 1)
        state = self.new_state()
        row = next(r for r in state.translation_page()["versions"] if r["id"] == edited)
        self.assertEqual(row["status"], "approved")
        self.assertTrue(row["imported"])
        self.assertFalse(state.translation_action("import", {})["changed"])
        mapping_disk = (self.base / "stage3-ui-reviews.json").read_text()
        self.assertNotIn("invented wording", mapping_disk)
        self.assertNotIn("Вигаданий переклад.", mapping_disk)

    def test_auto_approval_requires_reviewed_identity_and_one_to_one(self):
        policy = SourcePolicy.from_mapping({"schema_version": 2, "sources": [
            {"name": "classicua", "save_translations": True,
             "auto_approve_one_to_one": True},
            {"name": "original_english", "save_translations": False},
        ]})
        state = self.unique_one_to_one_state(policy=policy)
        # Quest ID/title intersections alone cannot approve anything.
        self.assertEqual(state.translation_action("refresh", {})["auto_approved"], 0)
        self.assertEqual(state.translation_page()["versions"], [])
        state.approve_mapping(self.request)
        result = state.translation_action("refresh", {})
        self.assertEqual(result["auto_approved"], 1)
        row = state.translation_page()["versions"][0]
        self.assertEqual(row["status"], "auto_approved_1to1")
        self.assertEqual(row["decisions"][0]["checks"]["text"], False)
        self.assertFalse(row["imported"])
        imported = state.translation_action("import", {})
        self.assertEqual(imported["imported"], 1)
        self.assertFalse(imported["activated"])
        self.assertTrue(state.translation_page()["versions"][0]["imported"])
        self.assertEqual(state.translation_page()["auto_approve_one_to_one"], ["classicua"])

    def test_bulk_one_to_one_import_shows_global_spoken_summary(self):
        policy = SourcePolicy.from_mapping({"schema_version": 2, "sources": [
            {"name": "classicua", "save_translations": True,
             "auto_approve_one_to_one": True},
            {"name": "original_english", "save_translations": False},
        ]})
        state = self.unique_one_to_one_state(policy=policy)
        provisional = state.translation_action("auto_import_one_to_one",
                                               {"source": "classicua"})
        self.assertEqual(provisional["imported"], 1)
        self.assertEqual(provisional["machine_imported"], 1)
        self.assertEqual(provisional["auto_approved"], 0)
        self.assertEqual(provisional["report"]["total_spoken_records"],
                         len(self.inventory.targets))
        self.assertEqual(provisional["report"]["machine_one_to_one_imported"], 1)
        self.assertEqual(provisional["report"]["verified_source_to_target_bindings"], 0)
        self.assertEqual(provisional["report"]["untranslated_total"],
                         len(self.inventory.targets) - 1)
        self.assertEqual(len(state.machine_imports.file.data["versions"]), 1)
        # A subsequent independently reviewed human mapping takes precedence.
        state.approve_mapping(self.request)
        imported = state.translation_action("auto_import_one_to_one",
                                            {"source": "classicua"})
        self.assertEqual(imported["imported"], 1)
        self.assertEqual(imported["auto_approved"], 1)
        self.assertFalse(imported["activated"])
        report = imported["report"]
        self.assertEqual(report["total_spoken_records"], len(self.inventory.targets))
        self.assertEqual(report["imported_total"], 1)
        self.assertEqual(report["untranslated_total"],
                         len(self.inventory.targets) - 1)
        self.assertEqual(report["by_source"][0]["source"], "classicua")
        self.assertEqual(report["by_source"][0]["imported_translations"], 1)
        self.assertEqual(report["verified_source_to_target_bindings"], 1)
        self.assertEqual(report["machine_one_to_one_imported"], 0)
        self.assertEqual(state.machine_imports.current_import_targets(), set())
        self.assertEqual(state.translation_action("auto_import_one_to_one",
                           {"source": "classicua"})["auto_approved"], 0)
        self.assertFalse(state.translation_action("auto_import_one_to_one",
                           {"source": "classicua"})["changed"])
        self.assertFalse(report["saved_to_git"])

    def test_shared_faction_variant_does_not_auto_import(self):
        policy = SourcePolicy.from_mapping({"schema_version": 2, "sources": [
            {"name": "classicua", "save_translations": True,
             "auto_approve_one_to_one": True}]})
        state = self.new_state(policy=policy)
        state.approve_mapping(self.request)
        result = state.translation_action("auto_import_one_to_one",
                                          {"source": "classicua"})
        self.assertEqual(result["auto_approved"], 0)
        self.assertEqual(result["imported"], 0)
        self.assertEqual(result["report"]["unreviewed_one_to_one_candidates"], 0)
        self.assertEqual(state.translation_page()["versions"][0]["status"], "pending")

    def test_bulk_one_to_one_rejects_disabled_policy_and_invalid_source(self):
        with self.assertRaisesRegex(ValueError, "not_enabled"):
            self.state.translation_action("auto_import_one_to_one",
                                          {"source": "classicua"})
        self.assertEqual(self.state.translations.file.data["versions"], [])
        policy = SourcePolicy.from_mapping({"schema_version": 2, "sources": [
            {"name": "classicua", "save_translations": True,
             "auto_approve_one_to_one": True}]})
        self.state.policy = policy
        for bad in ({}, {"source": "another"}, {"source": "classicua", "force": True}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.state.translation_action("auto_import_one_to_one", bad)

    def test_mapping_requires_independent_reviewers_and_exact_proof(self):
        for change in ({"mapping_reviewer": self.request["proof"]["evidence_reviewer"]},
                       {"proof": self.request["proof"] | {"facts": {}}},
                       {"proof": self.request["proof"] | {"source_blob_sha256": "f" * 64}},
                       {"proof": self.request["proof"] | {"target_context_sha256": "f" * 64}},
                       {"proof": {}}, {"target_id": "q:999:accept"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.state.approve_mapping(self.request | change)
        self.assertEqual(self.state.reviews, ())
        self.assertFalse((self.base / "stage3-ui-reviews.json").exists())

    def test_rejected_mapping_cannot_be_approved_deferred_requires_full_proof(self):
        self.state.decide(self.unit.source_id, "q:42:accept", "rejected", "wrong_speaker", "Invented reviewer")
        with self.assertRaises(ValueError):
            self.state.approve_mapping(self.request)
        self.assertEqual(self.state.translation_page()["versions"], [])
        # Use a separate synthetic session for a deferred mapping.
        other = self.base / "other"
        state = LocalReviewState(self.dataset, self.source, self.inventory, self.originals,
                                  other / "decisions.json", other)
        state.decide(self.unit.source_id, "q:42:accept", "deferred", "insufficient_evidence", "Invented reviewer")
        self.assertTrue(state.approve_mapping(self.request)["identity_approved"])
        self.assertEqual(state.page()["summary"]["human_stage3_approved_joins"], 1)
        self.assertEqual(state.decisions["decisions"][0]["decision"], "deferred")

    def test_no_content_review_without_proven_identity_and_no_duplicate_joins(self):
        self.state.translation_action("refresh", {})
        self.assertEqual(self.state.translation_page()["versions"], [])
        with self.assertRaises(ValueError):
            self.state.translation_action("decide", {"identity": "f" * 64, "decision": "approved",
                         "reviewer": "Invented reviewer", "checks": CHECKS})
        self.state.approve_mapping(self.request)
        with self.assertRaises(ValueError):
            self.state.approve_mapping(self.request)

    def test_import_revalidates_effective_field_and_target_context(self):
        identity = self.approve_and_collect()
        self.state.translation_action("decide", {"identity": identity, "decision": "approved",
                         "reviewer": "Invented reviewer", "checks": CHECKS})
        self.state.dataset = Fixture().add("quest_both", "classic", '{[42]={nil,"tampered invented text"}}').dataset
        with self.assertRaises(ValueError):
            self.state.translation_action("import", {})
        self.assertEqual(self.state.translations.file.data["imports"], [])
        self.state.dataset = self.dataset
        contexts = deepcopy(self.inventory.contexts)
        contexts["q:42:accept"][0]["voice"] = "changed invented voice"
        self.state.inventory = replace(self.inventory, contexts=contexts)
        with self.assertRaises(ValueError):
            self.state.translation_action("import", {})

    def test_policy_english_first_mock_and_disabled_storage(self):
        self.state.approve_mapping(self.request)
        for policy in (SourcePolicy(()), SourcePolicy(("original_english", "classicua")),
                       SourcePolicy(("own_translator", "original_english"))):
            self.state.policy = policy
            self.assertEqual(self.state.translation_observations(), [])
        self.state.policy = SourcePolicy(("own_translator", "classicua"), (("classicua", False),))
        self.assertEqual(len(self.state.translation_observations()), 1)
        self.state.translation_action("refresh", {})
        self.assertEqual(self.state.translation_page()["versions"], [])
        self.assertFalse(self.state.translation_page()["current_candidates"][0]["stored_locally"])

    def test_review_discovers_all_providers_and_imports_approved_lower_priority(self):
        """An unreviewed higher-priority result must not hide approved later content."""
        from adapters.translation_approvals import text_sha
        self.state.approve_mapping(self.request)
        self.state.policy = SourcePolicy(("classicua", "another", "original_english"))
        lower_text = "Вигаданий переклад із другого джерела."
        class SecondProvider:
            def lookup(self, request):
                return TranslationCandidate(
                    lower_text, "another", "synthetic/other.lua", "synthetic-revision",
                    "b" * 64, text_sha(lower_text), "reviewed",
                    CandidateState.NEEDS_REVIEW)
        with patch("adapters.review_ui.AlternativeSourceStub", SecondProvider):
            observations = self.state.translation_observations()
            self.assertEqual([o.candidate.provider for o in observations],
                             ["classicua", "another"])
            self.state.translation_action("refresh", {})
            versions = self.state.translation_page()["versions"]
            self.assertEqual(len(versions), 2)
            lower = next(row for row in versions
                         if row["provenance"][0]["provider"] == "another")
            self.state.translation_action("decide", {
                "identity": lower["id"], "decision": "approved",
                "reviewer": "Actual reviewer", "checks": CHECKS})
            imported = self.state.translation_action("import", {})
            self.assertEqual(imported["imported"], 1)
            selected = self.state.translations.file.data["imports"][0]
            self.assertEqual(selected["version_id"], lower["id"])
            self.assertEqual(sum(row["status"] == "pending"
                                 for row in self.state.translation_page()["versions"]), 1)

    def test_review_discovery_respects_explicit_english_boundary(self):
        self.state.approve_mapping(self.request)
        self.state.policy = SourcePolicy(("original_english", "classicua", "another"))
        self.assertEqual(self.state.translation_observations(), [])

    def test_corrupt_or_conflicting_local_mapping_files_refused(self):
        self.state.approve_mapping(self.request)
        with self.assertRaises(ValueError):
            self.new_state(reviews=(self.review,))
        path = self.base / "stage3-ui-reviews.json"
        data = json.loads(path.read_text())
        data["decisions"][0]["evidence"]["evidence_reviewer"] = data["decisions"][0]["decision"]["review_by"]
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.new_state()

    def test_changed_proof_files_and_originals_refuse_import(self):
        identity = self.approve_and_collect()
        self.state.translation_action("decide", {"identity": identity, "decision": "approved",
                         "reviewer": "Invented reviewer", "checks": CHECKS})
        path = self.base / "stage3-ui-reviews.json"
        path.write_text(json.dumps(review_file([])))
        with self.assertRaisesRegex(ValueError, "conflict"):
            self.state.translation_action("import", {})
        self.assertEqual(self.state.translations.file.data["imports"], [])

    def test_changed_external_review_input_and_strict_stage3_schema(self):
        path = self.base / "external-reviews.json"
        self.base.mkdir(parents=True)
        path.write_text(json.dumps(review_file([self.review])))
        state = self.new_state(reviews=(self.review,), reviews_input_file=path)
        state.translation_action("refresh", {})
        path.write_text(json.dumps(review_file([])))
        with self.assertRaisesRegex(ValueError, "stage3_input_changed"):
            state.translation_action("import", {})
        for bad in ({"schema_version": True, "decisions": []},
                    {"schema_version": 1, "decisions": {}}, None):
            with self.assertRaises(ValueError):
                load_reviews(bad, source_inventories={self.source.revision: self.source})

    def test_input_reaudit_is_required_before_mapping_and_content_writes(self):
        def fail():
            raise ValueError("synthetic changed pinned input")
        self.state.revalidate_inputs = fail
        with self.assertRaisesRegex(ValueError, "changed pinned input"):
            self.state.approve_mapping(self.request)
        self.state.revalidate_inputs = None
        self.approve_and_collect()
        self.state.revalidate_inputs = fail
        with self.assertRaisesRegex(ValueError, "changed pinned input"):
            self.state.translation_action("import", {})
        self.assertEqual(self.state.translations.file.data["imports"], [])

    def test_http_approval_routes_reject_csrf_unknown_fields_and_malformed_proofs(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(self.state, "token", 0))
        port = server.server_address[1]
        server.RequestHandlerClass = create_handler(self.state, "token", port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join()))
        base = f"http://127.0.0.1:{port}"
        def post(route, body, headers=None):
            return urlopen(Request(base + route, data=body, method="POST", headers=headers or {
                "Content-Type": "application/json", "Origin": base, "X-Review-Token": "token"}), timeout=5)
        for route in ("/api/mapping/approve", "/api/translations/refresh", "/api/translations/edit",
                      "/api/translations/decide", "/api/translations/import",
                      "/api/translations/auto_import_one_to_one"):
            with self.subTest(route=route), self.assertRaises(HTTPError) as error:
                post(route, b'{}', {"Content-Type": "application/json", "Origin": base})
            self.assertEqual(error.exception.code, 403)
        for headers in (
            {"Content-Type": "text/plain", "Origin": base, "X-Review-Token": "token"},
            {"Content-Type": "application/json", "Origin": base, "X-Review-Token": "token", "Transfer-Encoding": "chunked"},
            {"Content-Type": "application/json", "Origin": base, "X-Review-Token": "token", "Host": "evil.example"},
        ):
            try:
                post("/api/translations/import", b'{}', headers)
            except HTTPError as error:
                self.assertIn(error.code, (400, 403))
            except OSError as error:
                # Early rejection of a chunked request can close the socket
                # before urllib finishes sending its body (BrokenPipeError).
                # This is a safe fail-closed behavior, not server acceptance.
                if headers.get("Transfer-Encoding") != "chunked":
                    raise
                self.assertIn("Broken pipe", str(error))
            else:
                self.fail("invalid HTTP headers were accepted")
        for body in (b'{}', b'{"schema_version":1,"schema_version":1}',
                     json.dumps(self.request | {"proof": {}}).encode()):
            with self.assertRaises(HTTPError) as error:
                post("/api/mapping/approve", body)
            self.assertEqual(error.exception.code, 400)
        with self.assertLogs("spoken.review_ui", level="INFO") as emitted:
            with post("/api/mapping/approve", json.dumps(self.request).encode()) as response:
                self.assertTrue(json.load(response)["identity_approved"])
        self.assertTrue(any("mapping.approve succeeded" in row for row in emitted.output))
        self.assertFalse(any("invented wording" in row or "Invented mapping reviewer" in row
                             for row in emitted.output))
        with post("/api/translations/refresh", b'{}') as response:
            self.assertTrue(json.load(response)["saved"])
        with urlopen(base + "/api/translations", timeout=5) as response:
            row = json.load(response)["versions"][0]
        with self.assertRaises(HTTPError) as incomplete:
            post("/api/translations/decide", json.dumps({"identity": row["id"],
                 "decision": "approved", "reviewer": "Invented reviewer",
                 "checks": CHECKS | {"rights": False}}).encode())
        self.assertEqual(incomplete.exception.code, 400)
        self.assertEqual(json.load(incomplete.exception.fp)["reason"],
                         "explicit_content_attestation_required")
        with urlopen(base + "/api/translations", timeout=5) as response:
            self.assertEqual(json.load(response)["versions"][0]["status"], "pending")
        with post("/api/translations/decide", json.dumps({"identity": row["id"], "decision": "approved",
                  "reviewer": "Invented reviewer", "checks": CHECKS}).encode()) as response:
            self.assertTrue(json.load(response)["saved"])
        with urlopen(base + "/api/translations", timeout=5) as response:
            after_approval = json.load(response)["versions"][0]
            self.assertEqual(after_approval["status"], "approved")
            self.assertEqual(after_approval["id"], row["id"])
            self.assertFalse(after_approval["imported"])
        with post("/api/translations/import", b'{}') as response:
            self.assertEqual(json.load(response)["imported"], 1)
        for route, body, expected in (("/api/translations/import?x=1", b'{}', 404),
                                       ("/api/translations/edit", b'{"text":"bad"}', 400),
                                       ("/api/translations/import", b'x' * 262145, 413)):
            with self.assertRaises(HTTPError) as error:
                post(route, body)
            self.assertEqual(error.exception.code, expected)


if __name__ == "__main__":
    unittest.main()
