"""Local HTTP Gossip Translation Review; no third-party bodies or network."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tools.review_ui_server import create_handler
from tools.gossip_translation_review import GossipReviews, discover_groups
from tools.gossip_coverage import classicua_hash

class GossipReviewHTTPTests(unittest.TestCase):
    def test_authentic_review_roundtrip_is_separate_from_quest_ui(self):
        english = "Example greeting."
        spoken = "a" * 40
        classicua = "b" * 40
        source = [{"source": "gossip", "npcType": "creature", "npcId": 42,
                   "npcName": "Synthetic speaker", "originalText": english}]
        existing = {"byNpc": {}, "common": {}}
        groups, _ = discover_groups(source, existing, spoken, classicua)
        with TemporaryDirectory() as directory:
            root = Path(directory) / "build"
            reviews = GossipReviews(groups, spoken, classicua,
                                    root / "gossip.json", root)
            state = SimpleNamespace(revalidate_inputs=lambda: None)
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0), create_handler(state, "token", 0, reviews))
            port = server.server_address[1]
            server.RequestHandlerClass = create_handler(state, "token", port, reviews)
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            self.addCleanup(lambda: None)
            base = f"http://127.0.0.1:{port}"
            def post(path, payload, headers=None):
                return urlopen(Request(base + path,
                     data=json.dumps(payload).encode("utf-8"),
                     headers=headers or {"Content-Type": "application/json",
                                          "X-Review-Token": "token", "Origin": base},
                     method="POST"), timeout=5)
            try:
                with urlopen(base + "/api/gossip?offset=0&limit=12", timeout=5) as resp:
                    queue = json.load(resp)
                self.assertEqual(queue["total"], 1)
                self.assertEqual(queue["items"][0]["english"], english)
                self.assertEqual(queue["items"][0]["contexts"][0]["npc_id"], 42)
                with self.assertRaises(HTTPError) as err:
                    post("/api/gossip/import", {}, headers={"Content-Type": "application/json",
                                                             "Origin": base})
                self.assertEqual(err.exception.code, 403)
                group = queue["items"][0]
                payload = {k: group[k] for k in
                           ("group_id", "english_sha256", "context_sha256")}
                payload.update({"ukrainian_text": "Синтетичний переклад.",
                                "provider": "manual"})
                with post("/api/gossip/propose", payload) as resp:
                    proposed = json.load(resp)
                self.assertEqual(proposed["added"], 1)
                version_id = proposed["version_id"]
                self.assertEqual(reviews.imported_by_npc(existing), {})
                with self.assertRaises(HTTPError) as err:
                    post("/api/gossip/decide", {"version_id": version_id,
                        "decision": "approved", "reviewer": "human",
                        "checks": {k: False for k in
                            ("text", "grammar", "ai", "rights", "all_contexts")}})
                self.assertEqual(err.exception.code, 400)
                with post("/api/gossip/decide", {"version_id": version_id,
                     "decision": "approved", "reviewer": "human",
                     "checks": {k: True for k in
                         ("text", "grammar", "ai", "rights", "all_contexts")}}) as resp:
                    self.assertEqual(json.load(resp)["status"], "approved")
                self.assertEqual(reviews.imported_by_npc(existing), {})
                with post("/api/gossip/import", {}) as resp:
                    self.assertEqual(json.load(resp)["imported"], 1)
                self.assertEqual(reviews.imported_by_npc(existing)[42][classicua_hash(english)],
                                 "Синтетичний переклад.")
                with post("/api/gossip/decide", {"version_id": version_id,
                     "decision": "rejected", "reviewer": "human",
                     "checks": {k: False for k in
                         ("text", "grammar", "ai", "rights", "all_contexts")}}) as resp:
                    self.assertEqual(json.load(resp)["status"], "rejected")
                self.assertEqual(reviews.imported_by_npc(existing), {})
                with urlopen(base + "/", timeout=5) as resp:
                    html = resp.read().decode("utf-8")
                    self.assertIn("Gossip Translation Review", html)
                    self.assertIn('id="gossip-versions"', html)
                with urlopen(base + "/app.js", timeout=5) as resp:
                    script = resp.read().decode("utf-8")
                    self.assertNotIn(".innerHTML", script)
                    self.assertIn('"/api/gossip/" + route', script)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)

if __name__ == "__main__":
    unittest.main()
