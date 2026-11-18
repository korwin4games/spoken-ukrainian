"""Unified manager inventory, sandboxed promotion and HTTP/CLI parity."""
from contextlib import redirect_stdout
from hashlib import sha256
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from adapters.import_statistics import store_successful_build
from adapters.sqlite_translation_store import connection, DB_ENV, SQLiteDocument
from tools import build_ukrainian as builder
from tools.manager_inventory import ModuleInventory, latest_units, load_inventory
from tools.review_ui_server import create_handler
from tools.translation_manager import MODULE, ManagerUI, db_stamp, main, reimport, reset_test_state


def row(identity, kind, label, status, *, built=False, recorded=False, english="", ukrainian=""):
    return dict(id=identity, type=kind, label=label, status=status, originals=[english] if english else [],
                candidates=[{"text": ukrainian}] if ukrainian else [], recorded=recorded,
                built={"route": "machine_1to1"} if built else None)


class ManagerTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.archive = self.root / "local.zip"
        self.db = self.root / "test.sqlite3"
        self.paths = (self.root / "ClassicUA", self.root / "spoken")
        self.view = ModuleInventory([
            row("q:42:accept", "quest", "Invented quest", "ready", built=True,
                english="Hello, $N!", ukrainian="Вітаю, {ім'я}!"),
            row("gossip:3:27:a", "gossip", "Fixture NPC", "missing", english="Which way?"),
            row("q:43:progress", "quest", "Road", "conflict", recorded=True),
        ], {"sha256": "fixture"}, {("gossip_common", "common:27"): {}})
        for name in ("ARCHIVE", "DIST"):
            stub = patch.object(builder, name, self.archive if name == "ARCHIVE" else self.root)
            stub.start()
            self.addCleanup(stub.stop)

    def fake_build(self, classicua, spoken, *, prepare, destination, skipped):
        self.assertEqual((classicua, spoken), self.paths)
        artifact, digest = builder.write_zip({"Spoken_Quests_UA/Translations.lua":
                'local sample = "Вітаю, {ім\'я}!"'.encode()}, destination)
        import os
        inventory = store_successful_build(os.environ[DB_ENV], artifact_sha256=digest,
            spoken_revision="a" * 40, classicua_revision="b" * 40,
            rows=[{"domain": "quests", "unit": "42:accept", "entity": "42",
                   "source": "classicua", "route": "machine_1to1"}])
        return {"artifact": artifact, "sha256": digest, "import_inventory": inventory}

    def test_inventory_search_filters_pages_and_missing_details(self):
        self.assertEqual(self.view.page()["total"], 3)
        self.assertEqual(self.view.page(filter_by="not_imported")["total"], 2)
        items = self.view.page(filter_by="not_imported", limit=1)["items"]
        self.assertEqual(items[0]["status"], "missing")
        self.assertEqual(self.view.page(filter_by="not_imported", offset=1, limit=1)["items"][0]["status"], "conflict")
        self.assertEqual(self.view.page(kind="gossip", query="npc which 3")["total"], 1)
        self.assertEqual(self.view.page(query="ВІТАЮ {ім'я}")["total"], 1)
        self.assertEqual(self.view.page(filter_by="imported")["total"], 1)
        self.assertTrue(self.view.page(filter_by="conflicts")["items"][0]["recorded"])
        missing = self.view.detail(identity="gossip:3:27:a")
        self.assertEqual(missing["originals"], ["Which way?"])
        self.assertEqual(missing["candidates"], [])
        self.assertIn("Перекладу", missing["help"])
        with self.assertRaisesRegex(ValueError, "invalid_filters"):
            self.view.page(module="Spoken_Readables")

    def test_catalog_joins_verified_placements_to_effective_common_unit(self):
        from adapters.crosswalk import digest
        from adapters.source_revision_store import sha
        from tools.gossip_coverage import classicua_hash
        from tools.gossip_translation_review import normalized

        english = "Welcome, $N!"
        hashed = classicua_hash(english)
        lines = [
            {"lineId": "q:42:accept", "source": "accept", "questTitle": "Invented quest"},
            {"lineId": "g:first", "source": "gossip", "npcId": 3, "npcType": "creature",
             "npcName": "Guide", "originalText": english},
            {"lineId": "g:missing", "source": "gossip", "npcId": 4, "npcType": "creature",
             "npcName": "Visitor", "originalText": "No translation"},
            {"lineId": "g:conflict", "source": "gossip", "npcId": 5, "npcType": "creature",
             "npcName": "Conflicted NPC", "originalText": english},
        ]
        empty = {"versions": [], "imports": []}
        state = SimpleNamespace(
            allowed_directory=self.root,
            source=SimpleNamespace(revision="b" * 40, units={}),
            inventory=SimpleNamespace(revision="a" * 40,
                targets={r["lineId"]: SimpleNamespace(family="quest" if r["source"] == "accept" else "gossip")
                         for r in lines},
                contexts={r["lineId"]: [{"wording_sha256": digest(r.get("originalText", "Hello"))}]
                          for r in lines}),
            original_index=SimpleNamespace(original_english={"q:42:accept": "Hello"}),
            policy=SimpleNamespace(auto_approves_one_to_one=lambda source: False),
            _hints=[], translation_observations=lambda: [],
            translations=SimpleNamespace(file=SimpleNamespace(data=empty),
                                         eligible=lambda *a, **kw: []),
            machine_imports=SimpleNamespace(file=SimpleNamespace(data=empty)),
        )
        placements = [{"npc_id": r["npcId"], "english_hash": classicua_hash(r["originalText"]),
                       "english_sha256": sha(normalized(r["originalText"])),
                       "target_id": f"gossip:common:{classicua_hash(r['originalText'])}",
                       "status": "untranslated" if r["npcId"] == 4 else "eligible"} for r in lines[1:]]
        self.archive.write_bytes(b"archive")
        stats = store_successful_build(self.db, artifact_sha256=sha256(b"archive").hexdigest(),
            spoken_revision="a" * 40, classicua_revision="b" * 40,
            rows=[{"domain": "gossip_common", "unit": f"common:{hashed}", "entity": "common",
                   "source": "classicua", "route": "agent_verified"},
                  {"domain": "gossip_excluded", "unit": f"npc:5:{hashed}", "entity": "5",
                   "source": "reviewed+source_selected", "route": "excluded"}])
        self.assertEqual(stats["total_text_records"], 1)
        self.assertEqual(stats["gossip_excluded_npc_hashes"], 1)
        with patch("tools.manager_inventory.read_pinned_corpus", return_value=lines), patch.object(
                builder, "local_gossip_texts", return_value={"byNpc": {}, "common": {hashed: "Вітаю, {ім'я}!"}}), patch(
                "tools.manager_inventory.GossipMachineImport.inspect", return_value=([], placements, 0, set(), empty)):
            result = load_inventory(*self.paths, self.db, self.archive, state=state)
        self.assertEqual(result.summary()["gossip"]["included"], 1)
        self.assertEqual(result.summary()["gossip"]["missing"], 1)
        self.assertEqual(result.summary()["gossip"]["conflicts"], 1)
        self.assertIsNone(result.page(filter_by="conflicts")["items"][0]["built"])
        self.assertEqual(result.summary()["gossip_archive_units"]["common_hashes"], 1)
        included = result.page(filter_by="imported")["items"][0]
        self.assertFalse(included["recorded"])
        self.assertIn("{ім'я}", result.detail(identity=included["id"])["candidates"][0]["text"])

    def test_scoped_preview_reset_and_repeat(self):
        with connection(self.db) as db:
            db.execute("CREATE TABLE unrelated(secret TEXT)")
            db.execute("INSERT INTO unrelated VALUES('leave me')")
            db.execute("INSERT INTO source_snapshots(provider, revision, content_sha256) VALUES('classicua', 'r', 'sha')")
            db.execute("""INSERT INTO source_candidates(id,snapshot_id,domain,target_id,english_sha256,
                context_sha256,ukrainian_text,text_sha256,source_ref)
                VALUES ('c',1,'gossip','gossip:3:27','en','ctx','Привіт','hash','origin')""")
            db.execute("""INSERT INTO source_candidate_decisions(candidate_id,decision,reviewer,checks_json)
                VALUES('c','rejected','tester','{}')""")
            db.execute("""INSERT INTO ledger_documents(ledger_name,payload,revision)
                VALUES ('stage4b-decisions.json','{}',4)""")
            old = db_stamp(db)
        untouched = self.root / "legacy.json"
        untouched.write_text("old offline evidence")
        with patch.object(builder, "build", side_effect=self.fake_build), patch(
                "tools.manager_inventory.load_inventory", return_value=self.view):
            preview = reimport(*self.paths, self.db, reset=True, dry_run=True)
            self.assertEqual(preview["build"], "preview")
            self.assertIsNone(preview["artifact"])
            self.assertFalse(self.archive.exists())
            with connection(self.db) as db:
                self.assertEqual(db_stamp(db), old)
            with self.assertRaisesRegex(ValueError, "confirmation_required"):
                reimport(*self.paths, self.db, reset=True)
            first = reimport(*self.paths, self.db, reset=True, confirm=True)
            second = reimport(*self.paths, self.db, reset=True, confirm=True)
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertFalse(second["inventory"]["new_snapshot"])
        self.assertEqual(untouched.read_text(), "old offline evidence")
        with connection(self.db) as db:
            self.assertEqual(db.execute("SELECT secret FROM unrelated").fetchone()[0], "leave me")
            self.assertEqual(db.execute("SELECT id FROM source_candidates").fetchone()[0], "c")
            self.assertFalse(db.execute("SELECT * FROM source_candidate_decisions").fetchall())
            self.assertEqual(db.execute("SELECT COUNT(*) FROM build_import_snapshots").fetchone()[0], 1)
            units, valid = latest_units(db, self.archive, "a" * 40, "b" * 40)
            self.assertIn(("quests", "42:accept"), units)
            self.assertIsNotNone(valid)
            self.archive.write_bytes(b"modified")
            units, valid = latest_units(db, self.archive, "a" * 40, "b" * 40)
            self.assertEqual((units, valid), ({}, None))

    def test_rollback_keeps_previous_archive_and_db_on_failure(self):
        self.archive.write_bytes(b"previous archive")
        checksum = self.archive.with_suffix(".zip.sha256")
        checksum.write_text("previous checksum")
        with connection(self.db) as db:
            before = db_stamp(db)
        with patch.object(builder, "build", side_effect=ValueError("pinned_sources_changed")):
            with self.assertRaisesRegex(ValueError, "pinned_sources_changed"):
                reimport(*self.paths, self.db, reset=True, confirm=True)
        import os
        replace = os.replace

        def break_publish(src, dest):
            if dest == checksum:
                raise OSError("disk write failed")
            return replace(src, dest)

        with patch.object(builder, "build", side_effect=self.fake_build), patch(
                "tools.manager_inventory.load_inventory", return_value=self.view), patch(
                "tools.translation_manager.os.replace", side_effect=break_publish):
            with self.assertRaisesRegex(OSError, "disk write failed"):
                reimport(*self.paths, self.db, reset=True, confirm=True)
        with connection(self.db) as db:
            self.assertEqual(db_stamp(db), before)
        self.assertEqual(self.archive.read_bytes(), b"previous archive")
        self.assertEqual(checksum.read_text(), "previous checksum")

    def test_reset_rejects_sqlite_path_in_sources_and_stale_writer(self):
        self.paths[0].mkdir()
        with self.assertRaisesRegex(ValueError, "unsafe_database_path"):
            reimport(*self.paths, self.paths[0] / "test.db", reset=True, confirm=True)
        path = self.root / "stage4b-decisions.json"
        empty = {"schema_version": 2, "decisions": []}
        doc = SQLiteDocument(self.db, path, empty, lambda data: data)
        with connection(self.db) as db:
            reset_test_state(db)
        with self.assertRaisesRegex(ValueError, "local_review_conflict"):
            doc.save(empty)

    def test_run_reports_legacy_test_zip_path_and_utf8(self):
        with patch.object(builder, "build", side_effect=self.fake_build), patch(
                "tools.manager_inventory.load_inventory", return_value=self.view):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["reimport", "--classicua", str(self.paths[0]),
                    "--spoken", str(self.paths[1]), "--db", str(self.db), "--confirm", "--json"]), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["artifact"], str(self.archive))
        self.assertEqual(payload["sha256"], sha256(self.archive.read_bytes()).hexdigest())
        with ZipFile(self.archive) as zipped:
            self.assertIn("{ім'я}", zipped.read("Spoken_Quests_UA/Translations.lua").decode())

    def test_http_contract_and_worker_cli_equivalence(self):
        manager = ManagerUI(*self.paths, self.db)
        http = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(None, "test", 0))
        self.addCleanup(http.server_close)
        port = http.server_address[1]
        http.RequestHandlerClass = create_handler(None, "test", port, manager=manager)
        worker = Thread(target=http.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 5)
        self.addCleanup(http.shutdown)
        url = f"http://127.0.0.1:{port}"

        def post(path, fields, *, token="test"):
            request = Request(url + "/api/manager/" + path, data=json.dumps(fields).encode(),
                              headers={"Content-Type": "application/json", "Origin": url,
                                       "X-Review-Token": token})
            with urlopen(request, timeout=10) as response:
                return json.load(response)

        with urlopen(url + "/", timeout=5) as response:
            body = response.read().decode()
        self.assertEqual(body.count("Переімпортувати Quest + Gossip"), 1)
        self.assertIn('href="/advanced"', body)
        with patch("tools.manager_inventory.load_inventory", return_value=self.view), patch.object(
                manager, "validate_checkouts", return_value=("fixture",)):
            self.assertEqual(post("list", {"module": MODULE, "kind": "gossip"})["total"], 1)
            self.assertEqual(post("detail", {"module": MODULE, "identity": "gossip:3:27:a"})["status"], "missing")
        with self.assertRaises(HTTPError) as error:
            post("reimport", {"module": MODULE, "confirm": True, "path": "/anything"})
        self.assertEqual(error.exception.code, 400)
        with self.assertRaises(HTTPError) as error:
            post("reimport", {"module": MODULE, "confirm": True}, token="wrong")
        self.assertEqual(error.exception.code, 403)

        def run_cli(args, **kwargs):
            result = io.StringIO()
            with redirect_stdout(result):
                exit_code = main(args[2:])
            return type("Result", (), {"stdout": result.getvalue(), "returncode": exit_code})()

        with patch.object(builder, "build", side_effect=self.fake_build), patch(
                "tools.manager_inventory.load_inventory", return_value=self.view), patch(
                "tools.translation_manager.subprocess.run", side_effect=run_cli) as worker_run:
            preview = post("reimport", {"module": MODULE, "reset": True, "dry_run": True})
        self.assertEqual(preview["build"], "preview")
        self.assertIn("--reset-test-data", worker_run.call_args.args[0])
        self.assertFalse(self.archive.exists())

        outcomes = [
            (SimpleNamespace(returncode=1, stdout=b"", stderr=b"PRIVATE STDERR"),
             "manager_reimport_worker_empty_response"),
            (SimpleNamespace(returncode=0, stdout=b"PRIVATE TEXT"),
             "manager_reimport_worker_invalid_response"),
            (SimpleNamespace(returncode=0, stdout=b'{"build":"success"}'),
             "manager_reimport_worker_invalid_response"),
            (SimpleNamespace(returncode=-9, stdout=b""),
             "manager_reimport_worker_terminated"),
            (SimpleNamespace(returncode=1, stdout=b'{"error":"private_reviewer_data"}'),
             "manager_reimport_failed"),
            (SimpleNamespace(returncode=1, stdout=b'{"error":"manager_state_changed_retry_reimport"}'),
             "manager_state_changed_retry_reimport"),
        ]
        for result, reason in outcomes:
            with self.subTest(reason=reason), patch(
                    "tools.translation_manager.subprocess.run", return_value=result):
                with self.assertRaises(HTTPError) as error:
                    post("reimport", {"module": MODULE, "confirm": True})
                self.assertEqual(error.exception.code, 400)
                self.assertEqual(json.load(error.exception)["reason"], reason)
        with patch("tools.translation_manager.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("private path", 600, stderr=b"PRIVATE")):
            with self.assertRaises(HTTPError) as error:
                post("reimport", {"module": MODULE, "confirm": True})
            self.assertEqual(json.load(error.exception)["reason"], "manager_reimport_timed_out_check_build")

    def test_cached_inventory_revalidates_both_source_repositories(self):
        def git(path, *args):
            return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()

        def commit(path, text):
            (path / "tracked").write_text(text)
            git(path, "add", "tracked")
            git(path, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
            return git(path, "rev-parse", "HEAD")

        pins = {}
        for name, path in zip(("classicua", "spoken"), self.paths):
            path.mkdir()
            git(path, "init", "-q")
            pins[name] = {"revision": commit(path, name), "files": {}}
        for name in ("tests", "config"):
            (self.root / name).mkdir()
        for path in ("config/translation_sources.json", "tests/stage3_sources.json"):
            (self.root / path).write_text("{}")
        lock = self.root / "sources.lock.json"
        lock.write_text(json.dumps(pins))
        manager = ManagerUI(*self.paths, self.db)
        with patch("tools.translation_manager.ROOT", self.root), patch(
                "tools.manager_inventory.load_inventory", return_value=self.view) as load:
            manager.action("list", {"module": MODULE})
            manager.action("detail", {"module": MODULE, "identity": "q:42:accept"})
            self.assertEqual(load.call_count, 1)
            (self.paths[0] / "tracked").write_text("dirty")
            with self.assertRaisesRegex(ValueError, "manager_classicua_checkout_invalid"):
                manager.action("list", {"module": MODULE})
            git(self.paths[0], "restore", "tracked")
            pins["spoken"]["revision"] = commit(self.paths[1], "new Spoken revision")
            with self.assertRaisesRegex(ValueError, "manager_spoken_checkout_invalid"):
                manager.action("list", {"module": MODULE})
            lock.write_text(json.dumps(pins))
            manager.action("list", {"module": MODULE})
            self.assertEqual(load.call_count, 2)
