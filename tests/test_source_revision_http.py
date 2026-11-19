"""Synthetic localhost source conflict reviewer and CSRF/attestation gates."""
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from adapters.source_revision_store import SourceReviewStore, CHECKS
from tools.build_ukrainian import GOSSIP_MODULE
from tools.manager_review import apply_review
from tools.source_revision_review import gossip_contexts
from tools.review_ui_server import create_handler


class SourceReviewHTTPTests(unittest.TestCase):
    def test_source_versions_are_visible_and_explicit_selection_needs_human_checks(self):
        originals = [{"source": "gossip", "npcType": "creature",
                      "npcId": 42, "npcName": "Synthetic NPC",
                      "originalText": "Hello traveler."}]
        trusted = gossip_contexts(originals)
        (domain, target), proof = next(iter(trusted.items()))
        def snapshot(provider, revision, translation):
            return {"provider": provider, "revision": revision,
                    "records": [{"domain": domain, "target_id": target,
                         "english_sha256": proof["english_sha256"],
                         "context_sha256": proof["context_sha256"],
                         "ukrainian_text": translation,
                         "source_ref": provider + ":unit-test"}]}
        with TemporaryDirectory() as root:
            reviews = SourceReviewStore(Path(root) / "review.sqlite3")
            reviews.ingest(snapshot("classicua", "a" * 40, "Ласкаво просимо"), trusted)
            reviews.ingest(snapshot("another", "b" * 40, "Вітаємо!"), trusted)
            state = SimpleNamespace(
                revalidate_inputs=lambda: None,
                inventory=SimpleNamespace(revision="c" * 40),
                source=SimpleNamespace(revision="a" * 40),
                policy=SimpleNamespace(sources=("classicua", "another")))
            def action(name, payload):
                self.assertEqual(name, "confirm_candidate")
                if payload.get("module") != GOSSIP_MODULE:
                    raise ValueError("manager_unknown_module")
                choices = [{"review_id": c["id"], "text": c["ukrainian_text"],
                            "review_kind": "source", "review": "pending"} for c in reviews.candidates()]
                row = {"id": target, "npc_id": 42, "english_hash": proof["english_hash"],
                       "originals": ["Hello traveler."], "mapping_state": "mapping_pending",
                       "candidates": choices}
                with patch("tools.manager_review.read_pinned_corpus", return_value=originals):
                    included = apply_review(name, {k: v for k, v in payload.items() if k != "module"},
                                            GOSSIP_MODULE, row, state, None, reviews.db_path)
                return {"text_sha256": included}
            manager = SimpleNamespace(action=action)
            server = ThreadingHTTPServer(("127.0.0.1", 0),
                create_handler("token", 0, manager))
            port = server.server_address[1]
            server.RequestHandlerClass = create_handler("token", port, manager)
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            host = f"http://127.0.0.1:{port}"
            def post(route, payload, token=True):
                headers = {"Content-Type": "application/json", "Origin": host}
                if token:
                    headers["X-Review-Token"] = "token"
                return urlopen(Request(host + route,
                    data=json.dumps(payload).encode("utf-8"), method="POST",
                    headers=headers), timeout=5)
            try:
                self.assertEqual(len(reviews.revisions()), 2)
                candidate = next(c for c in reviews.candidates() if c["provider"] == "another")
                candidate_id = candidate["id"]
                route = "/api/manager/confirm_candidate"
                payload = {"module": GOSSIP_MODULE, "identity": target, "candidate": candidate_id,
                           "reviewer": "human", "confirm": True, "checks": dict.fromkeys(CHECKS, True)}
                with self.assertRaises(HTTPError) as err:
                    post(route, payload | {"confirm": False})
                self.assertEqual(err.exception.code, 400)
                with self.assertRaises(HTTPError) as err:
                    post(route, payload, token=False)
                self.assertEqual(err.exception.code, 403)
                with self.assertRaises(HTTPError) as err:
                    post(route, payload | {"checks": dict.fromkeys(CHECKS, False)})
                self.assertEqual(err.exception.code, 400)
                self.assertEqual(reviews.active(trusted), [])
                with post(route, payload) as response:
                    self.assertEqual(json.load(response)["text_sha256"], candidate["text_sha256"])
                self.assertEqual(reviews.active(trusted)[0]["provider"], "another")
                self.assertEqual(reviews.active(trusted)[0]["id"], candidate_id)
                with urlopen(host + "/", timeout=5) as response:
                    html = response.read().decode("utf-8")
                    self.assertIn(GOSSIP_MODULE, html)
                with urlopen(host + "/manager.js", timeout=5) as response:
                    script = response.read().decode("utf-8")
                    self.assertNotIn(".innerHTML", script)
                    self.assertIn("confirm_candidate", script)
                self.assertFalse(reviews.clear_selection("gossip", target, "human", trusted)["selected"])
                self.assertEqual(reviews.active(trusted), [])
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
