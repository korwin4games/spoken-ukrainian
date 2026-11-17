"""Local metadata import statistics API never exposes private translation bodies."""
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from adapters.import_statistics import store_successful_build
from tools.review_ui_server import create_handler

A = "a" * 40
B = "b" * 40
SHA = "c" * 64


class ImportStatisticsHTTPTests(unittest.TestCase):
    def test_http_stats_are_live_and_not_private_text(self):
        with TemporaryDirectory() as root:
            db = Path(root) / "translations.sqlite3"
            state = SimpleNamespace()
            server = ThreadingHTTPServer(("127.0.0.1", 0),
                create_handler(state, "test-csrf", 0, import_db_path=db))
            port = server.server_address[1]
            server.RequestHandlerClass = create_handler(
                state, "test-csrf", port, import_db_path=db)
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            url = f"http://127.0.0.1:{port}/api/import-stats"
            try:
                with urlopen(url, timeout=5) as res:
                    empty = json.load(res)
                self.assertEqual(empty["recorded_imports"]["total_text_records"], 0)
                self.assertIsNone(empty["latest_successful_build"])
                store_successful_build(db, artifact_sha256=SHA,
                      spoken_revision=A, classicua_revision=B,
                      rows=[{"domain": "quests", "unit": "42:accept", "entity": "42",
                             "source": "classicua", "route": "machine_1to1"}])
                with urlopen(url, timeout=5) as res:
                    data = json.load(res)
                self.assertEqual(data["latest_successful_build"]["categories"]["quests"], 1)
                self.assertEqual(data["latest_successful_build"]["rows"][0]["source"], "classicua")
                self.assertNotIn("secret translation body", json.dumps(data))
                with self.assertRaises(HTTPError) as ctx:
                    urlopen(Request(url, headers={"Host": "attacker.example"}),
                            timeout=5)
                self.assertEqual(ctx.exception.code, 403)
                with urlopen(f"http://127.0.0.1:{port}/", timeout=5) as res:
                    html = res.read().decode()
                self.assertIn("Translation Import Statistics", html)
                with urlopen(f"http://127.0.0.1:{port}/app.js", timeout=5) as res:
                    script = res.read().decode()
                self.assertIn("spoken-import-stats-refresh", script)
                self.assertIn("/api/import-stats", script)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
