"""Stage 4A synthetic inventory integration; no upstream text is committed."""
import gzip
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.crosswalk import VerifiedTarget, digest
from adapters.spoken import Inventory
from adapters.spoken.text_index import index_verified_originals
from adapters.translation_sources import (
    AlternativeSourceStub, ClassicUAProvider, OwnTranslatorMock, SourcePolicy,
    TranslationRequest, resolve_spoken_batch,
)
from tools.stage4_coverage import build_coverage


class SyntheticReader:
    """Invented texts; fake reader models a *previously pinned* public reader."""
    def __init__(self, lines=None):
        self.lines = lines or [
            {"source": "accept", "lineId": "q:41:accept", "originalText": "Fictional quest description."},
            {"source": "gossip", "lineId": "g:" + "a" * 32,
             "originalText": "Fictional NPC greeting."},
        ]
        self.calls = []

    def read(self, path):
        self.calls.append(path)
        if path == "pipelines/quests/corpus/corpus.json.gz":
            return gzip.compress(json.dumps({"lines": self.lines}).encode("utf-8"))
        if path == "addons/Spoken_Readables/Data/Books.lua":
            return (b'SpokenReadablesData = { pages = { [123] = '
                    b'{ text = "Fictional book page." } } }')
        raise ValueError("synthetic_unknown_public_reference")


def inventory_for(*, bad_context=False, extra_quest_context=()):
    ids = {
        "q:41:accept": ("quest", "pipelines/quests/corpus/corpus.json.gz",
                        [{"wording_sha256": digest("Fictional quest description.")}] +
                         list(extra_quest_context)),
        "g:" + "a" * 32: ("gossip", "pipelines/quests/corpus/corpus.json.gz",
                          [{"wording_sha256": digest("Fictional NPC greeting.")}]),
        "b:123": ("readable", "addons/Spoken_Readables/Data/Books.lua",
                  [{"wording_sha256": digest("Fictional book page.")}]),
        "z:54": ("places", "pipelines/places/tools/seed/zones.json", [{}]),
        "boss:2:ogre": ("bosses", "addons/Spoken_Bosses/Data/Bosses.lua", [{}]),
    }
    revision = "1" * 40
    targets = {k: VerifiedTarget(k, f, revision, path, "a" * 64)
               for k, (f, path, _) in ids.items()}
    contexts = {k: rows for k, (_, _, rows) in ids.items()}
    if bad_context:
        contexts["q:41:accept"] = [{"wording_sha256": "0" * 64}]
    return Inventory(targets, contexts, {}, revision, {})


class Stage4CoverageTests(unittest.TestCase):
    def setUp(self):
        self.reader = SyntheticReader()
        self.inventory = inventory_for()

    def report(self, sources, client_locale=None, *, reader=None, inventory=None):
        return build_coverage(reader or self.reader, inventory or self.inventory,
                              SourcePolicy(tuple(sources)), client_locale)

    def test_real_canonical_index_with_english_originals(self):
        index = index_verified_originals(self.reader, self.inventory)
        self.assertEqual(set(index.original_english),
                         {"q:41:accept", "g:" + "a" * 32, "b:123"})
        self.assertEqual(len(index.unresolved), 2)
        self.assertEqual(index.families["quest"]["with_original"], 1)
        self.assertEqual(index.families["places"]["without_verified_original"], 1)
        self.assertEqual(index.families["bosses"]["without_verified_original"], 1)

    def test_no_approved_joins_means_no_translation_even_if_source_is_enabled(self):
        report = self.report(["classicua", "another", "own_translator", "original_english"])
        self.assertEqual(report["coverage"]["total_spoken_identities"], 5)
        self.assertEqual(report["coverage"]["with_verified_public_original"], 3)
        self.assertEqual(report["coverage"]["without_verified_public_original"], 2)
        self.assertEqual(report["coverage"]["approved_translations"], 0)
        self.assertEqual(report["coverage"]["translation_candidates_pending_review"], 0)
        self.assertEqual(report["coverage"]["original_english_selected"], 3)
        self.assertEqual(len(report["records"]), 5)
        self.assertEqual(sum(s["candidate_translations"] for s in report["stages"]), 0)
        self.assertEqual([s["remaining_for_next_source"] for s in report["stages"]],
                         [3, 3, 3, 0])
        self.assertEqual(report["stages"][2]["mock_skipped"], 3)
        self.assertEqual({r["status"] for r in report["records"]},
                         {"original_english", "public_original_not_verified"})

    def test_empty_policy_uses_explicit_real_client_locale_without_calls(self):
        report = self.report([], "deDE")
        self.assertEqual(report["coverage"]["client_language_selected"], 3)
        self.assertEqual(report["coverage"]["original_english_selected"], 0)
        self.assertEqual(report["stages"], [])
        self.assertEqual(len([r for r in report["records"]
                              if r["client_locale"] == "deDE"]), 3)

    def test_english_first_and_only_skip_all_ukrainian_sources(self):
        report = self.report(["original_english", "classicua", "own_translator"])
        self.assertEqual([s["source"] for s in report["stages"]], ["original_english"])
        self.assertEqual(report["coverage"]["original_english_selected"], 3)
        self.assertEqual(report["coverage"]["translation_candidates_pending_review"], 0)

    def test_without_english_source_rows_stay_untranslated(self):
        report = self.report(["classicua"])
        self.assertEqual(report["coverage"]["untranslated_with_public_original"], 3)
        self.assertEqual(report["coverage"]["original_english_selected"], 0)
        self.assertEqual({r["status"] for r in report["records"]},
                         {"untranslated", "public_original_not_verified"})

    def test_report_metadata_has_no_copyrightable_dialogue_or_pages(self):
        report = json.dumps(self.report(["original_english"]), ensure_ascii=False)
        for line in ("Fictional quest description.", "Fictional NPC greeting.",
                     "Fictional book page."):
            self.assertNotIn(line, report)
        self.assertNotIn("source_identity", report)

    def test_source_text_does_not_become_identity_for_classicua_lookup(self):
        index = index_verified_originals(self.reader, self.inventory)
        requests = [TranslationRequest(None, text, identity)
                    for identity, text in index.original_english.items()]
        seen = []

        class RecordingClassicUA(ClassicUAProvider):
            def lookup(self, request):
                seen.append(request.source_identity)
                return super().lookup(request)

        # A source field with a matching *target ID string* must not be assumed
        # to be a real human-reviewed source↔target join.
        registry = {"classicua": RecordingClassicUA({}), "another": AlternativeSourceStub(),
                    "own_translator": OwnTranslatorMock()}
        r = resolve_spoken_batch(requests, SourcePolicy(("classicua",)), registry,
                                 self.inventory.targets)
        self.assertEqual(seen, [None] * 3)
        self.assertEqual(r.metadata()["translation_candidates_pending_review"], 0)

    def test_original_context_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "public_original_context_mismatch"):
            index_verified_originals(self.reader, inventory_for(bad_context=True))

    def test_multiple_verified_original_wordings_remain_ambiguous(self):
        second = "Alternative invented English wording."
        reader = SyntheticReader(lines=self.reader.lines + [{
            "source": "accept", "lineId": "q:41:accept", "originalText": second}])
        inventory = inventory_for(extra_quest_context=({"wording_sha256": digest(second)},))
        index = index_verified_originals(reader, inventory)
        self.assertNotIn("q:41:accept", index.original_english)
        self.assertIn("q:41:accept", index.unresolved)

    def test_single_and_batch_requests_allow_unmatched_sources_without_forging_id(self):
        req = TranslationRequest(None, "Invented English", "q:41:accept", "deDE")
        r = resolve_spoken_batch((req,), SourcePolicy(("classicua", "original_english")),
                                 {"classicua": ClassicUAProvider({})}, self.inventory.targets)
        self.assertEqual(r.metadata()["original_english_fallback"], 1)
        with self.assertRaisesRegex(ValueError, "source_identity_and_english_text_required"):
            TranslationRequest("", "Invented English", "q:41:accept")


if __name__ == "__main__":
    unittest.main()
