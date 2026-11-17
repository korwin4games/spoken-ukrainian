"""Synthetic local-only Stage 4B review UI tests (no copyrighted text)."""
from dataclasses import replace
from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import test_review_workbench as fixtures

from adapters.classicua.evidence import SourceInventory
from adapters.review_ui import LocalReviewState, guarded_decisions_path
from adapters.spoken.text_index import TextIndex
from tools.review_ui_server import create_handler


UK = "Вигадана локальна репліка."
EN = "Invented English"


class SyntheticDataset:
    def __init__(self, units):
        self.views = {"horde": {}, "alliance": {}}
        pos = {"accept": 2, "progress": 4, "complete": 5}
        for identity, unit in units.items():
            _, faction, quest, event = identity.split(":")
            if quest not in ("42", "43") or event not in pos:
                continue
            origin = SimpleNamespace(
                revision=unit.source_revision, file=unit.origin_file,
                layer=unit.origin_layer, sha256=unit.source_file_sha256)
            field = SimpleNamespace(node=SimpleNamespace(value=UK), origin=origin)
            self.views[faction].setdefault(int(quest), SimpleNamespace(fields={})
                    ).fields[(pos[event],)] = field

    def faction_views(self, include_ai=True):
        return self.views, []


class ReviewUITests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.WorkbenchTests()
        fixture.setUp()
        units = {
            k: replace(u, effective_sha256=sha256(UK.encode("utf-8")).hexdigest())
            for k, u in fixture.units.items()
        }
        self.source = SourceInventory(fixture.source.revision,
                                      fixture.source.files, units)
        self.inventory = fixture.inv
        self.dataset = SyntheticDataset(units)
        self.original_index = TextIndex({
            "q:42:accept": EN,
            "q:43:progress:w1": EN,
        }, (), {})
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / "build"
        self.decisions_file = self.base / "stage4b-decisions.json"
        self.state = LocalReviewState(
            self.dataset, self.source, self.inventory, self.original_index,
            self.decisions_file, self.base)

    def test_side_by_side_text_only_for_verified_targets(self):
        page = self.state.page("horde", 0, 10)
        self.assertEqual(page["scope"], "local_review_only_no_approval")
        self.assertEqual(len(page["items"]), 2)
        self.assertEqual(page["items"][0]["ukrainian_text"], UK)
        options = page["items"][1]["target_options"]
        self.assertEqual(options[0]["english_original"], EN)
        self.assertTrue(options[0]["english_verified"])
        self.assertIsNone(options[1]["english_original"])
        self.assertFalse(options[1]["english_verified"])
        self.assertEqual(page["summary"]["new_identity_approvals_created"], 0)
        self.assertEqual(page["summary"]["translation_content_approvals_created"], 0)

    def test_reject_persists_only_metadata_and_filters_target(self):
        response = self.state.decide(
            "quest:horde:43:progress", "q:43:progress:w1", "rejected",
            "wrong_speaker", "real-local-reviewer")
        self.assertTrue(response["saved"])
        self.assertFalse(response["identity_approved"])
        self.assertTrue(self.decisions_file.is_file())
        disk = self.decisions_file.read_text(encoding="utf-8")
        self.assertNotIn(UK, disk)
        self.assertNotIn(EN, disk)
        self.assertEqual(json.loads(disk)["schema_version"], 2)
        page = self.state.page("horde")
        item = next(x for x in page["items"]
                    if x["source_id"] == "quest:horde:43:progress")
        self.assertEqual([o["target_id"] for o in item["target_options"]],
                         ["q:43:progress:w2"])
        again = LocalReviewState(self.dataset, self.source, self.inventory,
                                 self.original_index, self.decisions_file, self.base)
        self.assertEqual(again.decisions["decisions"][0]["decision"], "rejected")
        with self.assertRaisesRegex(ValueError, "invalid_or_duplicate"):
            again.decide("quest:horde:43:progress", "q:43:progress:w1",
                         "deferred", "other", "reviewer-2")

    def test_deferred_candidate_stays_visible_no_approval(self):
        self.state.decide("quest:horde:42:accept", "q:42:accept",
                          "deferred", "insufficient_evidence", "reviewer-1")
        option = self.state.page()["items"][0]["target_options"][0]
        self.assertEqual(option["manual_decision"], "deferred")
        self.assertEqual(self.state.page()["summary"]["human_stage3_approved_joins"], 0)

    def test_reject_unverified_or_malformed_english_original(self):
        wrong = TextIndex({"q:42:accept": "unverified invented text"}, (), {})
        with self.assertRaisesRegex(ValueError, "unverified_spoken_original_text"):
            LocalReviewState(self.dataset, self.source, self.inventory, wrong,
                             self.decisions_file, self.base)

    def test_outside_directory_and_symlink_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "review_ui_decisions_must_be_under_build"):
            guarded_decisions_path(Path(self.tmp.name) / "wrong.json", self.base)
        self.base.mkdir(parents=True, exist_ok=True)
        symlink = self.base / "escape"
        symlink.symlink_to(Path(self.tmp.name), target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "review_ui_decisions_must_be_under_build"):
            guarded_decisions_path(symlink / "decisions.json", self.base)

    def test_bad_request_and_pagination_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "invalid_review_ui_page"):
            self.state.page("both")
        with self.assertRaisesRegex(ValueError, "invalid_review_ui_page"):
            self.state.page(offset=-1)
        with self.assertRaisesRegex(ValueError, "invalid_review_ui_page"):
            self.state.page(limit=100)
        with self.assertRaisesRegex(ValueError, "invalid_or_duplicate"):
            self.state.decide("quest:horde:42:accept", "q:42:accept",
                              "approved", "other", "fake-reviewer")

    def test_local_http_host_origin_and_csrf_controls(self):
        # Bind ephemeral loopback port for test and then install port-specific
        # HTTP handler. No network access beyond this local process.
        server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(self.state, "token", 0))
        port = server.server_address[1]
        server.RequestHandlerClass = create_handler(self.state, "token", port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join()))
        base = f"http://127.0.0.1:{port}"
        with urlopen(base + "/", timeout=5) as reply:
            html = reply.read().decode("utf-8")
            self.assertIn("Quest Mapping Review", html)
            self.assertIn("id=\"target-ref\"", html)
            self.assertEqual(reply.headers.get("X-Frame-Options"), "DENY")
        with urlopen(base + "/app.js", timeout=5) as reply:
            js = reply.read().decode("utf-8")
            self.assertIn("textContent", js)
            self.assertNotIn(".innerHTML", js)
            self.assertNotIn("insertAdjacentHTML(", js)
            self.assertIn("target_options[0]?.target_id", js)
        with urlopen(base + "/api/bootstrap", timeout=5) as reply:
            info = json.load(reply)
            self.assertEqual(info["csrf_token"], "token")
            self.assertEqual(reply.headers.get("Cache-Control"), "no-store")
            self.assertIsNone(reply.headers.get("Access-Control-Allow-Origin"))
        with urlopen(base + "/api/queue?faction=horde&limit=1", timeout=5) as reply:
            queue = json.load(reply)
            self.assertEqual(len(queue["items"]), 1)
            self.assertEqual(queue["items"][0]["ukrainian_text"], UK)
        bad_host = Request(base + "/api/bootstrap", headers={"Host": "evil.example"})
        with self.assertRaises(HTTPError) as error:
            urlopen(bad_host, timeout=5)
        self.assertEqual(error.exception.code, 403)
        payload = json.dumps({
            "source_id": "quest:horde:42:accept", "target_id": "q:42:accept",
            "decision": "deferred", "reason": "insufficient_evidence",
            "reviewer": "reviewer-a",
        }).encode("utf-8")
        for headers in (
            {"Content-Type": "application/json", "Origin": base},
            {"Content-Type": "application/json", "X-Review-Token": "token",
             "Origin": "http://attacker.example"},
        ):
            req = Request(base + "/api/decisions", data=payload,
                          headers=headers, method="POST")
            with self.assertRaises(HTTPError) as error:
                urlopen(req, timeout=5)
            self.assertEqual(error.exception.code, 403)
        req = Request(base + "/api/decisions", data=payload,
                      headers={"Content-Type": "application/json",
                               "X-Review-Token": "token", "Origin": base}, method="POST")
        with urlopen(req, timeout=5) as reply:
            result = json.load(reply)
            self.assertFalse(result["identity_approved"])
        self.assertNotIn(UK, self.decisions_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
