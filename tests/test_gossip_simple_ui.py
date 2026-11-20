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
