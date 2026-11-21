"""Invented text only. UA Forever acquisition stays closed in production."""
from contextlib import ExitStack, closing, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from adapters.crosswalk import digest
from adapters.import_statistics import store_successful_build
from adapters.source_revision_store import sha
from adapters.sqlite_translation_store import DB_ENV, connection
from tools import build_ukrainian as builder, gossip_provider_policy as policy
from tools import gossip_simple, translation_manager as manager
from tools.gossip_coverage import classicua_hash

NPC = 3143
HASH = 1810368146
CANONICAL = "g:bf70aae4154725dec8a65fa84ba0d954"
# Invented English constructed to exercise the actual native hash.
ENGLISH = "synthetic gornek fixture 004 xwayk53"
UA = "Вигадане привітання."
CLASSIC = "Тестова репліка."
MANUAL = "Мій тестовий вибір."


class GossipProviderPolicyTests(unittest.TestCase):
    def fixture(self, english=ENGLISH):
        self.line = {
            "source": "gossip", "lineId": CANONICAL, "npcId": NPC, "npcName": "Gornek",
            "npcType": "creature", "voice": "orc-male-guard", "playerGender": None,
            "originalText": english, "faction": "shared",
        }
        self.hashed = classicua_hash(english)
        self.key = (NPC, self.hashed)
        self.identity = f"gossip:{NPC}:{self.hashed}"
        self.source = SimpleNamespace(revision="b" * 40, files={"entries/classic/gossip.lua": "c" * 64})
        origin = SimpleNamespace(file="entries/classic/gossip.lua", line=12)
        scoped = SimpleNamespace(fields={(self.hashed,): SimpleNamespace(origin=origin)})
        self.dataset = SimpleNamespace(records={"gossip": {NPC: scoped, "!common": scoped}})
        self.inventory = SimpleNamespace(revision="a" * 40, contexts={CANONICAL: [{
            "wording_sha256": digest(english), "npc_id": NPC, "npc_type": "creature",
            "voice": "orc-male-guard", "player_gender": None,
        }]})
        self.state = SimpleNamespace(dataset=self.dataset, source=self.source, inventory=self.inventory)
        self.audit = {self.key: {"exact_hash_sources": [{"scope": NPC}, {"scope": "!common"}]}}

    def ua(self, text=UA, **fields):
        return {"text": text, "sha256": sha(text), "english": self.line["originalText"],
                "npc_id": NPC, "english_hash": self.hashed, "scope": NPC, "role": "greeting",
                "faction": "shared", "context_sha256": digest([self.line]),
                "revision": policy.UA_REVISION, "file_sha256": policy.UA_GOSSIP_SHA256, "line": 99} | fields

    def inputs(self, stack, ua, classic, common=None):
        if ua is not None:
            stack.enter_context(patch.object(policy, "load_ua_forever_candidates",
                                            return_value={self.key: ua}))
        stack.enter_context(patch.object(builder, "local_gossip_texts", return_value={
            "byNpc": {NPC: {self.hashed: classic}} if classic else {},
            "common": {self.hashed: common} if common else {},
        }))

    def resolve(self, ua=None, classic=CLASSIC, common=None, db=None):
        with ExitStack() as stack:
            self.inputs(stack, ua, classic, common)
            return next(gossip_simple.rows(self.state, [self.line], db, {}, self.audit))

    def test_gornek_priority_and_default_rights_block(self):
        self.fixture()
        self.assertEqual(self.hashed, HASH)
        current = self.resolve()
        self.assertEqual(current["provider_decision"]["reason"], policy.FALLBACK)
        self.assertEqual({c["provider"] for c in current["candidates"]}, {"classicua"})
        preferred = self.resolve([self.ua()])
        self.assertEqual(preferred["id"], f"gossip:{NPC}:{HASH}")
        self.assertEqual(preferred["selection"]["source"], "ua_forever")
        self.assertEqual(preferred["provider_decision"]["reason"], policy.PRIORITY_WIN)
        self.assertTrue(preferred["ready_to_import"])

    def test_cross_provider_identical_and_distinct_candidates(self):
        self.fixture()
        identical = self.resolve([self.ua()], classic=UA)
        self.assertEqual(len(identical["candidates"]), 1)
        self.assertEqual(identical["provider_decision"]["reason"], policy.IDENTICAL)
        self.assertEqual({p["provider"] for p in identical["provider_decision"]["provenance"]},
                         {"ua_forever", "classicua"})
        lower_ambiguous = self.resolve([self.ua()], classic=UA, common=CLASSIC)
        self.assertEqual(lower_ambiguous["provider_decision"]["reason"], policy.PRIORITY_WIN)
        self.assertEqual(lower_ambiguous["selection"]["source"], "ua_forever")
        ua_only = self.resolve([self.ua()], classic=None)
        self.assertEqual(ua_only["provider_decision"]["reason"], policy.UNIQUE)
        english = self.resolve([], classic=None)
        self.assertEqual(english["provider_decision"]["reason"], policy.ENGLISH)
        self.assertIsNone(english["selection"])

    def test_ambiguity_within_a_provider(self):
        self.fixture()
        for ua, classic, common, provider in (
                ([self.ua(), self.ua(MANUAL, line=100)], CLASSIC, None, "ua_forever"),
                ([], CLASSIC, MANUAL, "classicua")):
            with self.subTest(provider=provider):
                row = self.resolve(ua, classic, common)
                self.assertTrue(row["needs_choice"])
                self.assertEqual(row["provider_decision"]["provider"], provider)
                self.assertEqual(row["provider_decision"]["reason"], policy.AMBIGUOUS)
                self.assertFalse(row["ready_to_import"])
        self.assertEqual(self.resolve([self.ua(), self.ua(line=100)])["selection"]["source"], "ua_forever")

    def test_bad_ua_evidence_falls_back_before_applying_priority(self):
        self.fixture("Synthetic greeting, $N.")
        classic = "Тестова репліка, $N."
        good = "Вигадане привітання, $N."
        for record in (
                self.ua(good, npc_id=42), self.ua(good, english_hash=HASH), self.ua(good, scope=42),
                self.ua(good, role="reply"), self.ua(good, faction="horde"),
                self.ua(good, context_sha256="0" * 64), self.ua(good, revision="0" * 40),
                self.ua(good, file_sha256="0" * 64), self.ua(good, sha256="0" * 64),
                self.ua(good, english="Another greeting."), self.ua("Привіт."),
                self.ua("Привіт, $1w, $N.")):
            with self.subTest(record=record):
                row = self.resolve([record], classic=classic)
                self.assertEqual(row["selection"]["source"], "classicua")
                self.assertEqual(row["provider_decision"]["reason"], policy.FALLBACK)
        valid_template = self.resolve([self.ua(good, english="Synthetic greeting, <name>.")], classic=classic)
        self.assertEqual(valid_template["selection"]["match_type"], "same_template")
        templates = [self.ua(good, english="Synthetic greeting, <name>.", line=line)
                     for line in (99, 100)]
        self.assertEqual(self.resolve(templates, classic=classic)["provider_decision"]["reason"],
                         policy.AMBIGUOUS)

    def test_migration_and_explicit_choices_preserve_history(self):
        self.fixture()
        with TemporaryDirectory() as temp:
            db_path = Path(temp) / "history.sqlite3"
            baseline = self.resolve()
            old_build = store_successful_build(
                db_path, artifact_sha256="a" * 64, spoken_revision=self.inventory.revision,
                classicua_revision=self.source.revision, module=builder.GOSSIP_MODULE, rows=[{
                    "domain": "gossip", "unit": f"npc:{NPC}:{HASH}", "entity": str(NPC),
                    "source": "classicua", "route": "pinned_unique", "text_sha256": sha(CLASSIC),
                }])
            with connection(db_path) as db:
                db.execute("INSERT INTO gossip_simple_choices VALUES (?,?,?,?,?,?)",
                           (self.identity, baseline["review_binding"], MANUAL, sha(MANUAL),
                            "manual", "local_selection"))
                db.execute("INSERT INTO ledger_documents(ledger_name,payload,revision) VALUES (?,?,?)",
                           ("gossip-translation-reviews.json", '{"fixture":true}', 7))
                # Recreate precisely the pre-provider choice schema and build metadata column.
                db.execute("ALTER TABLE gossip_simple_choices RENAME TO new_choices")
                db.execute("""CREATE TABLE gossip_simple_choices (
                    identity TEXT PRIMARY KEY, evidence TEXT NOT NULL, text TEXT NOT NULL,
                    text_sha256 TEXT NOT NULL, source TEXT NOT NULL CHECK(source IN ('classicua', 'manual')),
                    reference TEXT NOT NULL)""")
                db.execute("INSERT INTO gossip_simple_choices SELECT * FROM new_choices")
                db.execute("DROP TABLE new_choices")
                db.execute("ALTER TABLE build_import_units DROP COLUMN decision")
                db.execute("DELETE FROM schema_migrations WHERE version=11")
                db.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES(10)")
            row = self.resolve([self.ua()], db=db_path)
            self.assertEqual(row["selection"]["text"], MANUAL)
            self.assertEqual(row["provider_decision"]["reason"], policy.EXPLICIT)
            with connection(db_path) as db:
                self.assertEqual(db.execute("SELECT payload,revision FROM ledger_documents").fetchone(),
                                 ('{"fixture":true}', 7))
                self.assertEqual(db.execute("SELECT text FROM gossip_simple_choices").fetchone(), (MANUAL,))
                self.assertEqual(db.execute("SELECT snapshot_id FROM module_build_heads").fetchone(),
                                 (old_build["snapshot_id"],))
                self.assertEqual(db.execute("SELECT source,decision FROM build_import_units").fetchone(),
                                 ("classicua", None))
                gossip_simple.apply_choice("choose_gossip", {
                    "candidate": sha(CLASSIC), "binding": row["review_binding"],
                }, row, self.state, db_path, db=db)
            saved = self.resolve([self.ua()], db=db_path)
            self.assertEqual(saved["selection"]["source"], "classicua")
            identical = self.resolve([self.ua(CLASSIC)], db=db_path)
            self.assertEqual(identical["selection"]["source"], "classicua")
            self.assertEqual(len(identical["candidates"][0]["provenance"]), 2)
            with connection(db_path) as db:
                gossip_simple.apply_choice("choose_gossip", {
                    "candidate": sha(UA), "binding": saved["review_binding"],
                }, saved, self.state, db_path, db=db)
            self.assertEqual(self.resolve([self.ua()], db=db_path)["provider_decision"]["reason"],
                             policy.EXPLICIT)
            disabled = self.resolve(db=db_path)
            self.assertEqual(disabled["provider_decision"]["reason"], policy.STALE)
            self.assertIsNone(disabled["selection"])

    def test_manager_cli_and_actual_synthetic_zip_share_decision(self):
        self.fixture()
        with TemporaryDirectory() as temp, ExitStack() as stack:
            root = Path(temp)
            db_path = root / "gossip.sqlite3"
            archive = root / "gossip.zip"
            archives = {builder.GOSSIP_MODULE: archive, builder.QUEST_MODULE: root / "quest.zip"}
            self.inputs(stack, [self.ua()], CLASSIC)
            stack.enter_context(patch.dict("os.environ", {DB_ENV: str(db_path)}))
            stack.enter_context(patch.object(builder, "DIST", root))
            stack.enter_context(patch.object(builder, "ARCHIVES", archives))
            stack.enter_context(patch.object(manager, "ARCHIVES", archives))
            stack.enter_context(patch.object(manager.ManagerUI, "validate_checkouts", return_value=("verified",)))
            stack.enter_context(patch("tools.review_ui_server.load_review_inputs", return_value=(
                self.dataset, self.source, self.inventory, SimpleNamespace(original_english={}), [self.line])))
            stack.enter_context(patch("tools.manager_inventory.read_pinned_corpus", return_value=[self.line]))
            stack.enter_context(patch.object(gossip_simple, "audit_catalog", return_value=self.audit))
            stack.enter_context(patch.object(builder, "read_classicua_inflections", return_value={}))
            with connection(db_path):
                pass
            query = {"module": builder.GOSSIP_MODULE, "identity": self.identity}
            with closing(manager.ManagerUI(root / "ClassicUA", root / "Spoken", db_path)) as ui:
                before = ui.action("detail", query)
                self.assertTrue(before["ready_to_import"])
                self.assertEqual(before["provider_decision"]["reason"], policy.PRIORITY_WIN)
            with redirect_stdout(StringIO()) as output:
                status = builder.main(["--module", builder.GOSSIP_MODULE, "--classicua",
                                       str(root / "ClassicUA"), "--spoken", str(root / "Spoken")])
            self.assertEqual(status, 0, output.getvalue())
            with ZipFile(archive) as zipped:
                native = zipped.read("Spoken_Gossip_UA/GossipTranslations.lua").decode()
                canonical = zipped.read("Spoken_Gossip_UA/TextPack.lua").decode()
                self.assertIn("greetingsByNpc", native)
                self.assertIn(UA, native)
                self.assertNotIn(CLASSIC, native)
                self.assertIn(CANONICAL, canonical)
                self.assertIn(UA, canonical)
            with connection(db_path) as db:
                decision, = db.execute("SELECT decision FROM build_import_units").fetchone()
                self.assertEqual(json.loads(decision), before["provider_decision"])
                self.assertNotIn(UA, decision)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM gossip_simple_choices").fetchone(), (0,))
            with closing(manager.ManagerUI(root / "ClassicUA", root / "Spoken", db_path)) as ui:
                after = ui.action("detail", query)
                self.assertFalse(after["ready_to_import"])
                self.assertEqual(after["built"]["source"], "ua_forever")
                self.assertEqual(after["provider_decision"], before["provider_decision"])
