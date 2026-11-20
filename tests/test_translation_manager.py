"""Unified manager inventory, sandboxed promotion and HTTP/CLI parity."""
from contextlib import redirect_stdout
from hashlib import sha256
from http.server import ThreadingHTTPServer
import io
import json
import sqlite3
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event, Thread
from types import SimpleNamespace
import unittest
import tools.translation_manager as manager_module
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from adapters.import_statistics import store_successful_build
from adapters.sqlite_translation_store import connection, DB_ENV, SQLiteDocument
from tools import build_ukrainian as builder
from tools.manager_inventory import ModuleInventory, latest_units, load_inventory
from tools.review_ui_server import create_handler
from tools.translation_manager import (MODULE, ManagerUI, db_stamp, main, reimport,
                                       reset_test_state, wow_addons_destination)


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
        self.gossip_archive = self.root / "gossip.zip"
        self.archives = {MODULE: self.archive, builder.GOSSIP_MODULE: self.gossip_archive}
        for target, name, value in (
                (builder, "DIST", self.root), (manager_module, "ARCHIVES", self.archives)):
            stub = patch.object(target, name, value)
            stub.start()
            self.addCleanup(stub.stop)

    def fake_build(self, classicua, spoken, *, module, before_import, prepare, destination, skipped,
                   incremental=False):
        self.assertEqual((classicua, spoken), self.paths)
        artifact, digest = builder.write_zip({"Spoken_Quest_UA/Translations.lua":
                'local sample = "Вітаю, {ім\'я}!"'.encode()}, destination)
        import os
        inventory = store_successful_build(os.environ[DB_ENV], artifact_sha256=digest,
            spoken_revision="a" * 40, classicua_revision="b" * 40, module=module,
            rows=[{"domain": "quests", "unit": "42:accept", "entity": "42",
                   "source": "classicua", "route": "machine_1to1"}])
        return {"artifact": artifact, "sha256": digest, "import_inventory": inventory}

    def test_wow_path_appends_forever_addons_and_trims_trailing_separator(self):
        windows = "D:\\Games\\World of Warcraft"
        expected = windows + "\\_forever_\\Interface\\AddOns"
        self.assertEqual(wow_addons_destination(windows, platform="nt"), expected)
        self.assertEqual(wow_addons_destination(windows + "\\", platform="nt"), expected)
        self.assertEqual(wow_addons_destination(windows + "\\\\", platform="nt"), expected)
        self.assertEqual(wow_addons_destination(windows.replace("\\", "/") + "/",
                                                platform="nt"), expected)
        linux_root = str(self.root / "Game") + "/"
        self.assertEqual(wow_addons_destination(linux_root, platform="posix"),
                         str(self.root / "Game" / "_forever_" / "Interface" / "AddOns"))
        for bad in ("", " ", "World of Warcraft", "D:World of Warcraft",
                    "\\\\remote\\games\\World of Warcraft", "D:\\foo\\..\\bar",
                    "D:\\Games\\World of Warcraft\\_forever_", "D:\\Games\\WOW\x00"):
            with self.subTest(bad=bad), self.assertRaisesRegex(
                    ValueError, "manager_install_invalid_wow_path"):
                wow_addons_destination(bad, platform="nt")
        with self.assertRaisesRegex(ValueError, "manager_install_windows_path_on_non_windows"):
            wow_addons_destination(windows, platform="posix")

    def test_manager_install_existing_zip_creates_backup_and_preserves_upstream(self):
        from tools.install_addon import install
        wow_root = self.root / "World of Warcraft"
        addons = wow_root / "_forever_" / "Interface" / "AddOns"
        for name in ("Spoken", "Spoken_Quests"):
            folder = addons / name
            folder.mkdir(parents=True, exist_ok=True)
            (folder / (name + ".toc")).write_text("upstream", encoding="utf-8")
        for name in ("Spoken_Ukrainian", MODULE):
            folder = addons / name
            folder.mkdir()
            (folder / "old.lua").write_text("old content", encoding="utf-8")
        payload = builder.template_entries(builder.render_quest_lua({
            42: {"accept": {"text": "Вітаю", "reviewed": False, "quick": True}}},
            "a" * 40))
        archive, digest = builder.write_zip(payload, self.archive)
        store_successful_build(self.db, module=MODULE, artifact_sha256=digest,
            spoken_revision="a" * 40, classicua_revision="b" * 40,
            rows=[{"domain": "quests", "unit": "42:accept", "entity": "42",
                   "source": "manual", "route": "user_selected",
                   "text_sha256": sha256("Вітаю".encode()).hexdigest()}])
        manager = ManagerUI(*self.paths, self.db)
        self.addCleanup(manager.close)
        result = manager.action("install", {
            "module": MODULE, "wow_path": str(wow_root) + os.sep})
        self.assertEqual(result["addons"], str(addons))
        self.assertEqual(set(result["installed"]), {"Spoken_Ukrainian", MODULE})
        self.assertEqual(set(result["replaced"]), {"Spoken_Ukrainian", MODULE})
        self.assertTrue(Path(result["backup"]).is_dir())
        for name in ("Spoken_Ukrainian", MODULE):
            self.assertEqual((Path(result["backup"]) / name / "old.lua").read_text(), "old content")
            self.assertFalse((addons / name / "old.lua").exists())
        self.assertEqual((addons / MODULE / "Translations.lua").read_bytes(),
                         payload[MODULE + "/Translations.lua"])
        for name in ("Spoken", "Spoken_Quests"):
            self.assertEqual((addons / name / (name + ".toc")).read_text(), "upstream")

    def test_install_requires_tracked_zip_and_never_builds_implicitly(self):
        wow_root = self.root / "World of Warcraft"
        addons = wow_root / "_forever_" / "Interface" / "AddOns"
        addons.mkdir(parents=True)
        manager = ManagerUI(*self.paths, self.db)
        self.addCleanup(manager.close)
        with patch("tools.translation_manager.subprocess.run") as worker:
            with self.assertRaisesRegex(ValueError, "manager_install_module_not_built"):
                manager.action("install", {"module": MODULE, "wow_path": str(wow_root)})
            worker.assert_not_called()
        self.assertEqual(list(addons.iterdir()), [])
        with self.assertRaisesRegex(ValueError, "manager_invalid_options"):
            manager.action("install", {
                "module": MODULE, "wow_path": str(wow_root), "archive": "/tmp/other.zip"})
        with self.assertRaisesRegex(ValueError, "manager_install_addons_directory_missing"):
            manager.action("install", {"module": MODULE, "wow_path": str(self.root / "missing")})

    def test_manager_install_rejects_outdated_archive_without_replacing_addons(self):
        wow_root = self.root / "World of Warcraft"
        addons = wow_root / "_forever_" / "Interface" / "AddOns"
        addons.mkdir(parents=True)
        archive, digest = builder.write_zip(
            builder.template_entries(builder.render_quest_lua({
                42: {"accept": {"text": "A", "reviewed": False, "quick": True}}}, "a" * 40)),
            self.archive)
        store_successful_build(self.db, module=MODULE, artifact_sha256=digest,
                               spoken_revision="a" * 40, classicua_revision="b" * 40, rows=[])
        archive.write_bytes(archive.read_bytes() + b"corruption")
        manager = ManagerUI(*self.paths, self.db)
        self.addCleanup(manager.close)
        with self.assertRaisesRegex(ValueError, "manager_install_archive_outdated"):
            manager.action("install", {"module": MODULE, "wow_path": str(wow_root)})
        self.assertEqual(list(addons.iterdir()), [])

    def test_inventory_search_filters_pages_and_missing_details(self):
        self.assertEqual(self.view.page()["total"], 2)
        self.assertEqual(self.view.page(filter_by="not_imported")["total"], 1)
        items = self.view.page(filter_by="not_imported", limit=1)["items"]
        self.assertEqual(items[0]["status"], "conflict")
        gossip = ModuleInventory([row("gossip:3:27:a", "gossip", "Fixture NPC", "missing",
                                      english="Which way?")], None, {}, builder.GOSSIP_MODULE)
        self.assertEqual(gossip.page(module=builder.GOSSIP_MODULE, query="npc which 3")["total"], 1)
        self.assertEqual(self.view.page(query="ВІТАЮ {ім'я}")["total"], 1)
        self.assertEqual(self.view.page(filter_by="imported")["total"], 1)
        self.assertTrue(self.view.page(filter_by="conflicts")["items"][0]["recorded"])
        missing = gossip.detail(module=builder.GOSSIP_MODULE, identity="gossip:3:27:a")
        self.assertEqual(missing["originals"], ["Which way?"])
        self.assertEqual(missing["candidates"], [])
        self.assertIn("Перекладу", missing["help"])
        with self.assertRaisesRegex(ValueError, "invalid_filters"):
            self.view.page(module="Spoken_Readables")

    def test_candidate_conflicts_and_multiple_originals_have_separate_statistics_and_filters(self):
        conflict = self.view.rows["q:43:progress"]
        conflict.update(mapping_state="mapping_conflict",
                        candidates=[{"text": "Річка"}, {"text": "Дорога"}])
        multi = row("q:8:progress", "quest", "Invented variants", "multiple_originals")
        multi.update(mapping_state="mapping_conflict", originals=["First crossing", "Second crossing"])
        self.view.rows[multi["id"]] = multi
        summary = self.view.summary()
        self.assertEqual(summary["quest"]["conflicts"], 1)
        self.assertEqual(summary["quest"]["conflicting_candidates"], 1)
        self.assertEqual(summary["quest"]["multiple_originals"], 1)
        self.assertEqual(summary["quest"]["mapping_states"]["mapping_conflict"], 2)
        self.assertEqual(summary["quest"]["included"], 1)
        self.assertNotIn("gossip", summary)

        for filter_by, match, excluded, expected in (
                ("conflicts", "РІЧКА", "second crossing", conflict),
                ("multiple_originals", "second crossing", "річка", multi)):
            with self.subTest(filter_by=filter_by):
                self.assertEqual(self.view.page(filter_by=filter_by)["total"], 1)
                page = self.view.page(filter_by=filter_by, query=match, kind="quest", limit=1)
                self.assertEqual([item["id"] for item in page["items"]], [expected["id"]])
                self.assertEqual(self.view.page(filter_by=filter_by, query=excluded)["total"], 0)
        self.assertEqual(self.view.page(status="multiple_originals", query="first crossing")["total"], 1)
        self.assertEqual(self.view.page(status="mapping_conflict")["total"], 2)

    def test_catalog_joins_verified_placements_to_effective_common_unit(self):
        from adapters.crosswalk import digest
        from adapters.source_revision_store import sha
        from adapters.translation_agent import TranslationAgent, candidate
        from tools.gossip_coverage import classicua_hash
        from tools.gossip_translation_review import normalized

        english = "Welcome, $N!"
        hashed = classicua_hash(english)
        lines = [
            {"lineId": "q:42:accept", "source": "accept", "questTitle": "Invented quest"},
            {"lineId": "g:first", "source": "gossip", "npcId": 3, "npcType": "creature",
             "npcName": "Guide", "originalText": english},
            {"lineId": "g:missing", "source": "gossip", "npcId": 4, "npcType": "creature",
             "npcName": "Visitor", "originalText": "No translation", "text": english},
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
            module=builder.GOSSIP_MODULE,
            rows=[{"domain": "gossip_common", "unit": f"common:{hashed}", "entity": "common",
                   "source": "classicua", "route": "agent_verified"},
                  {"domain": "gossip_excluded", "unit": f"npc:5:{hashed}", "entity": "5",
                   "source": "reviewed+source_selected", "route": "excluded"}])
        self.assertEqual(stats["total_text_records"], 1)
        self.assertEqual(stats["gossip_excluded_npc_hashes"], 1)
        text = "Вітаю, {ім'я}!"
        target = f"gossip:common:{hashed}"
        def assessment(context):
            return candidate(domain="gossip", target_id=target, provider="classicua",
                revision="b" * 40, target_revision="a" * 40, original=english + "\n", text=text,
                context=context, provenance={"source_file": target}, identity=True, rights=True)
        current = [assessment("one")]
        TranslationAgent(self.db, lambda: current).run("one", candidate_ids=[current[0]["id"]])
        inputs = (None, state.source, state.inventory, state.original_index, lines)
        with patch("tools.manager_inventory.load_source_policy", return_value=state.policy), patch(
                "tools.review_ui_server.build_state", side_effect=AssertionError("Quest state loaded for Gossip")), patch.object(
                builder, "local_gossip_texts", return_value={"byNpc": {}, "common": {hashed: text}}), patch(
                "tools.manager_inventory.GossipMachineImport.inspect", return_value=([], placements, 0, set(), empty)), patch(
                "tools.translation_agent.evidence", side_effect=lambda *a, **k: current):
            result = load_inventory(*self.paths, self.db, self.archive, input_loader=lambda: inputs,
                                    module=builder.GOSSIP_MODULE)
            current[:] = [assessment("changed")]
            stale = load_inventory(*self.paths, self.db, self.archive, input_loader=lambda: inputs,
                                   module=builder.GOSSIP_MODULE)
        self.assertEqual(result.summary()["gossip"]["included"], 1)
        self.assertEqual(result.summary()["gossip"]["missing"], 1)
        self.assertEqual(result.summary()["gossip"]["unverified_alternatives"], 1)
        self.assertEqual(result.summary()["gossip"]["agent_warnings"], 1)
        self.assertEqual(result.summary()["gossip"]["conflicts"], 1)
        self.assertIsNone(result.page(module=builder.GOSSIP_MODULE, filter_by="conflicts")["items"][0]["built"])
        self.assertEqual(result.summary()["gossip_archive_units"]["common_hashes"], 1)
        included = result.page(module=builder.GOSSIP_MODULE, filter_by="imported")["items"][0]
        self.assertFalse(included["recorded"])
        assessed = result.detail(module=builder.GOSSIP_MODULE, identity=included["id"])["candidates"][0]
        self.assertIn("{ім'я}", assessed["text"])
        self.assertEqual(assessed["validation"], "needs_human_review")
        self.assertFalse(assessed["checks"]["line_breaks"])
        past = stale.detail(module=builder.GOSSIP_MODULE, identity=included["id"])["candidates"][0]
        self.assertEqual(past["validation"], "stale")
        self.assertNotIn("checks", past)

    def test_quest_multiple_originals_are_bound_to_their_contexts(self):
        from adapters.crosswalk import digest
        from adapters.spoken.text_index import TextIndex
        from test_stage3 import Fixture, synthetic_inventory
        from adapters.review_ui import LocalReviewState

        identity = "q:8:progress"
        texts = ("First invented original.", "Second invented original.")
        contexts = [dict(quest_id=8, source="progress", faction="horde", npc_id=20 + i,
                         npc_type="creature", voice="invented", player_gender=None,
                         wording_sha256=digest(text)) for i, text in enumerate(texts)]
        inventory = synthetic_inventory(identity=identity, contexts=contexts)
        fixture = Fixture().add("quest_both", "classic", '{[8]={nil,nil,nil,"Вигаданий переклад."}}')
        state = LocalReviewState(fixture.dataset, fixture.inventory(), inventory,
            TextIndex({}, (identity,), {}, {identity: texts}), self.root / "decisions.json", self.root)
        with patch("tools.manager_inventory.read_pinned_corpus", return_value=[]), patch(
                "tools.manager_inventory.GossipMachineImport.inspect") as gossip_inspection, patch(
                "tools.manager_inventory.discover_groups") as gossip_groups, patch(
                "tools.manager_inventory.gossip_evidence") as gossip_hashes:
            catalog = load_inventory(*self.paths, self.db, self.archive, state=state)
        for gossip_work in (gossip_inspection, gossip_groups, gossip_hashes):
            gossip_work.assert_not_called()
        detail = catalog.detail(identity=identity)
        self.assertEqual(detail["status"], "multiple_originals")
        self.assertEqual(detail["mapping_state"], "mapping_pending")
        self.assertEqual(detail["translation_state"], "translation_available")
        self.assertEqual(catalog.page(status="mapping_pending")["total"], 1)
        self.assertTrue(detail["draft_available"])
        self.assertFalse(detail["built"])
        self.assertEqual([(v["text"], v["contexts"][0]["npc_id"]) for v in detail["original_variants"]],
                         list(zip(texts, (20, 21))))
        option = state.page(target_filter=identity)["items"][0]["target_options"][0]
        self.assertEqual(tuple(v["english_original"] for v in option["variants"]), texts)
        self.assertFalse(option["english_verified"])

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
            self.assertEqual(db.execute("SELECT decision FROM source_candidate_decisions").fetchone()[0], "rejected")
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

    def test_legacy_snapshot_does_not_become_a_module_build(self):
        from adapters.import_statistics import latest_successful_build
        values = dict(spoken_revision="a" * 40, classicua_revision="b" * 40, rows=[])
        legacy = store_successful_build(self.db, artifact_sha256="a" * 64, **values)
        self.assertIsNone(latest_successful_build(self.db, MODULE))
        self.assertIsNone(latest_successful_build(self.db, builder.GOSSIP_MODULE))
        gossip = store_successful_build(self.db, artifact_sha256="b" * 64,
                                       module=builder.GOSSIP_MODULE, **values)
        with patch.object(builder, "build", side_effect=self.fake_build), patch(
                "tools.manager_inventory.load_inventory", return_value=self.view):
            quest = reimport(*self.paths, self.db, reset=True, confirm=True)
        self.assertNotEqual(quest["inventory"]["snapshot_id"], gossip["snapshot_id"])
        self.assertEqual(latest_successful_build(self.db, builder.GOSSIP_MODULE)["snapshot_id"],
                         gossip["snapshot_id"])
        self.assertEqual(latest_successful_build(self.db)["snapshot_id"], legacy["snapshot_id"])

    def test_import_ready_uses_incremental_builder_only_for_quest(self):
        from tools.translation_manager import reimport
        with patch.object(builder, "build", side_effect=self.fake_build) as build, patch(
                "tools.manager_inventory.load_inventory", return_value=self.view):
            result = reimport(*self.paths, self.db, confirm=True, import_ready=True)
        self.assertEqual(result["build"], "success")
        self.assertTrue(build.call_args.kwargs["incremental"])
        self.assertEqual(result["agent"], {"eligible": 0, "skipped": 0, "reasons": []})
        self.assertFalse(self.gossip_archive.exists())
        with self.assertRaisesRegex(ValueError, "manager_invalid_options"):
            reimport(*self.paths, self.db, module=builder.GOSSIP_MODULE,
                     confirm=True, import_ready=True)
        with self.assertRaisesRegex(ValueError, "manager_invalid_options"):
            reimport(*self.paths, self.db, confirm=True,
                     reset=True, import_ready=True)

    def test_registering_candidate_promotes_only_quest_ledger_without_building(self):
        self.gossip_archive.write_bytes(b"existing gossip archive")
        with connection(self.db) as db:
            db.execute("""INSERT INTO ledger_documents(ledger_name,payload,revision)
                VALUES ('gossip-translation-reviews.json','fixture gossip',1)""")

        def register(action, payload, module, row, state, spoken, db_path):
            self.assertEqual((action, module), ("register_candidate", MODULE))
            with connection(db_path) as db:
                db.execute("""INSERT INTO ledger_documents(ledger_name,payload,revision)
                    VALUES ('translation-reviews.json','fixture quest',1)""")
        with patch.object(builder, "build") as build, patch.object(builder, "local_test_state"), patch(
                "tools.manager_inventory.load_inventory", return_value=self.view), patch(
                "tools.manager_review.apply_review", side_effect=register):
            result = reimport(*self.paths, self.db, confirm=True,
                              review=("register_candidate", {"identity": "q:42:accept"}))
        build.assert_not_called()
        self.assertEqual(result, {"module": MODULE, "build": "review_saved"})
        self.assertFalse(self.archive.exists())
        self.assertEqual(self.gossip_archive.read_bytes(), b"existing gossip archive")
        with connection(self.db) as db:
            self.assertEqual(dict(db.execute("SELECT ledger_name,payload FROM ledger_documents")),
                             {"gossip-translation-reviews.json": "fixture gossip",
                              "translation-reviews.json": "fixture quest"})

    def test_saving_quest_stages_only_database_until_explicit_import_all(self):
        # Save is not a ZIP build; every already-published Quest and Gossip
        # archive/checksum must remain byte-for-byte unchanged.
        original_quest, original_gossip = b"original quest ZIP", b"original gossip ZIP"
        self.archive.write_bytes(original_quest)
        self.gossip_archive.write_bytes(original_gossip)
        checksum = self.archive.with_suffix(".zip.sha256")
        checksum.write_bytes(b"original checksum")

        def save(action, payload, module, row, state, spoken, db_path):
            self.assertEqual((action, module), ("save_quest", MODULE))
            with connection(db_path) as db:
                db.execute("""INSERT INTO quest_simple_choices
                    (moment, evidence, text, text_sha256, source) VALUES (?, ?, ?, ?, ?)""",
                    ("q:42:accept", "test-binding", "Новий текст.", "fingerprint", "manual"))
            return "fingerprint"

        with patch.object(builder, "build") as build, patch.object(builder, "local_test_state"), patch(
                "tools.manager_inventory.load_inventory", return_value=self.view), patch(
                "tools.manager_review.apply_review", side_effect=save):
            result = reimport(*self.paths, self.db, confirm=True,
                              review=("save_quest", {"identity": "q:42:accept"}))
            build.assert_not_called()
        self.assertEqual(result, {"module": MODULE, "build": "review_saved"})
        self.assertEqual(self.archive.read_bytes(), original_quest)
        self.assertEqual(checksum.read_bytes(), b"original checksum")
        self.assertEqual(self.gossip_archive.read_bytes(), original_gossip)
        with connection(self.db) as db:
            self.assertEqual(db.execute(
                "SELECT text FROM quest_simple_choices WHERE moment='q:42:accept'"
            ).fetchone()[0], "Новий текст.")

        # Only the explicit bulk-import operation is permitted to build the ZIP.
        with patch.object(builder, "build", side_effect=self.fake_build), patch(
                "tools.manager_inventory.load_inventory", return_value=self.view):
            result = reimport(*self.paths, self.db, confirm=True)
        self.assertEqual(result["build"], "success")
        self.assertNotEqual(self.archive.read_bytes(), original_quest)
        self.assertEqual(self.gossip_archive.read_bytes(), original_gossip)

    def test_new_review_routes_reject_unsafe_http_before_dispatch(self):
        manager = ManagerUI(*self.paths, self.db)
        self.addCleanup(manager.close)
        http = ThreadingHTTPServer(("127.0.0.1", 0), create_handler("token", 0))
        port = http.server_address[1]
        http.RequestHandlerClass = create_handler("token", port, manager)
        thread = Thread(target=http.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (http.shutdown(), http.server_close(), thread.join(5)))
        origin = f"http://127.0.0.1:{port}"
        standard = {"Content-Type": "application/json", "Origin": origin, "X-Review-Token": "token"}
        cases = [
            (standard | {"Host": "invalid.example"}, b"{}", 403),
            (standard | {"Origin": "http://invalid.example"}, b"{}", 403),
            (standard | {"X-Review-Token": ""}, b"{}", 403),
            (standard | {"Content-Type": "text/plain"}, b"{}", 403),
            (standard, b'{"module":1,"module":2}', 400),
            (standard, b"x" * 262145, 413),
        ]
        with patch.object(manager, "action") as dispatch:
            for action in ("confirm_candidate", "review_mapping", "save_translation", "register_candidate"):
                for headers, body, status in cases:
                    with self.subTest(action=action, status=status), self.assertRaises(HTTPError) as err:
                        urlopen(Request(origin + "/api/manager/" + action, headers=headers,
                                        data=body), timeout=5)
                    self.assertEqual(err.exception.code, status)
            dispatch.assert_not_called()

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
            self.assertIn("{ім'я}", zipped.read("Spoken_Quest_UA/Translations.lua").decode())

    def test_http_contract_and_worker_cli_equivalence(self):
        manager = ManagerUI(*self.paths, self.db)
        self.addCleanup(manager.close)
        http = ThreadingHTTPServer(("127.0.0.1", 0), create_handler("test", 0))
        self.addCleanup(http.server_close)
        port = http.server_address[1]
        http.RequestHandlerClass = create_handler("test", port, manager=manager)
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
        self.assertEqual(body.count("Створити модуль"), 1)
        self.assertNotIn('/advanced', body)
        with self.assertRaises(HTTPError) as missing:
            urlopen(url + "/advanced", timeout=5)
        self.assertEqual(missing.exception.code, 404)
        with patch("tools.manager_inventory.load_inventory", return_value=self.view), patch.object(
                manager, "validate_checkouts", return_value=("fixture",)):
            self.assertEqual(post("list", {"module": MODULE})["total"], 2)
            self.assertEqual(post("detail", {"module": MODULE, "identity": "q:43:progress"})["status"], "conflict")
            with self.assertRaises(HTTPError) as cross_module:
                post("detail", {"module": MODULE, "identity": "gossip:3:27:a"})
            self.assertEqual(cross_module.exception.code, 400)
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
        self.assertEqual(worker_run.call_args.kwargs["timeout"], 600)
        with patch.object(builder, "build", side_effect=self.fake_build), patch(
                "tools.manager_inventory.load_inventory", return_value=self.view), patch(
                "tools.translation_manager.subprocess.run", side_effect=run_cli):
            built = post("reimport", {"module": MODULE, "confirm": True})
        self.assertEqual(built["build"], "success")
        self.assertEqual(built["sha256"], sha256(self.archive.read_bytes()).hexdigest())

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
        failure = subprocess.TimeoutExpired(["worker"], 600, b"PRIVATE TEXT", b"PRIVATE REVIEWER")
        for module in self.archives:
            for action, options in (
                    ("reimport", {"dry_run": True}), ("reimport", {"confirm": True}),
                    ("confirm_candidate", {}), ("register_candidate", {}),
                    ("save_translation", {}), ("review_mapping", {})):
                with self.subTest(module=module, action=action, options=options), patch(
                        "tools.translation_manager.subprocess.run", side_effect=failure) as timed_out:
                    with self.assertRaises(HTTPError) as error:
                        post(action, {"module": module, **options})
                    self.assertEqual(error.exception.code, 400)
                    self.assertEqual(json.load(error.exception), {
                        "error": "invalid_or_duplicate_review_decision",
                        "reason": "manager_reimport_timed_out_check_build",
                    })
                    self.assertEqual(timed_out.call_args.kwargs["timeout"], 600)
                    self.assertIn(module, timed_out.call_args.args[0])

    def test_killed_staging_worker_preserves_live_state_and_releases_lock(self):
        manager = ManagerUI(*self.paths, self.db)
        self.addCleanup(manager.close)
        with connection(self.db):
            pass
        checksum = self.archive.with_suffix(".zip.sha256")
        self.archive.write_bytes(b"previous archive")
        checksum.write_bytes(b"previous checksum")
        live_paths = (self.db, self.archive, checksum)
        before = [path.read_bytes() for path in live_paths]
        started = self.root / "worker-staged-files"
        run = subprocess.run

        def interrupted_worker(args, **kwargs):
            workspace = Path(args[args.index("--stage-in") + 1])
            with self.assertRaisesRegex(ValueError, "manager_reimport_already_running"):
                with manager_module.manager_lock(self.root):
                    self.fail("build lock must be held while staging")
            code = """
import sqlite3
import sys
from pathlib import Path
from time import sleep

staged, incoming, started = map(Path, sys.argv[1:])
with sqlite3.connect(staged) as db:
    db.execute("CREATE TABLE staged_change (id INTEGER)")
incoming.write_bytes(b"new staged archive")
started.touch()
sleep(60)
"""
            return run([sys.executable, "-c", code, str(workspace / "translations.sqlite3"),
                        str(manager_module.staged_zip(workspace)), str(started)], **kwargs)

        with patch.object(manager_module, "MANAGER_WORKER_TIMEOUT_SECONDS", 3), patch(
                "tools.translation_manager.subprocess.run", side_effect=interrupted_worker):
            with self.assertRaisesRegex(ValueError, "^manager_reimport_timed_out_check_build$"):
                manager.action("reimport", {"module": MODULE, "confirm": True})
        self.assertTrue(started.exists())
        self.assertEqual([path.read_bytes() for path in live_paths], before)
        self.assertEqual(list(self.root.glob(".translation-manager-*")), [])
        with patch.object(builder, "build", side_effect=self.fake_build), patch(
                "tools.manager_inventory.load_inventory", return_value=self.view):
            result = reimport(*self.paths, self.db, confirm=True)
        self.assertEqual(result["build"], "success")
        self.assertNotEqual(self.archive.read_bytes(), before[1])

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
        self.addCleanup(manager.close)
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

    def test_cached_catalogs_survive_switching_and_refresh_on_zip_or_pins(self):
        manager = ManagerUI(*self.paths, self.db)
        self.addCleanup(manager.close)
        gossip = ModuleInventory([], None, {}, builder.GOSSIP_MODULE)
        views = {MODULE: self.view, builder.GOSSIP_MODULE: gossip}

        def browse(module, **fields):
            return manager.action("list", {"module": module, **fields})

        with patch.object(manager, "validate_checkouts", return_value=("first",)) as pins, patch(
                "tools.manager_inventory.load_inventory", side_effect=lambda *a, module, **k: views[module]) as load:
            browse(MODULE)
            browse(builder.GOSSIP_MODULE)
            self.assertEqual(browse(MODULE, query="Invented", limit=1)["total"], 1)
            self.assertEqual(browse(MODULE, offset=1, limit=1)["items"][0]["id"], "q:43:progress")
            self.assertEqual(load.call_count, 2)

            self.archive.write_bytes(b"new archive")
            browse(MODULE)
            browse(builder.GOSSIP_MODULE)
            self.assertEqual(load.call_count, 3)
            pins.return_value = ("second",)
            browse(builder.GOSSIP_MODULE)
            browse(MODULE)
            self.assertEqual(load.call_count, 5)

    def test_wal_commit_during_catalog_build_retries_and_invalidates_both_modules(self):
        manager = ManagerUI(*self.paths, self.db)
        self.addCleanup(manager.close)
        entered, committed = Event(), Event()
        document = '"quest_cache_fixture"'
        started = []
        with connection(self.db) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(f"CREATE TABLE {document} (value INTEGER)")
            db.execute(f"INSERT INTO {document} VALUES (0)")

        def load(*args, module, **kwargs):
            with connection(self.db) as db:
                value = db.execute(f"SELECT value FROM {document}").fetchone()[0]
            if not started:
                started.append(value)
                entered.set()
                self.assertTrue(committed.wait(5))
            return ModuleInventory([], {"value": value}, {}, module)

        def write():
            if entered.wait(5):
                with connection(self.db) as db:
                    db.execute(f"UPDATE {document} SET value = 1")
                committed.set()

        thread = Thread(target=write)
        thread.start()
        try:
            with patch.object(manager, "validate_checkouts", return_value=("pins",)), patch(
                    "tools.manager_inventory.load_inventory", side_effect=load) as inventory:
                result = manager.action("list", {"module": MODULE})
                self.assertEqual(result["build"], {"value": 1})
                self.assertEqual(inventory.call_count, 2)
                manager.action("list", {"module": builder.GOSSIP_MODULE})
                with sqlite3.connect(self.db, isolation_level=None) as db:
                    db.execute("PRAGMA wal_autocheckpoint=0")
                    stamp = self.db.stat().st_mtime_ns
                    db.execute(f"UPDATE {document} SET value = 2")
                    self.assertEqual(self.db.stat().st_mtime_ns, stamp)
                    for module in (MODULE, builder.GOSSIP_MODULE):
                        self.assertEqual(manager.action("list", {"module": module})["build"], {"value": 2})
                    self.assertEqual(inventory.call_count, 5)
                db.close()
        finally:
            thread.join(5)

    def test_successful_save_and_ready_import_invalidate_but_failed_promotion_keeps_cache(self):
        manager = ManagerUI(*self.paths, self.db)
        self.addCleanup(manager.close)
        (self.root / "promotion.json").write_text(json.dumps(["db", [None, None], ["pins"]]))
        with patch.object(manager, "validate_checkouts", return_value=("pins",)), patch(
                "tools.manager_inventory.load_inventory", return_value=self.view) as load, patch(
                "tools.translation_manager.source_stamps", return_value=["pins"]), patch(
                "tools.translation_manager.promote") as promote:
            browse = lambda: manager.action("list", {"module": MODULE})
            browse()
            manager._promote_worker_result(self.root, MODULE, "save_quest", False, {})
            browse()
            self.assertEqual(load.call_count, 2)
            promote.side_effect = ValueError("manager_reimport_failed")
            with self.assertRaisesRegex(ValueError, "manager_reimport_failed"):
                manager._promote_worker_result(self.root, MODULE, "import_ready", False, {"sha256": "fixture"})
            browse()
            self.assertEqual(load.call_count, 2)
            promote.side_effect = None
            manager._promote_worker_result(self.root, MODULE, "import_ready", False, {"sha256": "fixture"})
            browse()
            self.assertEqual(load.call_count, 3)

    def test_commit_during_final_pin_check_invalidates_completed_catalog(self):
        manager = ManagerUI(*self.paths, self.db)
        self.addCleanup(manager.close)
        with connection(self.db) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE generation_fixture (value INTEGER)")
            db.execute("INSERT INTO generation_fixture VALUES (1)")

        def load(*args, module, **kwargs):
            with connection(self.db) as db:
                value = db.execute("SELECT value FROM generation_fixture").fetchone()[0]
            return ModuleInventory([], {"value": value}, {}, module)

        def validate():
            if inventory.call_count == 1:
                with connection(self.db) as db:
                    db.execute("UPDATE generation_fixture SET value = 2")
            return ("pins",)

        with patch("tools.manager_inventory.load_inventory", side_effect=load) as inventory, patch.object(
                manager, "validate_checkouts", side_effect=validate):
            self.assertEqual(manager.action("list", {"module": MODULE})["build"], {"value": 2})
            self.assertEqual(inventory.call_count, 2)
            self.assertEqual(manager.action("list", {"module": MODULE})["build"], {"value": 2})
            self.assertEqual(inventory.call_count, 2)
