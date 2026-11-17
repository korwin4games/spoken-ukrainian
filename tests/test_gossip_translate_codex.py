"""Codex CLI one-batch translation safety; entirely synthetic, no model calls."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import gossip_translate_codex as codex

A="a"*40
B="b"*40

class CodexDraftTests(unittest.TestCase):
    def fixture(self, directory):
        root=Path(directory)
        build=root/"build"
        batch=build/"gossip-batches/batch-0001.json"
        batch.parent.mkdir(parents=True)
        groups=[]
        for i, text in enumerate(("Hello <name>.", "Another greeting.")):
            key=str(i+1)*64
            groups.append({
                "group_id":key,"english_sha256":key,
                "context_sha256":str(i+3)*64,
                "english":text,"occurrence_count":1,
                "contexts":[{"npc_id":42+i,"npc_name":"Synthetic NPC"}]
            })
        queue={"spoken_revision":A,"classicua_revision":B,"groups":groups}
        batchdata={"schema_version":1,"spoken_revision":A,"classicua_revision":B,
          "entries":[{"group_id":g["group_id"],"english_sha256":g["english_sha256"],
            "context_sha256":g["context_sha256"],"english_original":g["english"],
            "occurrence_count":g["occurrence_count"],"ukrainian_text":""} for g in groups]}
        (build/"gossip-translation-queue.json").write_text(json.dumps(queue))
        batch.write_text(json.dumps(batchdata))
        (root/"sources.lock.json").write_text(json.dumps(
            {"spoken":{"revision":A},"classicua":{"revision":B}}))
        return build,batch,groups

    def test_invalid_and_missing_translations_fail_without_written_drafts(self):
        rows=[{"group_id":"a","english_original":"Hello <name>."}]
        for result in (
            {"translations":[]},
            {"translations":[{"group_id":"b","ukrainian_text":"Вітаю <name>."}]},
            {"translations":[{"group_id":"a","ukrainian_text":"Вітаю."}]},
            {"translations":[{"group_id":"a","ukrainian_text":"hi","extra":1}]},
        ):
            with self.subTest(result=result), self.assertRaises(ValueError):
                codex.accepted_translations(rows,result)
        self.assertEqual(codex.accepted_translations(rows, {
          "translations":[{"group_id":"a","ukrainian_text":"Вітаю <name>."}]}),
          {"a":"Вітаю <name>."})

    def test_codex_only_runs_on_opt_in_and_updates_only_blank_fields(self):
        with TemporaryDirectory() as d:
            build,path,groups=self.fixture(d)
            def fake(cmd, prompt, output):
                self.assertEqual(cmd[0:4],["codex","exec","--sandbox","read-only"])
                self.assertIn('"entries"',prompt)
                output.write_text(json.dumps({"translations":[
                    {"group_id":groups[0]["group_id"],"ukrainian_text":"Вітаю <name>."},
                    {"group_id":groups[1]["group_id"],"ukrainian_text":"Вітаємо!"}]}),
                    encoding="utf-8")
                return SimpleNamespace(returncode=0)
            with patch.object(codex,"BUILD",build),patch.object(codex,"QUEUE",build/"gossip-translation-queue.json"),patch.object(codex,"ROOT",Path(d)):
                report=codex.translate(path)
                self.assertFalse(report["applied"])
                self.assertEqual(report["pending"],2)
                report=codex.translate(path,apply=True,runner=fake)
                self.assertEqual(report["translated_now"],2)
                result=json.loads(path.read_text())
                self.assertEqual(result["entries"][0]["ukrainian_text"],"Вітаю <name>.")
                self.assertEqual(result["entries"][0]["english_original"],"Hello <name>.")
                self.assertEqual(codex.translate(path,apply=True,runner=fake)["pending"],0)

    def test_dry_run_and_source_mismatch_never_invoke_codex(self):
        with TemporaryDirectory() as d:
            build,path,groups=self.fixture(d)
            with patch.object(codex,"BUILD",build),patch.object(codex,"QUEUE",build/"gossip-translation-queue.json"),patch.object(codex,"ROOT",Path(d)):
                before=path.read_bytes()
                stale=json.loads((build/"gossip-translation-queue.json").read_text())
                stale["groups"][0]["context_sha256"]="9"*64
                (build/"gossip-translation-queue.json").write_text(json.dumps(stale))
                with self.assertRaisesRegex(ValueError,"stale_or_duplicate_gossip_codex_context"):
                    codex.translate(path,apply=True,runner=lambda *_: self.fail("called"))
                self.assertEqual(before,path.read_bytes())
                with self.assertRaisesRegex(ValueError,"gossip_codex_path_must_be_under_private_build"):
                    codex.translate(Path(d)/"wrong.json")
