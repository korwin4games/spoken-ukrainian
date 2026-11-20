"""Local HTTP Gossip Translation Review; no third-party bodies or network."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tools.review_ui_server import create_handler
from tools.gossip_translation_review import GossipReviews, discover_groups
from tools.gossip_coverage import classicua_hash
from tools.build_ukrainian import GOSSIP_MODULE
from tools.manager_review import apply_review
from tools.gossip_translation_review import CHECKS, version_status

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
            state = SimpleNamespace(revalidate_inputs=lambda: None,
                                    inventory=SimpleNamespace(revision=spoken),
                                    source=SimpleNamespace(revision=classicua))
            identity = "fixture-gossip"
            hashed = classicua_hash(english)
            def action(name, payload):
                if payload.get("module") != GOSSIP_MODULE or payload.get("identity") != identity:
                    raise ValueError("manager_item_not_found")
                choices = [{"review_id": v["id"], "review_kind": "gossip", "text": v["text"],
                            "review": version_status(v)} for v in reviews.file.data["versions"]]
                row = {"id": identity, "npc_id": 42, "english_hash": hashed,
                       "originals": [english], "mapping_state": "mapping_pending", "candidates": choices}
                if name == "detail":
                    return row
                with patch("tools.manager_review.read_pinned_corpus", return_value=source), patch(
                        "tools.manager_review.local_gossip_texts", return_value=existing), patch(
                        "tools.manager_review.GossipReviews", return_value=reviews):
                    apply_review(name, {k: v for k, v in payload.items() if k != "module"},
                                 GOSSIP_MODULE, row, state, None, None)
                return {"saved": True, "imported": reviews.import_approved() if name == "confirm_candidate" else 0}
            manager = SimpleNamespace(action=action)
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0), create_handler("token", 0, manager))
            port = server.server_address[1]
            server.RequestHandlerClass = create_handler("token", port, manager)
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
                record = {"module": GOSSIP_MODULE, "identity": identity}
                with post("/api/manager/detail", record) as resp:
                    detail = json.load(resp)
                self.assertEqual(detail["originals"], [english])
                self.assertEqual(detail["npc_id"], 42)
                reviewer = record | {"reviewer": "human", "confirm": True}
                text = "Синтетичний переклад."
                draft = reviewer | {"candidate": "", "text": text}
                with self.assertRaises(HTTPError) as err:
                    post("/api/manager/save_translation", draft,
                         headers={"Content-Type": "application/json", "Origin": base})
                self.assertEqual(err.exception.code, 403)
                with post("/api/manager/save_translation", draft) as resp:
                    self.assertEqual(json.load(resp)["imported"], 0)
                version_id = reviews.file.data["versions"][0]["id"]
                self.assertEqual(reviews.imported_by_npc(existing), {})
                with self.assertRaises(HTTPError) as err:
                    post("/api/manager/confirm_candidate",
                         reviewer | {"candidate": version_id, "checks": dict.fromkeys(CHECKS, False)})
                self.assertEqual(err.exception.code, 400)
                self.assertEqual(reviews.imported_by_npc(existing), {})
                with post("/api/manager/confirm_candidate",
                          reviewer | {"candidate": version_id, "checks": dict.fromkeys(CHECKS, True)}) as resp:
                    self.assertEqual(json.load(resp)["imported"], 1)
                self.assertEqual(reviews.imported_by_npc(existing)[42][classicua_hash(english)],
                                 "Синтетичний переклад.")
                self.assertEqual(reviews.decide(version_id, "rejected", "human", dict.fromkeys(CHECKS, False)),
                                 "rejected")
                self.assertEqual(reviews.imported_by_npc(existing), {})
                with urlopen(base + "/", timeout=5) as resp:
                    html = resp.read().decode("utf-8")
                    self.assertIn(GOSSIP_MODULE, html)
                    self.assertIn('id="selected"', html)
                with urlopen(base + "/manager.js", timeout=5) as resp:
                    script = resp.read().decode("utf-8")
                    self.assertNotIn(".innerHTML", script)
                    self.assertNotIn("confirm_candidate", script)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)

if __name__ == "__main__":
    unittest.main()
