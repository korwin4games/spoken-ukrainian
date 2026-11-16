"""Stage 3 metadata-only contracts. All fixture words are invented."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.classicua.lua import parse_value
from adapters.classicua.model import Dataset, Origin
from adapters.classicua.evidence import source_reference
from adapters.crosswalk import (VerifiedJoin, VerifiedTarget, approve_mapping, compare_effective,
                                digest, effective_units, metadata_json, metadata_report)


class Fixture:
    def __init__(self, file_hash_override=None, revision="synthetic-revision"):
        self.revision = revision
        self.bodies = {}
        self.file_hash_override = file_hash_override
        self.dataset = Dataset(self.origin)
        self.active_layer = {}
        self.serial = 0

    def origin(self, node, key):
        return Origin("synthetic", self.revision, node.file, node.line,
                      node.column, self.active_layer[node.file],
                      self.file_hash_override or hashlib.sha256(self.bodies[node.file].encode()).hexdigest(), key)

    def add(self, category, layer, body, file=None):
        self.serial += 1
        file = file or f"{layer}/{category}.lua"
        self.bodies[file] = body
        self.active_layer[file] = layer
        self.dataset.apply(category, layer, parse_value(body, file),
                           "gossip" if category == "gossip" else "merge")
        return self

    def inventory(self):
        from adapters.classicua.evidence import SourceInventory
        return SourceInventory(self.revision, {p: hashlib.sha256(b.encode()).hexdigest()
                                              for p, b in self.bodies.items()}, self.units())

    def units(self, evidence=None):
        return effective_units(self.dataset, evidence)


class CrosswalkTests(unittest.TestCase):
    def test_quest_accept_progress_complete_not_title_or_objective(self):
        f = Fixture().add("quest_both", "classic",
            '{[42]={"SECRET-SYNTHETIC-TITLE","Quest intro","Objective",'
            '"In progress","Finished"}}')
        units = f.units()
        self.assertEqual(set(units), {f"quest:{side}:42:{event}"
                         for side in ("alliance", "horde")
                         for event in ("accept", "progress", "complete")})
        self.assertEqual(units["quest:horde:42:accept"].family, "quest")

    def test_faction_override_and_sparse_whole_row_replacement(self):
        f = Fixture().add("quest_both", "classic", '{[42]={"title","shared","obj","ongoing","done"}}')
        f.add("quest_alliance", "forever", '{[42]={"new title",nil,"objective",nil,"done newer",ai=true}}')
        u = f.units()
        self.assertNotIn("quest:alliance:42:accept", u)
        self.assertNotIn("quest:alliance:42:progress", u)
        self.assertTrue(u["quest:alliance:42:complete"].ai)
        self.assertFalse(u["quest:horde:42:complete"].ai)
        self.assertEqual(u["quest:horde:42:accept"].origin_layer, "classic")

    def test_ai_filtered_view_is_not_automatically_restored(self):
        f = Fixture().add("quest_alliance", "classic", '{[42]={nil,"human",nil,"work"}}')
        f.add("quest_alliance", "forever", '{[42]={nil,"AI replacement",ai=true}}')
        self.assertEqual(set(f.units()), {"quest:alliance:42:accept"})
        no_ai, _ = f.dataset.faction_views(include_ai=False)
        self.assertNotIn(42, no_ai["alliance"])

    def test_gossip_merge_uses_effective_fields_and_excludes_code(self):
        f = Fixture().add("gossip", "classic",
            '{[7]={[11]="SECRET-ONE",[12]="SECRET-OLD",["!code"]={x="SECRET-CODE"}},'
            '["!common"]={[1]="SECRET-COMMON"}}')
        f.add("gossip", "forever", '{[7]={[12]="SECRET-NEW",["!code"]={y="SECRET-OTHER"}}}')
        u = f.units()
        self.assertEqual(len(u), 2)
        self.assertTrue(all(x.startswith("gossip:") for x in u))
        self.assertNotIn("SECRET-", metadata_json(metadata_report({}, u)))
        self.assertEqual({x.origin_layer for x in u.values()}, {"classic", "forever"})

    def test_empty_forever_inherits_readables_and_h1_is_not_text(self):
        f = Fixture().add("item_text", "classic", '{[91]={"SECRET-BOOK-ONE","SECRET-BOOK-TWO"}}')
        f.add("item_text", "sod", '{[92]={"SECRET-SOD"}}')
        f.add("item_text", "forever", "{}")
        f.add("object_text", "classic",
              '{["SECRET-OBJECT"]={{"SECRET-PAGE",h1=87},{"SECRET-OTHER",h1=99}}}')
        u = f.units()
        self.assertEqual(len(u), 5)
        self.assertEqual(sum(1 for x in u.values() if x.origin_layer == "sod"), 1)
        report = metadata_json(metadata_report({}, u))
        for secret in ("SECRET-OBJECT", "SECRET-PAGE", "SECRET-BOOK"):
            self.assertNotIn(secret, report)

    def test_readables_whole_row_override_removes_old_page(self):
        f = Fixture().add("item_text", "classic", '{[91]={"one","two"}}')
        before = f.units()
        f.add("item_text", "forever", '{[91]={"replacement"}}')
        delta = compare_effective(before, f.units())
        self.assertEqual([r["change"] for r in delta].count("removed"), 1)
        self.assertEqual([r["change"] for r in delta].count("modified"), 1)

    def test_changed_text_preserves_mapping_but_stales_audio(self):
        f = Fixture().add("quest_both", "classic", '{[42]={nil,"old"}}')
        old = f.units()
        f.add("quest_both", "forever", '{[42]={nil,"new"}}')
        items = [x for x in compare_effective(old, f.units()) if x["change"] == "modified"]
        self.assertEqual(len(items), 2)
        self.assertTrue(all(x["mapping"] == "retain_if_approved" for x in items))
        self.assertTrue(all(x["audio"] == "stale_if_present" for x in items))

    def test_raw_source_file_hash_only_drift_is_not_effective_change(self):
        a = Fixture("a" * 64).add("quest_both", "classic", '{[42]={nil,"same"}}').units()
        b = Fixture("b" * 64).add("quest_both", "classic", '{[42]={nil,"same"}}').units()
        self.assertTrue(all(x["change"] == "unchanged" for x in compare_effective(a, b)))

    def test_origin_swap_rechecks_content_not_identity(self):
        before = Fixture().add("quest_both", "classic", '{[42]={nil,"same"}}').units()
        after = Fixture().add("quest_both", "forever", '{[42]={nil,"same"}}').units()
        entries = compare_effective(before, after)
        self.assertTrue(all(x["reasons"] == ["origin_changed"] for x in entries))
        self.assertTrue(all(x["mapping"] == "retain_if_approved" for x in entries))
        self.assertTrue(all(x["content_review"] == "required" for x in entries))

    def test_ai_status_only_rechecks_eligibility_not_audio(self):
        before = Fixture().add("quest_both", "classic", '{[42]={nil,"same"}}').units()
        after = Fixture().add("quest_both", "classic", '{[42]={nil,"same",ai=true}}').units()
        for item in compare_effective(before, after):
            self.assertEqual(item["reasons"], ["ai_status_changed"])
            self.assertEqual(item["ai_review"], "required")
            self.assertEqual(item["audio"], "unchanged")

    def test_identity_evidence_changed_requires_mapping_review(self):
        a = Fixture().add("quest_both", "classic", '{[42]={nil,"same"}}')
        key = "quest:horde:42:accept"
        x = a.units({key: "a" * 64})
        y = a.units({key: "b" * 64})
        entry = next(x for x in compare_effective(x, y) if x["source_id"] == key)
        self.assertEqual(entry["mapping"], "revalidate")
        self.assertIn("identity_evidence_changed", entry["reasons"])

    def test_mapping_fails_without_independent_target_inventory(self):
        u = Fixture().add("quest_both", "classic", '{[42]={nil,"same"}}').units()
        unit = u["quest:horde:42:accept"]
        with self.assertRaisesRegex(ValueError, "Unverified"):
            approve_mapping(unit, "q:42:accept", {}, {}, "Reviewer")
        with self.assertRaisesRegex(ValueError, "Invalid canonical"):
            VerifiedTarget("q:42:objective", "quest", "pin", "path", "a" * 64)
        with self.assertRaisesRegex(ValueError, "Source identity"):
            approve_mapping(unit, "q:42:accept",
                {"q:42:accept": VerifiedTarget("q:42:accept", "quest", "pin", "path", "a" * 64)}, {}, "Reviewer")

    def test_explicit_review_requires_evidence_and_separate_review_status(self):
        f = Fixture(revision="1" * 40).add("quest_both", "classic", '{[42]={nil,"same"}}')
        unit = f.units({"quest:horde:42:accept": "b" * 64})["quest:horde:42:accept"]
        target = VerifiedTarget("q:42:accept", "quest", "synthetic-pin", "synthetic-public-reference", "a" * 64)
        join = VerifiedJoin(unit.source_id, target.canonical_id, "b" * 64, "a" * 64,
                            source_reference(unit), "c" * 64)
        decision = approve_mapping(unit, "q:42:accept", {"q:42:accept": target},
                                   {(unit.source_id, target.canonical_id): join}, "Synthetic Reviewer", source_inventory=f.inventory())
        self.assertEqual(decision.target_id, "q:42:accept")
        self.assertEqual(decision.join_evidence_sha256, "c" * 64)
        self.assertEqual((decision.mapping_status, decision.content_status, decision.grammar_status, decision.ai_status),
                         ("approved", "pending", "pending", "pending"))
        with self.assertRaisesRegex(ValueError, "Cross-family"):
            approve_mapping(unit, "b:42",
                {"b:42": VerifiedTarget("b:42", "readable", "pin", "path", "a" * 64)}, {}, "Reviewer")

    def test_target_exists_but_join_missing_or_stale_is_rejected(self):
        f = Fixture().add("quest_both", "classic", '{[42]={nil,"same"}}')
        unit = f.units({"quest:horde:42:accept": "b" * 64})["quest:horde:42:accept"]
        target = VerifiedTarget("q:42:accept", "quest", "pin", "path", "a" * 64)
        with self.assertRaisesRegex(ValueError, "join evidence"):
            approve_mapping(unit, target.canonical_id, {target.canonical_id: target}, {}, "Reviewer")
        stale = VerifiedJoin(unit.source_id, target.canonical_id, "a" * 64, "a" * 64,
                             "synthetic-link", "c" * 64)
        with self.assertRaisesRegex(ValueError, "Stale"):
            approve_mapping(unit, target.canonical_id, {target.canonical_id: target},
                            {(unit.source_id, target.canonical_id): stale}, "Reviewer")
        wrong_quest = VerifiedTarget("q:99:accept", "quest", "pin", "path", "a" * 64)
        with self.assertRaisesRegex(ValueError, "Quest ID/event"):
            approve_mapping(unit, wrong_quest.canonical_id, {wrong_quest.canonical_id: wrong_quest},
                            {}, "Reviewer")

    def test_removed_and_added_require_review(self):
        first = Fixture().add("quest_both", "classic", '{[41]={nil,"one"}}').units()
        second = Fixture().add("quest_both", "classic", '{[42]={nil,"two"}}').units()
        items = compare_effective(first, second)
        self.assertEqual({x["change"] for x in items}, {"added", "removed"})
        self.assertEqual({x["mapping"] for x in items}, {"unresolved", "revalidate"})

    def test_deterministic_metadata_no_body_or_object_name_leaks(self):
        f = Fixture().add("object_text", "classic",
            '{["SECRET-PRIVATE-TITLE"]={{"SECRET-PRIVATE-STRING",h1=123}}}')
        old = f.units()
        new = Fixture().add("object_text", "classic",
            '{["SECRET-PRIVATE-TITLE"]={{"SECRET-CHANGED",h1=123}}}').units()
        report = metadata_report(old, new)
        payload = metadata_json(report)
        self.assertEqual(payload, metadata_json(report))
        for token in ("SECRET-PRIVATE-TITLE", "SECRET-PRIVATE-STRING", "SECRET-CHANGED"):
            self.assertNotIn(token, payload)
        self.assertEqual(report["counts"], {"modified": 1})


if __name__ == "__main__":
    unittest.main()
