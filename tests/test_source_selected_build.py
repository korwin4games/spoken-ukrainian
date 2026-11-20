"""The supported Gossip build reads current local choices and preserves legacy records."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile
import unittest

from adapters.crosswalk import digest
from adapters.import_statistics import latest_successful_build
from adapters.sqlite_translation_store import connection, enable_sqlite
from tools import build_ukrainian as builder, gossip_simple
from tools.gossip_coverage import classicua_hash
from tools.manager_inventory import ModuleInventory, latest_units


class FreshGossipBuildTests(unittest.TestCase):
    def test_new_choices_rebuild_idempotently_without_legacy_imports(self):
        english = "Hello traveler."
        hashed = classicua_hash(english)
        lines = [{"lineId": "g:test", "source": "gossip", "npcId": npc,
                  "npcType": "creature", "originalText": english} for npc in (42, 43)]
        leaf = SimpleNamespace(origin=SimpleNamespace(file="synthetic.lua", line=4))
        state = SimpleNamespace(
            inventory=SimpleNamespace(revision="a" * 40, contexts={"g:test": [
                {"npc_id": npc, "npc_type": "creature", "wording_sha256": digest(english)}
                for npc in (42, 43)]}),
            source=SimpleNamespace(revision="b" * 40, files={}),
            dataset=SimpleNamespace(records={"gossip": {
                scope: SimpleNamespace(fields={(hashed,): leaf}) for scope in (42, "!common")}}))
        lookup = {"byNpc": {42: {hashed: "Перша версія."}}, "common": {hashed: "Спільна версія."}}
        audit = {(42, hashed): {"exact_hash_sources": [{"scope": 42}, {"scope": "!common"}]},
                 (43, hashed): {"template_candidates": [{"source": {"english": "Another original."}}]}}
        with TemporaryDirectory() as temp:
            db_path, archive = Path(temp) / "test.sqlite3", Path(temp) / "test.zip"

            def view(*_args, **_kwargs):
                with connection(db_path) as db:
                    units, build = latest_units(db, archive, "a" * 40, "b" * 40, builder.GOSSIP_MODULE)
                return ModuleInventory(gossip_simple.rows(state, lines, db_path, units, audit),
                                       build, units, builder.GOSSIP_MODULE, state)

            with connection(db_path) as db:
                db.execute("INSERT INTO ledger_documents(ledger_name,payload,revision) VALUES (?,?,1)",
                           ("gossip-translation-reviews.json", '{"historic":true}'))
                db.execute("""INSERT INTO quest_simple_choices(moment,evidence,text,text_sha256,source)
                    VALUES ('q:7:accept','proof','Quest','hash','manual')""")
            with enable_sqlite(db_path), patch.object(builder, "DIST", Path(temp)), patch.object(
                    builder, "local_gossip_texts", return_value=lookup), patch.object(
                    builder, "read_classicua_inflections", return_value={}), patch(
                    "tools.manager_inventory.load_inventory", side_effect=view):
                rows = view().rows
                uncertain = rows[f"gossip:43:{hashed}"]
                row = rows[f"gossip:42:{hashed}"]
                self.assertTrue(row["needs_choice"])
                self.assertEqual(len(row["candidates"]), 2)
                self.assertEqual(uncertain["candidates"], [])
                self.assertFalse(uncertain["ready_to_import"])
                empty = builder.build(temp, temp, module=builder.GOSSIP_MODULE, destination=archive)
                self.assertEqual(empty["gossip_text_records"]["npc_hashes"], 0)
                old_zip = archive.read_bytes()
                with connection(db_path) as db:
                    gossip_simple.apply_choice("choose_gossip", {"binding": row["review_binding"],
                        "candidate": row["candidates"][1]["sha256"]}, row, state, db_path, db=db)
                self.assertEqual(archive.read_bytes(), old_zip)
                self.assertTrue(view().rows[row["id"]]["ready_to_import"])
                first = builder.build(temp, temp, module=builder.GOSSIP_MODULE, destination=archive)
                with ZipFile(archive) as zip_file:
                    lua = zip_file.read("Spoken_Gossip_UA/GossipTranslations.lua").decode()
                self.assertIn("Спільна версія.", lua)
                self.assertIn("[42]", lua)
                self.assertNotIn("[43]", lua)
                self.assertFalse(view().rows[row["id"]]["ready_to_import"])
                self.assertIsNotNone(view().rows[row["id"]]["built"])
                second = builder.build(temp, temp, module=builder.GOSSIP_MODULE, destination=archive)
                self.assertEqual(first["sha256"], second["sha256"])
                self.assertEqual(latest_successful_build(db_path, builder.GOSSIP_MODULE)["categories"]["gossip"], 1)
            with connection(db_path) as db:
                self.assertEqual(db.execute("SELECT text FROM quest_simple_choices").fetchone()[0], "Quest")
                self.assertEqual(db.execute("SELECT payload FROM ledger_documents").fetchone()[0],
                                 '{"historic":true}')

    def test_placeholder_and_gender_branches(self):
        original = "$N, $C of the $R.$B$G Brother:Sister;"
        rendered = gossip_simple.runtime_text(original, "$N, $C, $R.$B$G Брате:Сестро;")
        self.assertIn("{Ім'я}".lower(), rendered.lower())
        self.assertIn("\n{стать:Брате:Сестро}", rendered)
        for bad, reason in (
            ("Брате.", "manager_gossip_missing_linebreak"),
            ("$N, $C, $R.$B$G Брате: ;", "manager_gossip_gender_invalid"),
            ("$N, $C, $R.$B$G $N:Сестро;", "manager_gossip_placeholder_mismatch"),
        ):
            with self.subTest(reason=reason), self.assertRaisesRegex(
                    ValueError, "^" + reason + "$"):
                gossip_simple.runtime_text(original, bad)
