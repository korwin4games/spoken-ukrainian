"""Stage 3 tests: invented text only, pinned public identity/parity evidence."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_crosswalk import Fixture
from lua_runtime import run_lua
from adapters.crosswalk import (VerifiedTarget, approve_mapping, VerifiedJoin, digest,
                                effective_units, compare_effective, metadata_json)
from adapters.mapping import (load_reviews, review_file, retain_review, assess_review,
                              candidates, coverage_report, target_context)
from adapters.spoken import PublicSource, build_index, Inventory, literal_data
from adapters.spoken.evidence import JoinProof, approve_review, proof_digest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('SPOKEN_SOURCE', ROOT.parent / 'spoken-wow'))


def synthetic_inventory(family='quest', identity='q:42:accept', contexts=None):
    target = VerifiedTarget(identity, family, 'a' * 40, 'invented-public-reference', 'a' * 64)
    context = {'npc_id': 7, 'npc_type': 'creature', 'voice': 'invented-voice', 'faction': 'horde',
               'player_gender': None, 'wording_sha256': digest('invented wording'),
               'source': 'accept', 'quest_id': 42, 'generatable': True}
    return Inventory({identity: target}, {identity: contexts or [context]}, {}, 'a' * 40, {})


def reviewed():
    inv = synthetic_inventory()
    f = Fixture().add('quest_both', 'classic', '{[42]={nil,"invented wording"}}')
    u = f.units()['quest:horde:42:accept']
    facts = {k: v for k, v in inv.contexts['q:42:accept'][0].items() if k != 'generatable'}
    proof = JoinProof(u.context_sha256, target_context(inv, 'q:42:accept'), facts,
                      'invented-identity-reference', 'b' * 64, 'invented-public-reference',
                      'a' * 64, 'Invented evidence reviewer')
    u = replace(u, identity_evidence_sha256=proof_digest(proof))
    r = approve_review(u, 'q:42:accept', inv, proof, 'Invented mapping reviewer')
    return inv, u, r, proof


class ReviewTests(unittest.TestCase):
    def test_schema_round_trip_unknown_fields_duplicates_and_versions(self):
        inv, u, r, _ = reviewed()
        data = review_file([r])
        self.assertEqual(load_reviews(json.loads(json.dumps(data))), [r])
        for bad in [data | {'text': 'SECRET'}, data | {'schema_version': 2},
                    data | {'decisions': data['decisions'] * 2}]:
            with self.assertRaises(ValueError):
                load_reviews(bad)
        self.assertNotIn('invented wording', metadata_json(data))

    def test_mapping_survives_revision_and_file_only_drift(self):
        inv, u, r, _ = reviewed()
        d = replace(r.decision, content_status='approved', grammar_status='approved', ai_status='approved')
        r = replace(r, decision=d)
        newer = replace(u, source_revision='c' * 40, source_file_sha256='d' * 64)
        row = assess_review(r, {u.source_id: newer}, inv)
        self.assertEqual(row['mapping_status'], 'approved')
        self.assertEqual(row['content_status'], 'approved')
        self.assertEqual(row['target_id'], 'q:42:accept')

    def test_wording_invalidates_reviews_audio_not_identity(self):
        inv, u, r, _ = reviewed()
        row = assess_review(r, {u.source_id: replace(u, effective_sha256='f' * 64)}, inv)
        self.assertEqual(row['mapping_status'], 'approved')
        self.assertEqual(row['content_status'], 'pending')
        self.assertEqual(row['grammar_status'], 'pending')
        self.assertEqual(row['audio'], 'stale_if_present')

    def test_origin_ai_template_identity_and_removal(self):
        inv, u, r, _ = reviewed()
        for changes, key, expected in [({'origin_layer': 'forever'}, 'audio', 'stale_if_present'),
                ({'ai': True}, 'ai_status', 'pending'),
                ({'grammar_sha256': 'd' * 64}, 'audio', 'stale_if_present'),
                ({'context_sha256': 'e' * 64}, 'mapping_status', 'invalidated')]:
            with self.subTest(changes=changes):
                self.assertEqual(assess_review(r, {u.source_id: replace(u, **changes)}, inv)[key], expected)
        self.assertEqual(assess_review(r, {}, inv)['reasons'], ['source_removed'])

    def test_target_revision_voice_speaker_alias_invalidates(self):
        inv, u, r, _ = reviewed()
        for key in ['voice', 'npc_id', 'wording_sha256']:
            c = dict(inv.contexts[u.source_id.replace('quest:horde:', 'q:')][0])
            c[key] = 'changed'
            changed = replace(inv, contexts={'q:42:accept': [c]})
            self.assertEqual(assess_review(r, {u.source_id: u}, changed)['mapping_status'], 'invalidated')
        changed = replace(inv, aliases={'q:42:accept': ['q:42:accept:w1']})
        self.assertEqual(assess_review(r, {u.source_id: u}, changed)['mapping_status'], 'invalidated')
        t = replace(inv.targets['q:42:accept'], spoken_revision='b' * 40)
        self.assertEqual(assess_review(r, {u.source_id: u}, replace(inv, targets={'q:42:accept':t}))['mapping_status'], 'invalidated')

    def test_independent_proof_cannot_combine_voices_or_self_review(self):
        inv, u, _, p = reviewed()
        for proof, reviewer in [(p, p.evidence_reviewer),
                (replace(p, facts=p.facts | {'voice':'unverified-voice'}), 'Mapping reviewer'),
                (replace(p, facts={}), 'Mapping reviewer')]:
            with self.assertRaises(ValueError):
                approve_review(u, 'q:42:accept', inv, proof, reviewer)

    def test_gossip_options_and_multiple_voices_need_exact_greeting_proof(self):
        identity = 'g:' + 'a' * 32
        contexts = [{'npc_id': 7, 'npc_type': 'creature', 'voice': v, 'wording_sha256': digest('invented'),
                     'source':'gossip','player_gender':None} for v in ['voice-one', 'voice-two']]
        inv = synthetic_inventory('gossip', identity, contexts)
        u = next(iter(Fixture().add('gossip','classic','{[7]={[123]="Invented greeting"}}').units().values()))
        p = JoinProof(u.context_sha256,target_context(inv,identity),contexts[0], 'invented-greeting-reference',
                      'b'*64,'invented-public-reference','a'*64,'Evidence reviewer')
        with self.assertRaisesRegex(ValueError,'gossip_option'):
            approve_review(u,identity,inv,p,'Mapping reviewer')
        p = replace(p,greeting=True)
        u = replace(u,identity_evidence_sha256=proof_digest(p))
        self.assertEqual(approve_review(u,identity,inv,p,'Mapping reviewer').decision.target_id,identity)

    def test_readable_owner_chain_not_title_or_ordinal(self):
        c={'book':11,'number':2,'chain':[100,102], 'owners':[['item',91]],'checksum':123,'wording_sha256':digest('invented')}
        inv=synthetic_inventory('readable','b:102',[c])
        u=next(iter(Fixture().add('item_text','classic','{[91]={[2]="Invented page"}}').units().values()))
        p=JoinProof(u.context_sha256,target_context(inv,'b:102'),c,'invented-chain-reference','b'*64,
                    'invented-public-reference','a'*64,'Evidence reviewer')
        u=replace(u,identity_evidence_sha256=proof_digest(p))
        r=approve_review(u,'b:102',inv,p,'Mapping reviewer')
        for field,value in [('chain',[100,101,102]),('owners',[['item',92]]),('book',12)]:
            changed=replace(inv,contexts={'b:102':[c|{field:value}]})
            self.assertEqual(assess_review(r,{u.source_id:u},changed)['mapping_status'],'invalidated')

    def test_candidates_coverage_denominators_determinism(self):
        inv,u,r,_=reviewed()
        units={u.source_id:u}
        a=coverage_report(units,inv,[r])
        self.assertEqual(a['coverage']['quest']['confirmed_unique_canonical_intersections'],1)
        self.assertEqual(a['coverage']['places']['resolved_source_units'],0)
        self.assertEqual(metadata_json(a),metadata_json(coverage_report(dict(reversed(list(units.items()))),inv,[r])))
        self.assertEqual(candidates(units,replace(inv,targets={}))[0]['reason'],'target_unavailable')
        variant=replace(inv.targets['q:42:accept'],canonical_id='q:42:accept:w1~invented-voice')
        inv=replace(inv,targets=inv.targets|{variant.canonical_id:variant})
        self.assertEqual(candidates(units,inv)[0]['status'],'ambiguous')


class SourceSemanticTests(unittest.TestCase):
    def test_masked_override_line_drift_and_predecessors(self):
        def units(old):
            f=Fixture().add('quest_both','classic','{[42]={nil,"'+old+'"}}')
            return f.add('quest_both','forever','\n\n{[42]={nil,"Invented final"}}').units()
        a,b=units('Invented old'),units('Invented edit')
        self.assertTrue(all(x['change']=='unchanged' for x in compare_effective(a,b)))
        self.assertTrue(all(u.predecessors for u in b.values()))

    def test_same_title_namesakes_h1_chain_change(self):
        def units(h):
            return Fixture().add('object_text','classic','{["SECRET-TITLE"]={{"Invented A",h1='+str(h)+'},{"Invented B",h1=99}}}').units()
        a,b=units(88),units(89)
        self.assertEqual(set(a),set(b))
        self.assertTrue(all(x['mapping']=='revalidate' for x in compare_effective(a,b)))
        self.assertNotIn('SECRET-TITLE',metadata_json(coverage_report(a,synthetic_inventory())))
        f=Fixture().add('item_text','classic','{[91]={[1]="One",[3]="Three"},[92]={"One"}}')
        self.assertEqual(len(f.units()),3)

    def test_non_narratable_fields_and_ai_fallback(self):
        f=Fixture().add('quest_both','classic','{[42]={"title","Shared","Objective",nil,"",en="metadata"}}')
        f.add('quest_horde','forever','{[42]={nil,"AI",ai=true}}')
        ai=effective_units(f.dataset,include_ai=False)
        self.assertFalse(ai['quest:horde:42:accept'].ai)
        self.assertEqual(ai['quest:horde:42:accept'].source_category,'quest_both')
        f.add('gossip','classic','{[7]={[1]="Greeting",[2]={"unsupported option"},["!code"]={x="metadata"}},["!common"]={[4]="Common"}}')
        self.assertEqual(sum(u.family=='gossip' for u in f.units().values()),1)

    def test_unicode_grammar_template_impact(self):
        a=Fixture().add('quest_both','classic','{[42]={nil,"Привіт, {ім’я}"}}').units()
        b=Fixture().add('quest_both','classic','{[42]={nil,"Привіт, {ім’я:р}"}}').units()
        self.assertTrue(all('grammar_changed' in r['reasons'] for r in compare_effective(a,b)))


class PublicIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((ROOT/'tests/stage3_sources.json').read_text())
        cls.reader=PublicSource(SOURCE,cls.manifest)
        cls.index=build_index(cls.reader)

    def test_pinned_counts_and_no_body_export(self):
        from collections import Counter
        self.assertEqual(dict(Counter(t.family for t in self.index.targets.values())),
                         {'quest':12594,'gossip':4641,'readable':1160,'places':947,'bosses':297})
        for target in self.index.targets.values():
            if target.family == 'readable':
                self.assertTrue(all(isinstance(owner, list) for owner in self.index.contexts[target.canonical_id][0]['owners']))
        self.assertEqual(set(self.reader.hashes),set(self.manifest['files']))
        for cs in self.index.contexts.values():
            for c in cs:
                self.assertNotIn('text',c)
                self.assertNotIn('originalText',c)

    def test_modified_digest_and_unpinned_path_rejected(self):
        p='pipelines/quests/tts_cli/naming.py'
        reader=PublicSource(SOURCE,self.manifest|{'files':{p:'0'*64}})
        with self.assertRaisesRegex(ValueError,'digest_mismatch'):reader.read(p)
        with self.assertRaisesRegex(ValueError,'not_pinned'):reader.read('private.json')
        with self.assertRaises(ValueError):literal_data(b'X = {a=1}\nos.execute("invented")','X')

    def test_naming_parity_with_actual_pinned_python_functions(self):
        # Execute only the inspected pure naming helper, not source datasets or addon code.
        import types
        m=types.ModuleType('pinned_naming')
        exec(compile(self.reader.read('pipelines/quests/tts_cli/naming.py'),'<pinned-naming>','exec'),m.__dict__)
        self.assertEqual(m.quest_wording_line_id(42,'accept',2),'q:42:accept:w2')
        self.assertEqual(m.filename_from_line_id('q:42:accept:w2:f~invented-voice'),'f-42-accept-w2-invented-voice')
        self.assertEqual(m.line_id_for_row({'source':'gossip','quest':None,'templateText_race_gender_hash':'a'*32,'player_gender':'m'}),'g:'+'a'*32+':m')
        self.assertEqual(m.moment_of('q:42:accept:f'),'q:42:accept')

    def test_utf8_checksum_pinned_lua_vectors(self):
        source=self.reader.read('addons/Spoken_Readables/Checksum.lua').decode()
        source='local function check(...)\n'+source+'\n'
        for text in ['Invented ASCII','Вигаданий текст ї ґ','Invented\u00a0text']:
            # Inputs without markup use the actual normalizer; compute expected sum in Python.
            normal=text
            blob=normal.encode(); value=len(blob)
            for byte in blob:value=(value*31+byte)%2147483647
            from test_stage1 import quote_lua
            run_lua(source+f'assert(SpokenReadables:ChecksumOf({quote_lua(text)}) == {value})\nend\ncheck("fixture", {{}})')


class OfflineWorkflowTests(unittest.TestCase):
    def test_two_independently_pinned_effective_snapshots(self):
        from test_classicua import source_fixture, wrapped
        from tools.stage3_report import reviewed_source
        from adapters.classicua.source import audit_checkout, GitSource
        with tempfile.TemporaryDirectory() as temp:
            snapshots=[]
            for number in (1,2):
                path=Path(temp)/str(number)
                path.mkdir()
                files=source_fixture()
                files['entries/classic/quest_both.lua']=wrapped('quest_both','{[42]={nil,"Invented '+str(number)+'"}}')
                files['entries/forever/quest_both.lua']=wrapped('quest_both','{[42]={nil,"Invented final"}}')
                for extra in ['scripts/entries.lua','scripts/utils.lua','entries/class.lua','entries/race.lua']:
                    files[extra]='-- invented fixture only'
                for name,body in files.items():
                    dest=path/name
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    dest.write_text(body)
                subprocess.run(['git','init','-q',str(path)],check=True)
                subprocess.run(['git','-C',str(path),'add','.'],check=True)
                subprocess.run(['git','-C',str(path),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Invented snapshot'],check=True)
                revision=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD']).decode().strip()
                hashes={k:hashlib.sha256(v.encode()).hexdigest() for k,v in files.items()}
                manifest={'revision':revision,'files':hashes,'review_by':'Invented reviewer '+str(number)}
                dataset=reviewed_source(path,manifest)
                snapshots.append((dataset,manifest))
                with self.assertRaises(ValueError):GitSource(path)
                with self.assertRaises(ValueError):reviewed_source(path,manifest|{'review_by':''})
            self.assertNotEqual(snapshots[0][1]['revision'],snapshots[1][1]['revision'])
            self.assertTrue(all(r['change']=='unchanged' for r in compare_effective(
                effective_units(snapshots[0][0]),effective_units(snapshots[1][0]))))

    def test_cli_output_boundary_and_sanitized_failures(self):
        import sys
        for dest in ['/tmp/forbidden-stage3.json',str(ROOT/'build/failure-stage3.json')]:
            result=subprocess.run([sys.executable,str(ROOT/'tools/stage3_report.py'),
                '--classicua','/does/not/exist','--spoken','/does/not/exist','--output',dest],capture_output=True)
            self.assertEqual(result.returncode,1)
            self.assertEqual(result.stderr,b'stage3_input_or_review_validation_failed\n')
            self.assertFalse(Path(dest).exists())

    def test_tampered_stored_proof_is_rejected(self):
        inv,u,r,p=reviewed()
        evidence=r.evidence|{'facts':p.facts|{'npc_id':999}}
        tampered=replace(r,evidence=evidence)
        self.assertEqual(assess_review(tampered,{u.source_id:u},inv)['reasons'],['stored_join_proof_invalid'])
        altered = replace(r, decision=replace(r.decision, join_evidence_sha256='0'*64))
        self.assertEqual(assess_review(altered,{u.source_id:u},inv)['reasons'],['stored_join_proof_invalid'])

    def test_canonical_syntax_rejects_guessed_ids(self):
        for identity,family in [('g:12345','gossip'),('g:invented-name','gossip'),
                                ('b:0','readable'),('q:42:objective','quest'),('z:0','places')]:
            with self.assertRaises(ValueError):VerifiedTarget(identity,family,'pin','reference','a'*64)

    def test_classicua_string_hash_reviewed_vectors(self):
        from adapters.classicua.fingerprint import string_hash
        # Values independently calculated with pinned utils.lua:string_hash arithmetic.
        self.assertEqual(string_hash(''),0)
        self.assertEqual(string_hash('abc'),2837061266)

    def test_places_slug_collision_keeps_canonical_keys(self):
        import shutil
        if not shutil.which('node'):
            self.skipTest('Node unavailable; Python and Lua parity remain required')
        manifest=json.loads((ROOT/'tests/stage3_sources.json').read_text())
        reader=PublicSource(SOURCE,manifest)
        source=reader.read('pipelines/places/tools/voice/naming.mjs').decode()
        script=source+"\nconst entries=[{mapID:42,key:'invented key'},{mapID:42,key:'invented-key'}]; const files=assignFiles(entries); if(files.size!==2 || new Set(files.values()).size!==2 || !files.has('s:42:invented key')) process.exit(1);"
        result=subprocess.run(['node','--input-type=module','-e',script],capture_output=True)
        self.assertEqual(result.returncode,0)
