"""Invented Gossip imports: identity, history, SQLite and actual ZIP bytes."""
from copy import deepcopy
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock, Thread
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from adapters.gossip_machine import (
    NAME, GossipMachineStore, candidates, validate_ledger,
)
from adapters.import_statistics import read_recorded_imports, latest_successful_build, store_successful_build
from adapters.sqlite_translation_store import connection, enable_sqlite
from test_crosswalk import Fixture
from tools import build_ukrainian as builder
from tools.gossip_coverage import classicua_hash
from tools.gossip_machine_import import GossipMachineImport
from tools.gossip_translation_review import GossipReviews, discover_groups, CHECKS
from tools.review_ui_server import create_handler

REV = 'a' * 40
SP = 'b' * 40
EN = 'Hello, $N!'
UK = 'Вітаю, {ім\'я}!'
H = classicua_hash(EN)


def corpus(npc=42, english=EN, **kwargs):
    return {'source': 'gossip', 'npcType': 'creature', 'npcId': npc,
            'originalText': english, **kwargs}


def state_for(root, common=False, revision=REV, text=UK, ai=False):
    scope = '"!common"' if common else '42'
    body = '{[' + scope + ']={[' + str(H) + ']=' + json.dumps(text, ensure_ascii=False)
    body += ',ai=true' if ai else ''
    fixture = Fixture(revision=revision).add('gossip', 'classic', body + '}}')
    return SimpleNamespace(dataset=fixture.dataset, source=fixture.inventory(),
        inventory=SimpleNamespace(revision=SP),
        policy=SimpleNamespace(allows_ai_transations=lambda _: not ai,
                               sources=('classicua',), stores=lambda _: True),
        allowed_directory=root, _lock=RLock(), revalidate_inputs=lambda: None)


class GossipMachineTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.allowed = self.root / 'build'
        self.db = self.root / 'translations.sqlite3'
        self.state = state_for(self.allowed)

    def rows(self, state=None, lines=None):
        state = state or self.state
        return candidates(state, lines if lines is not None else [corpus()], builder.local_gossip_texts(state))

    def store(self):
        return GossipMachineStore(self.allowed / NAME, self.allowed)

    def test_exact_npc_hash_utf8_placeholders_and_provenance(self):
        rows, items, unknown = self.rows(lines=[corpus(), corpus(), corpus(43)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['bindings'], [42])
        self.assertEqual(rows[0]['approval_status'], 'unreviewed')
        self.assertEqual(rows[0]['text'], UK)
        self.assertEqual(rows[0]['source_provenance']['revision'], REV)
        self.assertEqual([i['status'] for i in items], ['eligible', 'untranslated'])
        self.assertEqual(unknown, 0)
        store = self.store()
        self.assertEqual(store.run(rows), 1)
        self.assertEqual(store.lookup(rows)['byNpc'][42][H], UK)
        bad = deepcopy(store.file.data)
        bad['versions'][0]['text'] += '!'
        with self.assertRaises(ValueError):
            validate_ledger(bad)

    def test_common_is_single_translation_with_multiple_npc_occurrences(self):
        state = state_for(self.allowed, common=True)
        rows, _, _ = self.rows(state, [corpus(), corpus(43), corpus(43)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['bindings'], [42, 43])
        store = self.store()
        self.assertEqual(store.run(rows), 1)
        self.assertEqual(store.lookup(rows), {'byNpc': {}, 'common': {H: UK}})

    def test_specific_and_common_precedence_without_duplicate_source_entries(self):
        state = state_for(self.allowed, common=True)
        fixture = Fixture(revision=REV).add('gossip', 'classic',
            '{["!common"]={[' + str(H) + ']="Спільний приклад."},'
            '[42]={[' + str(H) + ']="Окремий приклад."}}')
        state.dataset, state.source = fixture.dataset, fixture.inventory()
        rows, _, _ = self.rows(state, [corpus(), corpus(43)])
        self.assertEqual(len(rows), 2)
        store = self.store()
        store.run(rows)
        lookup = store.lookup(rows)
        self.assertEqual(lookup['byNpc'][42][H], 'Окремий приклад.')
        self.assertEqual(lookup['common'][H], 'Спільний приклад.')

    def test_source_route_change_does_not_reimport_old_npc_binding(self):
        rows, _, _ = self.rows()
        store = self.store()
        store.run(rows)
        changed = state_for(self.allowed, common=True)
        common_rows, _, _ = self.rows(changed)
        self.assertEqual(store.run(common_rows), 0)
        self.assertEqual(store.lookup(common_rows), {'byNpc': {}, 'common': {}})
        self.assertEqual(len(store.file.data['versions']), 3)

    def test_shared_wording_remains_npc_scoped_and_ambiguous_context_excluded(self):
        rows, items, _ = self.rows(lines=[corpus(), corpus(npcType='vehicle')])
        self.assertEqual(rows, [])
        self.assertEqual(items[0]['status'], 'conflict')
        rows, items, unknown = self.rows(lines=[corpus(npcType='object'), corpus(npc=-1)])
        self.assertEqual(rows, [])
        self.assertEqual(unknown, 2)
        common = state_for(self.allowed, common=True)
        rows, items, _ = self.rows(common, [corpus(), corpus(npcType='vehicle'), corpus(43)])
        self.assertEqual(rows, [])
        self.assertTrue(all(i['status'] == 'conflict' for i in items))

    def test_empty_or_disabled_provider_never_imports(self):
        self.state.policy.sources = ()
        with patch('tools.gossip_coverage.read_pinned_corpus', return_value=[corpus()]), patch.object(
                builder, 'local_gossip_texts') as lookup:
            service = GossipMachineImport(self.state, '/unused')
            self.assertEqual(service.run()['machine_imported'], 0)
            lookup.assert_not_called()

    def test_global_hash_collision_never_enters_npc_or_common_import(self):
        for common in (False, True):
            state = state_for(self.allowed, common=common)
            with patch('tools.gossip_coverage.classicua_hash', return_value=H):
                lines = [corpus(), corpus(43, 'Different sentence')]
                rows, items, _ = self.rows(state, lines)
                self.assertFalse(discover_groups(lines, {'byNpc': {}, 'common': {}}, SP, REV)[0])
                from tools.source_revision_review import gossip_contexts
                self.assertEqual(gossip_contexts(lines), {})
            self.assertEqual(rows, [])
            self.assertTrue(all(i['status'] == 'conflict' for i in items))

    def test_npc_type_ambiguity_is_blocked_by_every_review_path(self):
        from tools.source_revision_review import gossip_contexts
        lines = [corpus(), corpus() | {'npcType': 'vehicle'}, corpus(43)]
        state = state_for(self.allowed, common=True)
        lookup = builder.local_gossip_texts(state)
        rows, items, _ = self.rows(state, lines)
        self.assertEqual(rows, [])
        self.assertEqual([item['status'] for item in items], ['conflict', 'conflict'])
        groups, _ = discover_groups(lines, {'byNpc': {}, 'common': {}}, SP, REV)
        self.assertEqual([c['npc_id'] for g in groups for c in g['contexts']], [43])
        trusted = gossip_contexts(lines)
        self.assertNotIn(('gossip', f'gossip:42:{H}'), trusted)
        self.assertFalse(trusted['gossip', f'gossip:43:{H}']['common_safe'])
        from tools.source_revision_review import classicua_snapshot
        state.translation_observations = lambda: []
        self.assertEqual(classicua_snapshot(state, trusted, lookup)['records'], [])

    def test_ai_policy_and_source_file_verification(self):
        state = state_for(self.allowed, ai=True)
        self.assertEqual(self.rows(state)[0], [])
        state.policy.allows_ai_transations = lambda _: True
        self.assertTrue(self.rows(state)[0][0]['ai'])
        state.source = SimpleNamespace(revision=REV, files={})
        with self.assertRaisesRegex(ValueError, 'unverified_classicua_gossip_source'):
            self.rows(state)

    def test_duplicate_source_target_rejected(self):
        rows, _, _ = self.rows()
        with self.assertRaises(ValueError):
            self.store().run(rows + rows)

    def test_repeated_imports_sqlite_persistence_and_concurrent_change(self):
        rows, _, _ = self.rows()
        with enable_sqlite(self.db):
            store = self.store()
            store.run(rows)
            first = deepcopy(store.file.data)
            store.run(rows)
            self.assertEqual(first, store.file.data)
            self.assertEqual(first, self.store().file.data)
            stale = self.store()
            store.run(rows, blocked=[rows[0]['target_id']])
            with self.assertRaisesRegex(ValueError, 'conflict'):
                stale.run(rows)
        with connection(self.db) as db:
            self.assertEqual(db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0], 9)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ledger_documents').fetchone()[0], 1)

    def test_changed_revision_pending_update_and_revert_stays_pending(self):
        rows, _, _ = self.rows()
        store = self.store()
        store.run(rows)
        changed = state_for(self.allowed, revision='c' * 40, text='Новий текст.')
        new_rows, _, _ = self.rows(changed)
        self.assertEqual(store.lookup(new_rows), {'byNpc': {}, 'common': {}})
        self.assertEqual(store.run(new_rows), 0)
        self.assertEqual(len(store.file.data['versions']), 2)
        self.assertEqual(store.file.data['versions'][0]['approval_status'], 'unreviewed')
        self.assertEqual(store.run(new_rows), 0)
        self.assertEqual(len(store.file.data['versions']), 2)
        self.assertEqual(store.run(rows), 0)
        self.assertIn(UK, [r['text'] for r in store.file.data['versions']])

    def test_missing_source_invalidates_but_preserves_history(self):
        rows, _, _ = self.rows()
        store = self.store()
        store.run(rows)
        store.run([])
        self.assertEqual(store.file.data['imports'], [])
        self.assertEqual(len(store.file.data['versions']), 2)
        self.assertEqual(store.run(rows), 0)

    def test_manual_pending_rejected_deferred_approved_all_block_automation(self):
        for decision in ('pending', 'rejected', 'deferred', 'approved'):
            with self.subTest(decision=decision), TemporaryDirectory() as directory:
                root = Path(directory) / 'build'
                state = state_for(root)
                groups, _ = discover_groups([corpus()], {'byNpc': {}, 'common': {}}, SP, REV)
                manual = GossipReviews(groups, SP, REV, root / 'gossip-translation-reviews.json', root)
                group = groups[0]
                manual.propose([{k: group[k] for k in ('group_id', 'english_sha256', 'context_sha256')} |
                               {'ukrainian_text': 'Ручний приклад.'}], 'manual')
                if decision != 'pending':
                    manual.decide(manual.file.data['versions'][0]['id'], decision, 'reviewer',
                                  {k: decision == 'approved' for k in CHECKS})
                before = deepcopy(manual.file.data)
                service = GossipMachineImport(state, '/unused')
                with patch('tools.gossip_coverage.read_pinned_corpus', return_value=[corpus()]):
                    self.assertEqual(service.run()['machine_imported'], 0)
                    self.assertEqual(service.page()['statuses_npc_wordings'][decision], 1)
                self.assertEqual(before, manual.file.data)

    def test_common_manual_block_cannot_leak_to_other_npcs(self):
        state = state_for(self.allowed, common=True)
        groups, _ = discover_groups([corpus()], {'byNpc': {}, 'common': {}}, SP, REV)
        reviews = GossipReviews(groups, SP, REV, self.allowed / 'gossip-translation-reviews.json', self.allowed)
        group = groups[0]
        reviews.propose([{k: group[k] for k in ('group_id', 'english_sha256', 'context_sha256')} |
                        {'ukrainian_text': 'Інший приклад.'}], 'manual')
        with patch('tools.gossip_coverage.read_pinned_corpus', return_value=[corpus(), corpus(43)]):
            service = GossipMachineImport(state, '/unused')
            service.run()
            self.assertEqual(service.build_lookup(), {'byNpc': {}, 'common': {}})

    def test_npc_scoped_source_review_does_not_block_shared_machine_import(self):
        state = state_for(self.allowed, common=True)
        target = f"gossip:42:{H}"
        with patch('tools.gossip_coverage.read_pinned_corpus', return_value=[corpus(), corpus(43)]), patch(
                'tools.gossip_machine_import.source_review_targets', return_value={target}):
            service = GossipMachineImport(state, '/unused')
            _, items, _, blocked, _ = service.inspect()
            self.assertEqual(blocked, {target})
            self.assertEqual([row["status"] for row in items], ["source_selected", "eligible"])
            service.run()
            self.assertEqual(service.build_lookup(), {"byNpc": {}, "common": {H: UK}})

    def test_migrate_v4_database_preserves_old_snapshot(self):
        with connection(self.db) as db:
            db.execute('ALTER TABLE build_import_units DROP COLUMN text_sha256')
            db.execute('DELETE FROM schema_migrations WHERE version=5')
            db.execute("DELETE FROM schema_migrations WHERE version >= 5")
            db.execute("""INSERT INTO build_import_snapshots
                (id, fingerprint, artifact_sha256, spoken_revision, classicua_revision, created_at)
                VALUES(1, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                       ('d' * 64, 'e' * 64, SP, REV))
        with connection(self.db) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM build_import_snapshots').fetchone()[0], 1)
            self.assertIn('text_sha256', {r[1] for r in db.execute('PRAGMA table_info(build_import_units)')})

    def test_latest_zip_can_reuse_earlier_immutable_snapshot(self):
        values = dict(spoken_revision=SP, classicua_revision=REV, rows=[])
        first = store_successful_build(self.db, artifact_sha256='d' * 64, **values)
        store_successful_build(self.db, artifact_sha256='e' * 64, **values)
        reused = store_successful_build(self.db, artifact_sha256='d' * 64, **values)
        self.assertFalse(reused['new_snapshot'])
        self.assertEqual(latest_successful_build(self.db)['snapshot_id'], first['snapshot_id'])

    def test_actual_zip_and_statistics_repeated_build_idempotent(self):
        state = self.state
        state.translation_action = Mock(return_value={'report': {'total_spoken_records': 1,
            'machine_one_to_one_imported': 1, 'human_reviewed_imported_total': 0}})
        state.machine_imports = SimpleNamespace(file=SimpleNamespace(data={'versions': [], 'imports': []}))
        state.translations = state.machine_imports
        # Preview provenance uses an explicit selected Quest version.
        def preview(_state, selected):
            selected.append({'target_id': 'q:1:accept', 'provider': 'manual', 'ukrainian_text': 'Квест.'})
            return {1: {'accept': {'text': 'Квест.', 'reviewed': True}}}, 1, 0
        # A second NPC/hash is intentionally ambiguous and must not be serialized.
        lines = [corpus(), corpus(43, 'Untranslated example.'), corpus(44, 'Unknown.', npcType='object'),
                 corpus(45, 'Reviewed greeting.')]
        with enable_sqlite(self.db):
            groups, _ = discover_groups(lines, builder.local_gossip_texts(state), SP, REV)
            group = next(g for g in groups if g['contexts'][0]['npc_id'] == 45)
            manual = GossipReviews(groups, SP, REV, self.allowed / 'gossip-translation-reviews.json', self.allowed)
            manual.propose([{k: group[k] for k in ('group_id', 'english_sha256', 'context_sha256')} |
                            {'ukrainian_text': 'Ручний перевірений текст.'}], 'manual')
            manual.decide(manual.file.data['versions'][0]['id'], 'approved', 'human', {k: True for k in CHECKS})
            manual.import_approved()
            human_history = deepcopy(manual.file.data)
        write_zip = builder.write_zip
        with enable_sqlite(self.db), patch.object(builder, 'validate_source_paths'), patch.object(
                builder, 'build_state', return_value=state), patch.object(builder, 'current_quest_texts', side_effect=preview), patch.object(
                builder, 'unknown_faction_import_counts', return_value={}), patch.object(builder, 'read_classicua_inflections', return_value={}), patch.object(
                builder, 'local_gossip_titles', return_value={}), patch.object(builder, 'import_reason_for_quest', return_value={}), patch(
                'tools.gossip_coverage.read_pinned_corpus', return_value=lines), patch(
                'tools.gossip_translation_review.load_reviewed_gossip',
                side_effect=lambda state, existing, spoken: manual.imported_by_npc(existing)), patch.object(
                builder, 'DIST', self.root / 'dist'), patch.object(builder, 'write_zip',
                    side_effect=lambda entries, destination: write_zip(entries, self.root / 'dist/test.zip')):
            first = builder.build('/unused/ua', '/unused/spoken', module=builder.GOSSIP_MODULE)
            with ZipFile(first['artifact']) as archive:
                text = archive.read('Spoken_Gossip_UA/GossipTranslations.lua').decode('utf-8')
                self.assertIn(UK, text)
                self.assertIn('[42]', text)
                self.assertNotIn('[43]', text)
                self.assertNotIn('[44]', text)
                self.assertIn('Ручний перевірений текст.', text)
                self.assertIn('[45]', text)
            again = builder.build('/unused/ua', '/unused/spoken', module=builder.GOSSIP_MODULE)
            self.assertEqual(first['sha256'], again['sha256'])
            self.assertFalse(again['import_inventory']['new_snapshot'])
            report = latest_successful_build(self.db, builder.GOSSIP_MODULE)
            self.assertEqual(report['categories']['gossip'], 2)
            gossip = next(r for r in report['rows'] if r['category'] == 'gossip' and r['source'] == 'classicua')
            self.assertEqual(gossip['route'], 'machine_1to1')
            self.assertEqual(gossip['unique_translation_texts'], 1)
            recorded = read_recorded_imports(self.db)['recorded_imports']
            self.assertEqual(recorded['categories']['gossip'], 2)
            self.assertEqual(recorded['gossip_counts']['reviewed_english_groups'], 1)
            self.assertEqual(report['gossip_counts']['distinct_npc_ids'], 2)
            self.assertEqual(manual.file.data, human_history)

    def test_ui_post_authentication_filter_and_refresh(self):
        from tools.translation_manager import ManagerUI
        service = GossipMachineImport(self.state, '/unused')
        manager = ManagerUI('/unused', '/unused', self.db)
        with patch('tools.gossip_coverage.read_pinned_corpus', return_value=[corpus()]):
            server = ThreadingHTTPServer(('127.0.0.1', 0), create_handler('token', 0))
            port = server.server_address[1]
            server.RequestHandlerClass = create_handler('token', port, manager)
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base = f'http://127.0.0.1:{port}'
            def import_worker(command, **options):
                self.assertIn(builder.GOSSIP_MODULE, command)
                try:
                    result = service.run()
                except ValueError as exc:
                    self.assertEqual(str(exc), 'pinned_source_changed')
                    return SimpleNamespace(returncode=1, stdout=b'{"error":"public_revision_mismatch"}')
                payload = {"build": "success", "module": builder.GOSSIP_MODULE,
                           "agent": {}, "summary": result, "skipped": [], "sha256": "fixture"}
                return SimpleNamespace(returncode=0, stdout=json.dumps(payload).encode())
            try:
                self.assertEqual(service.page(status='eligible')['total'], 1)
                request = Request(base + '/api/manager/reimport',
                    data=json.dumps({"module": builder.GOSSIP_MODULE, "confirm": True}).encode(),
                    headers={'Origin': base, 'Content-Type': 'application/json'})
                with patch.object(manager, '_promote_worker_result'), patch(
                        'tools.translation_manager.subprocess.run', side_effect=import_worker) as worker_call:
                    with self.assertRaises(HTTPError) as error:
                        urlopen(request)
                    self.assertEqual(error.exception.code, 403)
                    worker_call.assert_not_called()
                    request.add_header('X-Review-Token', 'token')
                    with urlopen(request) as response:
                        self.assertEqual(json.load(response)['summary']['machine_imported'], 1)
                    self.assertEqual(service.page(status='machine_1to1_provisional')['total'], 1)
                    self.state.revalidate_inputs = Mock(side_effect=ValueError('pinned_source_changed'))
                    with self.assertRaises(HTTPError) as error:
                        urlopen(request)
                    self.assertEqual(error.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(5)
