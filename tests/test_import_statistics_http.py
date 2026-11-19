"""Local metadata import statistics API never exposes private translation bodies."""
import json
from hashlib import sha256
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from adapters.import_statistics import store_successful_build
from adapters.sqlite_translation_store import connection
from tools.build_ukrainian import QUEST_MODULE, GOSSIP_MODULE
from tools.manager_inventory import ModuleInventory, latest_units
from tools.review_ui_server import create_handler

A = "a" * 40
B = "b" * 40


class ImportStatisticsHTTPTests(unittest.TestCase):
    def test_http_stats_are_live_and_not_private_text(self):
        with TemporaryDirectory() as root:
            db = Path(root) / "translations.sqlite3"
            artifact = Path(root) / "quest.zip"
            artifact.write_bytes(b"fixture")
            def read_stats(action, payload):
                self.assertEqual(action, "stats")
                module = payload["module"]
                with connection(db) as sqlite:
                    units, built = latest_units(sqlite, artifact, A, B, module)
                source_row = {"id": "q:42:accept", "type": "quest", "status": "ready",
                              "recorded": False, "built": units.get(("quests", "42:accept"))}
                return {"summary": ModuleInventory([source_row], built, units, module).summary(), "build": built}
            manager = SimpleNamespace(action=read_stats)
            server = ThreadingHTTPServer(("127.0.0.1", 0),
                create_handler("test-csrf", 0, manager))
            port = server.server_address[1]
            server.RequestHandlerClass = create_handler(
                "test-csrf", port, manager)
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            endpoint = f"http://127.0.0.1:{port}/api/import-stats"
            url = endpoint + "?module=" + QUEST_MODULE
            try:
                with urlopen(url, timeout=5) as res:
                    empty = json.load(res)
                self.assertEqual(empty["summary"]["quest"]["recorded"], 0)
                self.assertIsNone(empty["build"])
                store_successful_build(db, artifact_sha256=sha256(artifact.read_bytes()).hexdigest(),
                      module=QUEST_MODULE,
                      spoken_revision=A, classicua_revision=B,
                      rows=[{"domain": "quests", "unit": "42:accept", "entity": "42",
                             "source": "classicua", "route": "machine_1to1"}])
                with urlopen(url, timeout=5) as res:
                    data = json.load(res)
                self.assertEqual(data["summary"]["quest"]["included"], 1)
                self.assertEqual(data["build"]["sha256"], sha256(artifact.read_bytes()).hexdigest())
                self.assertNotIn("secret translation body", json.dumps(data))
                with urlopen(endpoint + "?module=" + GOSSIP_MODULE, timeout=5) as res:
                    self.assertIsNone(json.load(res)["build"])
                with self.assertRaises(HTTPError) as ctx:
                    urlopen(Request(url, headers={"Host": "attacker.example"}),
                            timeout=5)
                self.assertEqual(ctx.exception.code, 403)
                with urlopen(f"http://127.0.0.1:{port}/", timeout=5) as res:
                    html = res.read().decode()
                self.assertIn('id="metrics"', html)
                with urlopen(f"http://127.0.0.1:{port}/manager.js", timeout=5) as res:
                    script = res.read().decode()
                self.assertIn("metrics(data.summary, data.build)", script)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
