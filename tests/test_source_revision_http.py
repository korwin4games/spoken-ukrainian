"""Synthetic localhost source conflict reviewer and CSRF/attestation gates."""
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from adapters.source_revision_store import SourceReviewStore, CHECKS
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
                policy=SimpleNamespace(sources=("classicua", "another")))
            server = ThreadingHTTPServer(("127.0.0.1", 0),
                create_handler(state, "token", 0, source_reviews=reviews,
                               source_trusted=trusted))
            port = server.server_address[1]
            server.RequestHandlerClass = create_handler(state, "token", port,
                                    source_reviews=reviews, source_trusted=trusted)
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
                with urlopen(host + "/api/source-reviews?offset=0&limit=20", timeout=5) as response:
                    listing = json.load(response)
                self.assertEqual(listing["conflicts"], 1)
                self.assertEqual(listing["total"], 1)
                self.assertEqual(len(listing["revisions"]), 2)
                candidate_id = next(c["id"] for c in listing["items"][0]["candidates"]
                                    if c["provider"] == "another")
                with self.assertRaises(HTTPError) as err:
                    post("/api/source-reviews/activate",
                         {"candidate_id": candidate_id, "reviewer": "human"})
                self.assertEqual(err.exception.code, 400)
                with self.assertRaises(HTTPError) as err:
                    post("/api/source-reviews/decide", {"candidate_id": candidate_id,
                        "decision": "approved", "reviewer": "human",
                        "checks": {k: True for k in CHECKS}}, token=False)
                self.assertEqual(err.exception.code, 403)
                with self.assertRaises(HTTPError) as err:
                    post("/api/source-reviews/decide", {"candidate_id": candidate_id,
                        "decision": "approved", "reviewer": "human",
                        "checks": {k: False for k in CHECKS}})
                self.assertEqual(err.exception.code, 400)
                with post("/api/source-reviews/decide", {"candidate_id": candidate_id,
                    "decision": "approved", "reviewer": "human",
                    "checks": {k: True for k in CHECKS}}) as response:
                    self.assertEqual(json.load(response)["status"], "approved")
                self.assertEqual(reviews.active(trusted), [])
                with post("/api/source-reviews/activate",
                          {"candidate_id": candidate_id, "reviewer": "human"}) as response:
                    self.assertTrue(json.load(response)["selected"])
                self.assertEqual(reviews.active(trusted)[0]["provider"], "another")
                with urlopen(host + "/api/source-reviews", timeout=5) as response:
                    after = json.load(response)
                self.assertEqual(after["items"][0]["selected_candidate_id"], candidate_id)
                with urlopen(host + "/", timeout=5) as response:
                    html = response.read().decode("utf-8")
                    self.assertIn("Source Revision Review", html)
                with urlopen(host + "/app.js", timeout=5) as response:
                    script = response.read().decode("utf-8")
                    self.assertNotIn(".innerHTML", script)
                    self.assertIn("/api/source-reviews/", script)
                with post("/api/source-reviews/clear", {
                     "domain": "gossip", "target_id": target,
                     "reviewer": "human"}) as response:
                    self.assertFalse(json.load(response)["selected"])
                self.assertEqual(reviews.active(trusted), [])
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
