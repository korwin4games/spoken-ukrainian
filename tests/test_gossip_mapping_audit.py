import gzip
import csv
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from tools.build_ukrainian import render_gossip_lua
from tools.gossip_candidate_tables import candidate_tables, one_edit, template, tokens
from tools.gossip_mapping_audit import (
    ALIAS_PATH, CORPUS_PATH, TOC_PATH, audit, classicua_hash, dynamic_code,
    dynamic_match, prepared_reason, replies, source_comments, spoken_baseline, zip_inventory,
)


def row(stem, text, npc=7, kind="creature", suffix=""):
    return {"source": "gossip", "npcId": npc, "npcType": kind,
            "lineId": "g:" + stem * 32 + suffix, "originalText": text, "text": text,
            "gender": "male", "playerGender": None, "voice": "fixture"}


def nonzero(counts):
    return {name: count for name, count in counts["categories"].items() if count}


class GossipMappingAuditTests(unittest.TestCase):
    def test_candidate_tables_keep_npc_identity_and_all_wording_leads_separate(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            line = dict(row("a", "Hello $N!"), corpus_index=4, npcName="Fixture")
            pair = {"category": "no_evidence", "npc_id": 7, "hash": 12,
                    "corpus_indices": [4], "canonical_ids": [line["lineId"]]}
            sources = {(scope, 13): {"scope": scope, "hash": 13, "english": "Hello <name>!",
                                     "file": "fixture.lua", "key_line": 8}
                       for scope in (7, "!common", 8)}
            counts = candidate_tables(root, "test", "pin", [line], [pair], sources, {},
                                     {7: [{"expansion": "classic", "name": "fixture"}]})
            self.assertEqual(counts["pairs_with_catalog_id_and_name"], 1)
            self.assertEqual(counts["pairs_with_competing_text_leads"], 1)
            with (root / "pairs-test.csv").open(encoding="utf-8-sig", newline="") as stream:
                pair_row, = csv.DictReader(stream)
            self.assertEqual(len(json.loads(pair_row["classicua_candidates"])), 2)
            with (root / "links-test.csv").open(encoding="utf-8-sig", newline="") as stream:
                links = list(csv.DictReader(stream))
            self.assertEqual([(r["test"], r["source_scope"]) for r in links],
                             [("same_template", "7"), ("same_template", "!common")])
            self.assertEqual(template("$C$B$B7"), "<class> 7")
            self.assertNotEqual(tokens(template("$R")), tokens(template("$N")))

    def test_one_word_review_preserves_length_and_order(self):
        words = tuple("a b c d e f".split())
        self.assertTrue(one_edit(words, (*words, "g")))
        self.assertTrue(one_edit(words, (*words[:-1], "g")))
        self.assertFalse(one_edit(words, words))
        self.assertFalse(one_edit(words, tuple(reversed(words))))
        self.assertFalse(one_edit(words, words[:-1]))

    def test_layout_candidates_preserve_both_sources_and_do_not_count_as_direct(self):
        sources = {}
        for english in ("A\nB", "A\n\nB"):
            digest = classicua_hash(english)
            sources[7, digest] = {"hash": digest, "scope": 7, "english": english}
        counts, _, pairs = audit([row("a", "A B"), row("b", "A B", npc=8)], {}, sources,
                                 {}, {}, {}, {"byNpc": {}, "common": {}}, [])
        self.assertEqual(nonzero(counts), {"whitespace_candidate": 1, "no_evidence": 1})
        self.assertEqual(len(pairs[0]["whitespace_candidates"]), 2)
        self.assertEqual(counts["context_detail"]["by_category"]["all_unmatched"]["originals"], 1)
        self.assertEqual(counts["context_detail"]["source_records_by_lookup_result"],
                         {"original_absent_from_corpus": 2})

    def test_recording_field_transform_requires_exact_result_and_gender(self):
        self.assertEqual(prepared_reason("A$B$BB", "A\n\nB", None), "line_breaks_only")
        self.assertEqual(prepared_reason("$G one:two;", "one", "m"), "player_gender_branch_only")
        self.assertEqual(prepared_reason("$G one:two;", "one", "f"), "other_preparation")
        self.assertEqual(prepared_reason("Dear $R", "Dear Traveler", None), "tts_race_substitution_only")

    def test_comment_parity_and_provenance(self):
        self.assertEqual(classicua_hash("  ABC\u00a0 "), 2837061266)
        digest = classicua_hash("Hello.\n\nWelcome.")
        data = ('local _, addonTable = ...\naddonTable.gossip = {\n[7] = {\n'
                '-- Hello.\n--\n-- Welcome.\n'
                f'[{digest}] = "invented",\n}}\n}}\n')
        source, = source_comments(data, "fixture.lua")
        self.assertEqual((source["scope"], source["comment_first_line"], source["key_line"]), (7, 4, 7))
        with self.assertRaisesRegex(ValueError, r"fixture.lua:7"):
            list(source_comments(data.replace("Hello.", "Goodbye."), "fixture.lua"))

    def test_duplicate_wordings_preserve_ids_and_common_precedence(self):
        digest = classicua_hash("Welcome")
        exact = {"scope": 7, "hash": digest, "english": "Welcome"}
        common = {**exact, "scope": "!common"}
        legacy = {"byNpc": {7: {digest: "fixture"}}, "common": {digest: "fixture"}}
        counts, _, evidence = audit(
            [row("a", "Welcome", suffix=":m"), row("a", "Welcome", suffix=":f"),
             row("b", "WELCOME", npc=8), row("c", "Welcome", kind="object")],
            {}, {(7, digest): exact, ("!common", digest): common}, {}, {}, {}, legacy, [])
        self.assertEqual(nonzero(counts), {"exact_npc": 1, "exact_common": 1})
        self.assertEqual(counts["exclusions"], {"unsupported_context": 1})
        self.assertEqual(counts["unique_normalized_english"], 1)
        self.assertEqual(len(evidence[0]["canonical_ids"]), 2)

    def test_alias_dynamic_reply_and_collision_stay_distinct(self):
        text = "Welcome home"
        digest = classicua_hash(text)
        source = {"scope": 7, "hash": digest, "english": text}
        legacy = {"byNpc": {7: {digest: "fixture"}}, "common": {}}
        lines = [row("a", "Welcome back"), row("b", text), row("c", "Unknown words", npc=8),
                 row("d", "The welcome home")]
        aliases = {"a" * 32: ["b" * 32]}
        dynamic = {8: [{"pattern": "un.-ws", "hash": 1}]}
        counts, _, _ = audit(lines, aliases, {(7, digest): source}, dynamic, {}, {}, legacy, [])
        self.assertEqual(nonzero(counts), {"verified_alias_wording": 1, "exact_npc": 1,
                                          "dynamic_candidate": 1, "reply_only_candidate": 1})
        self.assertEqual(dynamic_code("Night elf!", [("night elf", "nightelf")]), "nf")
        self.assertTrue(dynamic_match("a" * 43, "a" * 42))
        self.assertFalse(dynamic_match("abcd", "ab"))
        self.assertIn("bank", replies("The bank"))
        with (patch("tools.gossip_mapping_audit.classicua_hash", return_value=digest),
              patch("tools.gossip_coverage.classicua_hash", return_value=digest)):
            counts, _, _ = audit([row("b", text), row("d", "Different")], {},
                                 {(7, digest): source}, {}, {}, {}, legacy, [])
        self.assertEqual(nonzero(counts), {"hash_collision": 1})

    def test_git_object_revision_and_fingerprint(self):
        data = {CORPUS_PATH: gzip.compress(b'{"lines": []}'),
                ALIAS_PATH: b"{}", TOC_PATH: b"## Version: 3.10.1\n"}
        pin = {"revision": "a" * 40, "version": "3.10.1",
               "files": {name: sha256(blob).hexdigest() for name, blob in data.items()}}
        with patch("tools.gossip_mapping_audit.subprocess.run") as git:
            git.side_effect = lambda args, **_: type("Result", (), {
                "stdout": data[args[-1].split(":", 1)[1]]})()
            self.assertEqual(spoken_baseline(Path("."), pin), ([], {}))
            self.assertIn(pin["revision"] + ":" + TOC_PATH, git.call_args.args[0])
            data[ALIAS_PATH] = json.dumps({"changed": []}).encode()
            with self.assertRaisesRegex(ValueError, "pin mismatch"):
                spoken_baseline(Path("."), pin)

    def test_zip_entries_and_source_fingerprint(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "gossip.zip"
            data = render_gossip_lua({"byNpc": {7: {13: "invented"}}, "common": {19: "other"}})
            with ZipFile(path, "w") as archive:
                archive.writestr("Fixture/GossipTranslations.lua", data)
            sidecar = path.with_suffix(".zip.sha256")
            sidecar.write_text(sha256(path.read_bytes()).hexdigest(), encoding="utf-8")
            counts = zip_inventory(path, {(7, 13): {
                "translation_sha256": sha256(b"invented").hexdigest()}})
            self.assertEqual((counts["npc_hash_entries"], counts["common_hash_entries"],
                              counts["exact_classicua_payload_entries"]), (1, 1, 1))
            sidecar.write_text("incorrect", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                zip_inventory(path, {})
