"""The simplified Gossip UI: automatic exact matches, IDs and import provenance."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from adapters.source_revision_store import sha
from tools import build_ukrainian as builder
from tools.gossip_simple import rows as gossip_rows
from tools.manager_inventory import ModuleInventory


NPC_ID = 68
TEXT_ID = 107874079
IDENTITY = f"gossip:{NPC_ID}:{TEXT_ID}"


class GossipSimpleUITests(TestCase):
    def setUp(self):
        self.original = {"lineId": "spoken:gossip:example", "npcId": NPC_ID,
                         "npcName": "Innkeeper", "npcType": "creature",
                         "originalText": "Hello.", "voice": None,
                         "playerGender": None, "race": None, "gender": None}
        record = SimpleNamespace(origin=SimpleNamespace(file="classic/gossip.lua", line=19))
        self.state = SimpleNamespace(
            inventory=SimpleNamespace(revision="a" * 40),
            source=SimpleNamespace(revision="b" * 40, files={}),
            dataset=SimpleNamespace(records={"gossip": {
                NPC_ID: SimpleNamespace(fields={(TEXT_ID,): record}),
                "!common": SimpleNamespace(fields={(TEXT_ID,): record})}}))
        self.audit = {(NPC_ID, TEXT_ID): {
            "exact_hash_sources": [{"scope": NPC_ID}]}}
        self.lookup = {"byNpc": {NPC_ID: {TEXT_ID: "Вітаю."}}, "common": {}}

    def one(self, *, lookup=None, audit=None, units=None, stored=None, unsafe=None):
        with patch("tools.gossip_simple.contexts", return_value=(
                {(NPC_ID, TEXT_ID): [self.original]}, unsafe or set())), patch(
                "tools.build_ukrainian.local_gossip_texts",
                return_value=self.lookup if lookup is None else lookup), patch(
                "tools.gossip_simple.selections", return_value=stored or {}):
            return list(gossip_rows(self.state, [self.original], None, units or {},
                                    self.audit if audit is None else audit))[0]

    def test_single_verified_translation_is_ready_without_clicking_save(self):
        row = self.one()
        self.assertEqual(row["id"], IDENTITY)
        self.assertEqual((row["npc_id"], row["english_hash"]), (68, 107874079))
        self.assertEqual(row["status"], "ready")
        self.assertTrue(row["ready_to_import"])
        self.assertFalse(row["recorded"])
        self.assertIsNone(row["built"])
        self.assertEqual(row["selection"]["text"], "Вітаю.")
        self.assertTrue(row["selection"]["auto"])
        view = ModuleInventory([row], None, {}, module=builder.GOSSIP_MODULE)
        self.assertEqual(view.summary()["gossip"]["ready"], 1)
        self.assertEqual(view.summary()["gossip"]["quest_problem"], 0)
        item = view.page(module=builder.GOSSIP_MODULE, filter_by="quest_ready")["items"][0]
        self.assertEqual((item["npc_id"], item["english_hash"]), (68, 107874079))
        self.assertEqual(view.page(module=builder.GOSSIP_MODULE,
                                   query="107874079")["total"], 1)

    def test_save_gossip_reloads_as_ready_from_actual_sqlite(self):
        """A chosen audit translation must persist, then leave Problematic."""
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        from adapters.sqlite_translation_store import connection
        from tools.gossip_simple import apply_choice, rows as current_rows

        original = "Welcome, $n."
        self.original["originalText"] = original
        candidate = "Вітаю, {Ім'я}."
        row = self.one(lookup={"byNpc": {NPC_ID: {TEXT_ID: candidate}}, "common": {}})
        self.assertTrue(row["review_binding"])
        with TemporaryDirectory() as temp:
            db_path = Path(temp) / "gossip.sqlite3"
            with connection(db_path) as sql:
                sql.execute("BEGIN IMMEDIATE")
                apply_choice("save_gossip", {
                    "identity": row["id"], "binding": row["review_binding"],
                    "text": candidate, "confirm": True,
                }, row, self.state, db_path, db=sql)
                sql.commit()
                persisted = sql.execute("""SELECT text,source,reference FROM gossip_simple_choices
                    WHERE identity=?""", (row["id"],)).fetchone()
            self.assertEqual(persisted, (candidate, "manual", "local_selection"))
            with patch("tools.gossip_simple.contexts", return_value=(
                    {(NPC_ID, TEXT_ID): [self.original]}, set())), patch(
                    "tools.build_ukrainian.local_gossip_texts",
                    return_value={"byNpc": {}, "common": {}}):
                updated = list(current_rows(self.state, [self.original], db_path, {}, {}))[0]
            self.assertEqual(updated["status"], "ready")
            self.assertTrue(updated["ready_to_import"])
            self.assertTrue(updated["recorded"])
            self.assertEqual(updated["selection"]["source"], "manual")
            self.assertEqual(updated["selection"]["text"], candidate)
            view = ModuleInventory([updated], None, {}, module=builder.GOSSIP_MODULE)
            self.assertEqual(view.summary()["gossip"]["ready"], 1)
            self.assertEqual(view.page(module=builder.GOSSIP_MODULE,
                                       filter_by="quest_problem")["total"], 0)
            self.assertEqual(view.page(module=builder.GOSSIP_MODULE,
                                       filter_by="quest_ready")["total"], 1)

    def test_manager_save_gossip_updates_cached_detail_and_ready_filter(self):
        """Exercise the exact browser Save -> SQLite -> list/detail reload path."""
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        from adapters.sqlite_translation_store import connection
        from tools import translation_manager as manager_module
        from tools.gossip_simple import rows as current_rows

        self.original["originalText"] = "Hello, $n."
        selected_text = "Вітаю, {Ім'я}."
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "gossip.sqlite3"
            gossip_zip = root / "gossip.zip"
            gossip_zip.write_bytes(b"existing ZIP stays unchanged")
            with connection(db_path):
                pass
            manager = manager_module.ManagerUI(root / "ClassicUA", root / "Spoken", db_path)
            self.addCleanup(manager.close)

            def view_loader(classicua, spoken, db_path, archive, *, module, input_loader):
                self.assertEqual(module, builder.GOSSIP_MODULE)
                with patch("tools.gossip_simple.contexts", return_value=(
                        {(NPC_ID, TEXT_ID): [self.original]}, set())), patch(
                        "tools.build_ukrainian.local_gossip_texts",
                        return_value={"byNpc": {}, "common": {}}):
                    records = list(current_rows(self.state, [self.original], db_path, {}, {}))
                return ModuleInventory(records, None, {}, module=module, state=self.state)

            archive_paths = {builder.QUEST_MODULE: root / "quest.zip",
                             builder.GOSSIP_MODULE: gossip_zip}
            with patch.object(builder, "DIST", root), patch.object(
                    manager_module, "ARCHIVES", archive_paths), patch.object(
                    manager, "validate_checkouts", return_value=("verified-pins",)), patch(
                    "tools.manager_inventory.load_inventory", side_effect=view_loader):
                options = {"module": builder.GOSSIP_MODULE, "identity": IDENTITY}
                before = manager.action("detail", options)
                self.assertFalse(before["ready_to_import"])
                self.assertEqual(manager.action("list", {
                    "module": builder.GOSSIP_MODULE,
                    "filter_by": "quest_problem"})["total"], 1)
                result = manager.action("save_gossip", options | {
                    "binding": before["review_binding"], "text": selected_text, "confirm": True})
                self.assertEqual(result["build"], "review_saved")
                after = manager.action("detail", options)
                self.assertTrue(after["ready_to_import"])
                self.assertEqual(after["status"], "ready")
                self.assertEqual(after["selection"]["text"], selected_text)
                self.assertTrue(after["recorded"])
                self.assertEqual(manager.action("list", {
                    "module": builder.GOSSIP_MODULE, "filter_by": "quest_problem"})["total"], 0)
                self.assertEqual(manager.action("list", {
                    "module": builder.GOSSIP_MODULE, "filter_by": "quest_ready"})["total"], 1)
                self.assertEqual(manager.action("stats", {
                    "module": builder.GOSSIP_MODULE})["summary"]["gossip"]["ready"], 1)
            self.assertEqual(gossip_zip.read_bytes(), b"existing ZIP stays unchanged")

    def test_matching_auto_import_is_marked_imported_not_ready(self):
        units = {("gossip", f"npc:{NPC_ID}:{TEXT_ID}"): {
            "source": "classicua", "route": "pinned_unique",
            "text_sha256": sha("Вітаю.")}}
        row = self.one(units=units)
        self.assertIsNotNone(row["built"])
        self.assertFalse(row["ready_to_import"])
        view = ModuleInventory([row], {"sha256": "built"}, units,
                               module=builder.GOSSIP_MODULE)
        stats = view.summary()["gossip"]
        self.assertEqual((stats["ready"], stats["quest_imported"], stats["quest_problem"]),
                         (0, 1, 0))

    def test_two_different_exact_translations_require_a_choice(self):
        lookup = {"byNpc": {NPC_ID: {TEXT_ID: "Вітаю."}},
                  "common": {TEXT_ID: "Привіт."}}
        audit = {(NPC_ID, TEXT_ID): {"exact_hash_sources": [
            {"scope": NPC_ID}, {"scope": "!common"}]}}
        row = self.one(lookup=lookup, audit=audit)
        self.assertFalse(row["ready_to_import"])
        self.assertTrue(row["needs_choice"])
        self.assertIsNone(row["selection"])
        self.assertEqual(len(row["candidates"]), 2)

    def test_unsafe_context_never_auto_imports(self):
        row = self.one(unsafe={(NPC_ID, TEXT_ID)})
        self.assertIsNone(row["selection"])
        self.assertFalse(row["ready_to_import"])
        self.assertIsNone(row["review_binding"])

    def test_old_invalid_manual_choice_is_not_silently_replaced(self):
        row = self.one(stored={IDENTITY: ("old-binding", "Старий.", sha("Старий."),
                                          "manual", "local_selection")})
        self.assertEqual(row["status"], "stale")
        self.assertIsNone(row["selection"])
        self.assertFalse(row["ready_to_import"])

    def test_persisted_manual_translation_must_match_all_originals(self):
        from adapters.crosswalk import digest

        first = {**self.original, "originalText": "Hello $N"}
        second = {**self.original, "originalText": "Hello $C"}
        fields = ("lineId", "npcType", "race", "gender", "playerGender", "voice", "originalText")
        evidence_contexts = [{key: line.get(key) for key in fields}
                             for line in (first, second)]
        binding = digest({"spoken": self.state.inventory.revision,
                          "classicua": self.state.source.revision,
                          "identity": IDENTITY, "contexts": evidence_contexts})
        text = "Вітаю $N"
        stored = {IDENTITY: (binding, text, sha(text), "manual", "local_selection")}
        with patch("tools.gossip_simple.contexts", return_value=(
                {(NPC_ID, TEXT_ID): [first, second]}, set())), patch(
                "tools.build_ukrainian.local_gossip_texts", return_value=self.lookup), patch(
                "tools.gossip_simple.selections", return_value=stored):
            row = list(gossip_rows(self.state, [first, second], None, {}, self.audit))[0]
        self.assertEqual(row["status"], "stale")
        self.assertIsNone(row["selection"])
        self.assertFalse(row["ready_to_import"])

    def test_stale_choice_does_not_block_other_ready_gossip_imports(self):
        stale = self.one(stored={IDENTITY: ("outdated", "Старий.", sha("Старий."),
                                           "manual", "local_selection")})
        valid = self.one()
        # The second row stands for a distinct verified NPC/hash.
        valid.update(id="gossip:69:107874079", npc_id=69)
        view = ModuleInventory([stale, valid], None, {}, module=builder.GOSSIP_MODULE,
                               state=self.state)
        self.assertEqual(view.summary()["gossip"]["ready"], 1)
        self.assertEqual(view.summary()["gossip"]["quest_problem"], 1)
        with patch("tools.manager_inventory.load_inventory", return_value=view), patch.object(
                builder, "read_classicua_inflections", return_value={}), patch.object(
                builder, "template_entries", return_value={}), patch.object(
                builder, "render_gossip_lua", return_value=b""), patch.object(
                builder, "write_zip", return_value=(Path("test.zip"), "checksum")), patch(
                "adapters.import_statistics.store_successful_build", return_value={}) as store:
            result = builder.build_gossip(Path("ClassicUA"), Path("Spoken"), Path("test.zip"))
        self.assertEqual(result["gossip_text_records"]["npc_hashes"], 1)
        self.assertEqual(store.call_args.kwargs["rows"][0]["unit"], "npc:69:107874079")

    def test_build_serializes_only_safe_auto_choice_with_pinned_provenance(self):
        row = self.one()
        view = ModuleInventory([row], None, {}, module=builder.GOSSIP_MODULE,
                               state=self.state)
        with patch("tools.manager_inventory.load_inventory", return_value=view), patch.object(
                builder, "read_classicua_inflections", return_value={}), patch.object(
                builder, "template_entries", return_value={}), patch.object(
                builder, "render_gossip_lua", return_value=b""), patch.object(
                builder, "write_zip", return_value=(Path("test.zip"), "checksum")), patch(
                "adapters.import_statistics.store_successful_build", return_value={}) as store:
            result = builder.build_gossip(Path("ClassicUA"), Path("Spoken"), Path("test.zip"))
        self.assertEqual(result["gossip_text_records"]["npc_hashes"], 1)
        unit = store.call_args.kwargs["rows"][0]
        self.assertEqual(unit["unit"], "npc:68:107874079")
        self.assertEqual((unit["source"], unit["route"]), ("classicua", "pinned_unique"))
        self.assertEqual(unit["text_sha256"], sha("Вітаю."))

    def fuzzy(self, original, english, ukrainian, *, kind="same_template", scope="!common"):
        from tools.gossip_coverage import classicua_hash

        self.original["originalText"] = original
        key = classicua_hash(english)
        self.assertNotEqual(key, TEXT_ID)
        path = "classic/gossip.lua"
        self.state.source.files[path] = "c" * 64
        leaf = SimpleNamespace(origin=SimpleNamespace(file=path, line=19))
        self.state.dataset.records["gossip"][scope].fields[(key,)] = leaf
        source = {"scope": scope, "hash": key, "english": english,
                  "file": path, "file_sha256": "c" * 64,
                  "revision": self.state.source.revision, "value_line": 19,
                  "effective": True}
        audit = {"category": "whitespace_candidate" if kind == "whitespace_candidate"
                 else "no_evidence"}
        if kind == "whitespace_candidate":
            audit["whitespace_candidates"] = [source]
        else:
            audit["template_candidates"] = [{"test": kind, "source": source}]
        lookup = {"byNpc": {}, "common": {key: ukrainian}} if scope == "!common" else {
            "byNpc": {NPC_ID: {key: ukrainian}}, "common": {}}
        return self.one(lookup=lookup, audit={(NPC_ID, TEXT_ID): audit})

    def test_same_template_auto_selected_with_distinct_classicua_hash(self):
        row = self.fuzzy("Greetings, $N!", "Greetings, <name>!", "Вітаю, $N!")
        self.assertEqual(row["status"], "ready")
        self.assertTrue(row["ready_to_import"])
        self.assertTrue(row["selection"]["auto"])
        self.assertEqual(row["selection"]["match_type"], "same_template")
        self.assertIn("same_template", row["match_types"])
        self.assertEqual(row["english_hash"], TEXT_ID)
        self.assertIn("[!common]", row["selection"]["reference"])
        self.assertEqual(row["selection"]["rendered"], "Вітаю, {ім'я}!")

    def test_same_template_supports_classicua_name_grammar(self):
        row = self.fuzzy(
            "The Sentinels need your help. $n, speak to their leader.",
            "The Sentinels need your help. <name>, speak to their leader.",
            "Стражам потрібна допомога. {Ім'я}, поговори з їхнім ватажком.")
        self.assertEqual(row["status"], "ready")
        self.assertTrue(row["ready_to_import"])
        self.assertTrue(row["selection"]["auto"])
        self.assertIn("{Ім'я}", row["selection"]["rendered"])
        self.assertEqual(row["selection"]["match_type"], "same_template")

    def test_classicua_grammar_does_not_hide_missing_or_extra_slots(self):
        from tools.gossip_simple import runtime_text
        self.assertEqual(runtime_text("Hello, $n.", "Вітаю, {Ім'я}."),
                         "Вітаю, {Ім'я}.")
        self.assertEqual(runtime_text("Hello, $C.", "Вітаю, {Клас}."),
                         "Вітаю, {Клас}.")
        self.assertEqual(runtime_text("Hello, $Gfriend:friend;", "Вітаю, {стать:друже:подруго}."),
                         "Вітаю, {стать:друже:подруго}.")
        for original, translation in (
            ("Hello, $n.", "Вітаю."),
            ("Hello.", "Вітаю, {ім'я}."),
            ("Hello, $n.", "Вітаю, {Ім'я} та $n."),
            ("Hello, $n.", "Вітаю, {ім'я:unknown}."),
            ("Hello, $c.", "Вітаю, {раса}."),
            ("Hello, $b.", "Вітаю."),
        ):
            with self.subTest(original=original, translation=translation), self.assertRaises(ValueError):
                runtime_text(original, translation)

    def test_real_stormwind_guard_template_becomes_ready(self):
        """Regression: NPC 68 / original hash 1978831227 from the reviewer screenshot."""
        import os
        from tempfile import TemporaryDirectory
        from tools.manager_inventory import load_inventory

        classicua = Path(os.environ.get("CLASSICUA_SOURCE", "../ClassicUA"))
        spoken = Path(os.environ.get("SPOKEN_SOURCE", "../spoken-wow"))
        if not (classicua / ".git").exists() or not (spoken / ".git").exists():
            self.skipTest("Requires pinned ClassicUA and Spoken Git checkouts")
        with TemporaryDirectory() as temp:
            view = load_inventory(classicua, spoken, Path(temp) / "review.sqlite3",
                                  Path(temp) / "Gossip.zip", module=builder.GOSSIP_MODULE)
            row = view.rows.get("gossip:68:1978831227")
            self.assertIsNotNone(row, "Missing pinned Stormwind guard Gossip record")
            self.assertTrue(row["ready_to_import"], {
                "status": row["status"], "match_types": row["match_types"],
                "choices": [(c["sha256"], c.get("match_type")) for c in row["candidates"]],
                "audit": [(a["kind"], a.get("scope"), bool(a.get("ukrainian")))
                          for a in row["unverified_alternatives"]],
                "originals": row["originals"],
            })
            self.assertEqual(row["selection"]["match_type"], "same_template")

    def test_whitespace_auto_selected_with_spoken_runtime_hash(self):
        row = self.fuzzy("Welcome.\nHave a seat.", "Welcome.  Have a seat.",
                         "Ласкаво просимо.", kind="whitespace_candidate")
        self.assertEqual(row["status"], "ready")
        self.assertEqual(row["selection"]["match_type"], "whitespace_candidate")
        self.assertIn("whitespace_candidate", row["match_types"])
        self.assertEqual(row["english_hash"], TEXT_ID)
        view = ModuleInventory([row], None, {}, module=builder.GOSSIP_MODULE)
        self.assertEqual(view.page(module=builder.GOSSIP_MODULE,
                                   match_type="whitespace_candidate")["total"], 1)
        self.assertEqual(view.page(module=builder.GOSSIP_MODULE,
                                   match_type="same_template")["total"], 0)

    def test_template_auto_rejects_missing_runtime_placeholders(self):
        row = self.fuzzy("Greetings, $N!", "Greetings, <name>!", "Вітаю!")
        self.assertIsNone(row["selection"])
        self.assertFalse(row["ready_to_import"])
        self.assertEqual(row["status"], "missing")
        self.assertIn("same_template", row["match_types"])

    def test_one_token_edit_is_filterable_but_not_auto_selected(self):
        row = self.fuzzy("Greetings, $N!", "Greetings, <name>!",
                         "Вітаю, $N!", kind="one_token_edit")
        self.assertIsNone(row["selection"])
        self.assertFalse(row["ready_to_import"])
        self.assertIn("one_token_edit", row["match_types"])
        view = ModuleInventory([row], None, {}, module=builder.GOSSIP_MODULE)
        self.assertEqual(view.page(module=builder.GOSSIP_MODULE,
                                   match_type="one_token_edit")["total"], 1)
        with self.assertRaisesRegex(ValueError, "manager_invalid_filters"):
            view.page(module=builder.GOSSIP_MODULE, match_type="not_a_match_type")

    def test_stale_manual_choice_blocks_template_auto_selection(self):
        stored = {IDENTITY: ("outdated", "Ручний.", sha("Ручний."),
                             "manual", "local_selection")}
        self.original["originalText"] = "Greetings, $N!"
        from tools.gossip_coverage import classicua_hash
        english = "Greetings, <name>!"
        source_hash = classicua_hash(english)
        self.state.source.files["classic/gossip.lua"] = "c" * 64
        self.state.dataset.records["gossip"]["!common"].fields[(source_hash,)] = SimpleNamespace(
            origin=SimpleNamespace(file="classic/gossip.lua", line=19))
        source = {"scope": "!common", "hash": source_hash, "english": english,
                  "file": "classic/gossip.lua", "file_sha256": "c" * 64,
                  "revision": self.state.source.revision, "value_line": 19, "effective": True}
        row = self.one(lookup={"byNpc": {}, "common": {source_hash: "Вітаю, $N!"}},
                       audit={(NPC_ID, TEXT_ID): {
                           "category": "no_evidence",
                           "template_candidates": [{"test": "same_template", "source": source}]}},
                       stored=stored)
        self.assertEqual(row["status"], "stale")
        self.assertIsNone(row["selection"])
        self.assertFalse(row["ready_to_import"])

    def test_ambiguous_whitespace_source_records_are_not_auto_selected(self):
        original = "Welcome.\nHave a seat."
        english = ("Welcome.  Have a seat.", "Welcome.\nHave a seat.")
        from tools.gossip_coverage import classicua_hash
        self.original["originalText"] = original
        srcs, lookup = [], {"byNpc": {}, "common": {}}
        self.state.source.files["classic/gossip.lua"] = "c" * 64
        for line, text in enumerate(english, 19):
            key = classicua_hash(text)
            self.state.dataset.records["gossip"]["!common"].fields[(key,)] = SimpleNamespace(
                origin=SimpleNamespace(file="classic/gossip.lua", line=line))
            srcs.append({"scope": "!common", "hash": key, "english": text,
                         "file": "classic/gossip.lua", "file_sha256": "c" * 64,
                         "revision": self.state.source.revision, "value_line": line,
                         "effective": True})
            lookup["common"][key] = "Ласкаво просимо."
        row = self.one(lookup=lookup, audit={(NPC_ID, TEXT_ID): {
            "category": "whitespace_candidate", "whitespace_candidates": srcs}})
        self.assertIsNone(row["selection"])
        self.assertFalse(row["ready_to_import"])
        self.assertTrue(row["candidate_conflict"])

    def test_ambiguous_npc_type_blocks_unreviewed_exact_auto_selection(self):
        audit = {(NPC_ID, TEXT_ID): {
            "category": "ambiguous_npc_type",
            "exact_hash_sources": [{"scope": NPC_ID}]}}
        row = self.one(audit=audit)
        self.assertFalse(row["ready_to_import"])
        self.assertIsNone(row["selection"])
        self.assertIn("ambiguous_npc_type", row["match_types"])
        self.assertEqual(row["status"], "review")
        self.assertEqual(len(row["candidates"]), 1)

    def test_ambiguous_npc_type_preserves_explicit_manual_choice(self):
        from adapters.crosswalk import digest

        fields = ("lineId", "npcType", "race", "gender", "playerGender", "voice", "originalText")
        binding = digest({"spoken": self.state.inventory.revision,
                          "classicua": self.state.source.revision,
                          "identity": IDENTITY,
                          "contexts": [{key: self.original.get(key) for key in fields}]})
        stored = {IDENTITY: (binding, "Ручний.", sha("Ручний."), "manual", "local_selection")}
        audit = {(NPC_ID, TEXT_ID): {"category": "ambiguous_npc_type",
                                    "exact_hash_sources": [{"scope": NPC_ID}]}}
        row = self.one(audit=audit, stored=stored)
        self.assertEqual(row["selection"]["source"], "manual")
        self.assertEqual(row["selection"]["text"], "Ручний.")
        self.assertTrue(row["ready_to_import"])

    def test_template_variants_with_different_placeholder_casing_are_not_auto_selected(self):
        from adapters.crosswalk import digest
        from tools.gossip_coverage import classicua_hash
        from tools.gossip_simple import safe_audit_candidates

        originals = ("Greetings, $C!", "Greetings, $c!")
        english = "Greetings, <class>!"
        source_hash = classicua_hash(english)
        self.state.source.files["classic/gossip.lua"] = "c" * 64
        self.state.dataset.records["gossip"]["!common"].fields[(source_hash,)] = SimpleNamespace(
            origin=SimpleNamespace(file="classic/gossip.lua", line=19))
        source = {"scope": "!common", "hash": source_hash, "english": english,
                  "file": "classic/gossip.lua", "file_sha256": "c" * 64,
                  "revision": self.state.source.revision, "value_line": 19, "effective": True}
        matching = safe_audit_candidates(
            {"template_candidates": [{"test": "same_template", "source": source}]},
            originals, NPC_ID, self.state, {
                "byNpc": {}, "common": {source_hash: "Вітаю, $C!"}})
        self.assertEqual(matching, [])
