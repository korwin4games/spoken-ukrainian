"""Synthetic data only. No ClassicUA translation text or network dependency."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.classicua.grammar import inventory
from adapters.classicua.lua import SourceError, Table, parse_file, parse_value
from adapters.classicua.model import Dataset, Origin
from adapters.classicua.source import (FAMILIES, GitSource, LAYERS, PINNED_REVISION,
                                       audit_checkout, load_dataset, loading_order,
                                       metadata_report, report_json, safe_relative)


def wrapped(category, body, direct=False):
    header = 'local _, addonTable = ...\n'
    target = 'addonTable.' + category
    if direct:
        return header + target + ' = ' + body
    variable = 'synthetic_data'
    if category == 'gossip':
        footer = f'''if {target} then
for k, v in pairs({variable}) do
if type({target}[k]) == "table" and type(v) == "table" then
for vk, vv in pairs(v) do {target}[k][vk] = vv end
else {target}[k] = v end end
else {target} = {variable} end'''
    elif category == 'object':
        footer = f'for k, v in pairs({variable}) do {target}[k] = v end'
    else:
        footer = f'''if {target} then
for k, v in pairs({variable}) do {target}[k] = v end
else {target} = {variable} end'''
    return header + 'local ' + variable + ' = ' + body + '\n' + footer


class MemorySource:
    def __init__(self, files):
        self.files, self.hashes = files, {}

    def read(self, path):
        self.hashes[path] = hashlib.sha256(self.files[path].encode()).hexdigest()
        return self.files[path]


def source_fixture():
    files = {'ClassicUA_Camelot.toc': '## Interface: 16001\nentries/index.xml\n' +
             '\n'.join(f'entries/{layer}/index.xml' for layer in LAYERS),
             'entries/index.xml': '<Ui><Script file="zone.lua"/></Ui>',
             'entries/zone.lua': wrapped('zone', '{["Synthetic region"]="Вигаданий край"}', direct=True)}
    for layer in LAYERS:
        families = sorted(FAMILIES - {'zone'})
        files[f'entries/{layer}/index.xml'] = '<Ui xsi:schemaLocation="fixture">' + ''.join(
            '<Script file="' + family + '.lua"/>' for family in families) + '<!-- <Script file="never.lua"/> --></Ui>'
        for family in families:
            files[f'entries/{layer}/{family}.lua'] = wrapped(family, '{}', direct=family == 'object' and layer == 'classic')
    return files


class ParserTests(unittest.TestCase):
    def test_long_brackets_and_first_newline(self):
        node = parse_value('[==[\nInvented ]=] marker\r\nі ї ґ]==]')
        self.assertEqual(node.value, 'Invented ]=] marker\nі ї ґ')

    def test_comments_quoted_escapes_and_unicode(self):
        node = parse_value('-- [==[not a string\n--[=[ block } ]=]\n{"і", "line\\nnext\\t\\\"quote\\\"", "\\209\\150", "slash\\\\"}', 'fixture.lua')
        self.assertEqual(node.value.get(1).value, 'і')
        self.assertEqual(node.value.get(2).value, 'line\nnext\t"quote"')
        self.assertEqual(node.value.get(3).value, 'і')
        self.assertEqual(node.value.get(4).value, 'slash\\')
        self.assertEqual(node.line, 3)

    def test_sparse_slots_nil_named_and_mixed_entries(self):
        node = parse_value('{en="Synthetic", "Title", nil, "Objective", [8]="Eight", tasks={["Do an invented task"]="Task"}, ai=true}')
        table = node.value
        self.assertEqual([e.key.value for e in table.entries if e.positional], [1, 2, 3])
        self.assertIsNone(table.entries[2].value.value)
        self.assertNotIn(2, table.effective())
        self.assertEqual(table.get(3).value, 'Objective')
        self.assertEqual(table.get(8).value, 'Eight')
        self.assertIsInstance(table.get('tasks').value, Table)
        self.assertTrue(table.get('ai').value)

    def test_quoted_syntax_is_data_not_structure(self):
        node = parse_value('{"}", "[", "=", "nil"}')
        self.assertEqual([node.value.get(i).value for i in range(1, 5)], ['}', '[', '=', 'nil'])
        for source in ['{"}"', '{"["=1}', '{1 "}"']:
            with self.subTest(source=source), self.assertRaises(SourceError):
                parse_value(source)
        with self.assertRaises(SourceError):
            parse_file('"local" _, addonTable = ... addonTable.zone = {}', 'zone')

    def test_numeric_literals_and_separators(self):
        t = parse_value('{[0x10]=-2; fraction=.5, exponent=1e2, false, true, nil}').value
        self.assertEqual(t.get(16).value, -2)
        self.assertEqual(t.get('fraction').value, .5)
        self.assertEqual(t.get('exponent').value, 100)
        self.assertFalse(t.get(1).value)
        self.assertTrue(t.get(2).value)

    def test_source_locations_for_keys_and_values(self):
        row = parse_value('{\n [9] = {\n label = "invented"\n }\n}', 'synthetic.lua').value.entries[0]
        self.assertEqual((row.key.file, row.key.line, row.value.line), ('synthetic.lua', 2, 2))
        self.assertEqual(row.value.value.get('label').line, 3)

    def test_nil_deletes_duplicate_key_without_collapsing_slots(self):
        table = parse_value('{[9]="gone", [9]=nil, nil, "second"}').value
        self.assertNotIn(9, table.effective())
        self.assertEqual(table.get(2).value, 'second')

    def test_unsupported_expressions_fail_at_location(self):
        for source in ['{x=function() end}', '{x=os.execute("never")}', '{x=1+2}', '{[true]=1}', '{[nil]=2}', '{x="a" .. "b"}', '{x=identifier}', '{true=1}', '{end=2}', '{[1]=2, 3}']:
            with self.subTest(source=source), self.assertRaises(SourceError) as error:
                parse_value(source, 'unsupported.lua')
            self.assertIn('unsupported.lua:1:', str(error.exception))

    def test_invalid_strings_and_nesting_fail(self):
        for source in ['[==[unfinished', '"unfinished', '"bad\\q"', '"\\999"', '"raw\nnewline"', '"\\255"', '{' * 130]:
            with self.subTest(source=source), self.assertRaises(SourceError):
                parse_value(source)

    def test_file_wrapper_rejects_hidden_executable_code(self):
        for source in [wrapped('npc', '{}') + '\nos.execute("never")',
                       wrapped('npc', '{}').replace('pairs(synthetic_data)', 'pairs(run())'),
                       'local _, addonTable = ...\naddonTable.npc = run()']:
            with self.subTest(source=source), self.assertRaises(SourceError):
                parse_file(source, 'npc', 'fixture.lua')

    def test_direct_initializer_and_overlay_wrapper(self):
        for category, direct, expected in [('zone', True, 'initialize'), ('object', False, 'merge'), ('gossip', False, 'gossip')]:
            _, mode = parse_file(wrapped(category, '{}', direct), category)
            self.assertEqual(mode, expected)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.infos = {}

        def origin(node, key):
            return Origin('synthetic', 'synthetic-revision', node.file, node.line, node.column,
                          self.infos[node.file], hashlib.sha256(node.file.encode()).hexdigest(), key)

        self.dataset = Dataset(origin)
        self.serial = 0

    def apply(self, category, layer, body):
        self.serial += 1
        file = f'{layer}/{category}-{self.serial}.lua'
        self.infos[file] = layer
        self.dataset.apply(category, layer, parse_value(body, file), 'gossip' if category == 'gossip' else 'merge')
        return self.dataset.records[category]

    def test_whole_quest_row_replacement_and_nil(self):
        self.apply('quest_both', 'classic', '{[42]={"old title","old description","old objective","old progress","old completion"}}')
        rows = self.apply('quest_both', 'forever', '{[42]={"new title",nil,"new objective",ai=true}}')
        row = rows[42]
        self.assertEqual(row.fields[(1,)].node.value, 'new title')
        self.assertIn((2,), row.fields)
        self.assertIsNone(row.fields[(2,)].node.value)
        self.assertNotIn((4,), row.fields)
        self.assertEqual(row.missing_fields, ('description', 'progress', 'completion'))
        self.assertTrue(row.ai)
        self.assertEqual(row.predecessors[0].layer, 'classic')
        self.assertEqual(row.fields[(1,)].predecessors[0].layer, 'classic')
        self.assertEqual(row.origin.source_key, 42)
        self.assertEqual(row.identity, 'classicua:quest_both:42')

    def test_readables_empty_forever_preserves_classic_and_sod(self):
        for category in ['item_text', 'object_text']:
            self.apply(category, 'classic', '{[19]={"first", "second"}}')
            self.apply(category, 'sod', '{[20]={"season page"}}')
            rows = self.apply(category, 'forever', '{}')
            self.assertEqual(set(rows), {19, 20})
            self.assertEqual(rows[20].origin.layer, 'sod')
            self.assertEqual(rows[19].fields[(2,)].node.value, 'second')

    def test_readable_row_replaces_entire_chain(self):
        self.apply('item_text', 'classic', '{[12]={"first", "second"}}')
        rows = self.apply('item_text', 'sod', '{[12]={"replacement"}}')
        self.assertNotIn((2,), rows[12].fields)

    def test_gossip_hash_merge_common_and_code_replacement(self):
        self.apply('gossip', 'classic', '{[7]={[1]="one",[2]="two",["!code"]={old=1,keep=2}},["!common"]={[5]="common"}}')
        rows = self.apply('gossip', 'forever', '{[7]={[2]="new two",["!code"]={new=2}},["!common"]={[6]="extra"}}')
        self.assertEqual(rows[7].fields[(1,)].node.value, 'one')
        self.assertEqual(rows[7].fields[(1,)].origin.layer, 'classic')
        self.assertEqual(rows[7].fields[(2,)].node.value, 'new two')
        self.assertNotIn(('!code', 'old'), rows[7].fields)
        self.assertNotIn(('!code', 'keep'), rows[7].fields)
        self.assertIn(('!code', 'new'), rows[7].fields)
        self.assertEqual(set(rows['!common'].fields), {(5,), (6,)})

    def test_nil_overlay_hash_is_not_a_runtime_assignment(self):
        self.apply('gossip', 'classic', '{[7]={[2]="retained"}}')
        rows = self.apply('gossip', 'sod', '{[7]={[2]=nil}}')
        self.assertEqual(rows[7].fields[(2,)].node.value, 'retained')

    def test_namesakes_keep_page_order_and_h1(self):
        rows = self.apply('object_text', 'classic', '{["Synthetic plaque"]={{"alpha",h1=11},{"beta","gamma",h1=22}}}')
        row = rows['Synthetic plaque']
        self.assertEqual(row.fields[(1, 'h1')].node.value, 11)
        self.assertEqual(row.fields[(2, 2)].node.value, 'gamma')
        self.assertEqual(row.fields[(2, 'h1')].node.value, 22)

    def test_faction_precedence_and_shared_retention(self):
        self.apply('quest_both', 'classic', '{[1]={"shared"},[2]={"shared two"}}')
        self.apply('quest_alliance', 'forever', '{[1]={"alliance",ai=true}}')
        self.apply('quest_horde', 'classic', '{[1]={"horde"}}')
        views, conflicts = self.dataset.faction_views()
        self.assertEqual(views['alliance'][1].fields[(1,)].node.value, 'alliance')
        self.assertEqual(views['horde'][1].fields[(1,)].node.value, 'horde')
        self.assertEqual(self.dataset.records['quest_both'][1].fields[(1,)].node.value, 'shared')
        self.assertEqual(len(conflicts), 2)
        no_ai, _ = self.dataset.faction_views(False)
        self.assertEqual(no_ai['alliance'][1].fields[(1,)].node.value, 'shared')
        self.assertEqual(set(no_ai['horde']), {1, 2})

    def test_no_restoration_of_overwritten_human_row(self):
        self.apply('quest_alliance', 'classic', '{[1]={"older human"}}')
        self.apply('quest_alliance', 'forever', '{[1]={"new ai",ai=true}}')
        views, _ = self.dataset.faction_views(False)
        self.assertNotIn(1, views['alliance'])

    def test_unknown_fields_and_unexpanded_templates_retained(self):
        rows = self.apply('quest_both', 'classic', '''{[11]={"{ім'я:к} invented", invented_field="retained"}}''')
        row = rows[11]
        self.assertEqual(row.unsupported_fields, ('invented_field',))
        self.assertEqual(row.fields[(1,)].node.value, "{ім'я:к} invented")
        self.assertEqual(row.fields[(1,)].grammar[0].syntax, "{ім'я:к}")
        self.assertEqual(self.dataset.raw[0]['missing_positional_fields']['description'], 1)

    def test_duplicate_declarations_counted_separately(self):
        self.apply('zone', 'common', '{["Synthetic"]="first",["Synthetic"]="last"}')
        self.assertEqual(self.dataset.raw[0]['declarations'], 2)
        self.assertEqual(len(self.dataset.records['zone']), 1)
        self.assertEqual(self.dataset.records['zone']['Synthetic'].fields[()].node.value, 'last')
        self.assertEqual(self.dataset.warnings[0]['code'], 'duplicate_table_key')

    def test_report_is_deterministic_and_excludes_bodies_keys_templates(self):
        rows = self.apply('quest_both', 'classic', '{[6]={"PRIVATE-INVENTED-BODY",nil,tasks={["PRIVATE-TASK"]="PRIVATE-TEXT {unknown-secret}"}}}')
        report = metadata_report(self.dataset, {}, [])
        first = report_json(report)
        self.assertEqual(first, report_json(report))
        for secret in ['PRIVATE-INVENTED-BODY', 'PRIVATE-TASK', 'PRIVATE-TEXT', 'unknown-secret']:
            self.assertNotIn(secret, first)
        self.assertEqual(report['effective_categories']['quest_both']['missing_positional_fields']['description'], 1)
        self.assertEqual(report['grammar']['statuses']['unknown'], 1)
        self.assertEqual(len(report['grammar_review_findings']), 1)
        self.assertTrue(report['provenance'][0]['fields'])
        self.assertIn((2,), rows[6].fields)


class GrammarTests(unittest.TestCase):
    def test_actual_template_families_with_invented_gender_words(self):
        text = "{ім'я} {ІМ'Я:к} {клас:к} {Раса:р} {стать:вигадав:вигадала} {1}"
        result = inventory(text)
        self.assertEqual([x.category for x in result], ['player_name','player_name','player_class','player_race','player_gender','numeric_capture'])
        self.assertEqual(result[4].status, 'supported')
        self.assertEqual(result[5].status, 'problematic')
        self.assertEqual(result[0].syntax, "{ім'я}")
        self.assertIn(result[0].syntax, text)

    def test_unknown_case_arity_nested_and_unmatched(self):
        findings = inventory('{клас:мр} {new} {стать:one} {стать::two} {a{b}} } {')
        self.assertEqual(findings[0].status, 'unknown')
        self.assertTrue(any(f.category == 'nested' for f in findings))
        self.assertEqual(sum(f.category == 'malformed' for f in findings), 2)
        self.assertEqual(inventory('plain text'), [])


class SourceTests(unittest.TestCase):
    def test_real_manifest_structure_order_and_commented_scripts(self):
        source = MemorySource(source_fixture())
        dataset, order = load_dataset(source)
        self.assertEqual(order[0], 'entries/zone.lua')
        self.assertEqual(len(order), 25)
        self.assertFalse(any('never' in p for p in order))
        self.assertEqual(len(dataset.raw), 25)

    def test_overlay_order_is_not_alphabetical(self):
        files = source_fixture()
        files['entries/classic/quest_both.lua'] = wrapped('quest_both', '{[1]={"classic"}}')
        files['entries/sod/quest_both.lua'] = wrapped('quest_both', '{[1]={"season"}}')
        files['entries/forever/quest_both.lua'] = wrapped('quest_both', '{[1]={"forever"}}')
        dataset, _ = load_dataset(MemorySource(files))
        self.assertEqual(dataset.records['quest_both'][1].fields[(1,)].node.value, 'forever')
        self.assertEqual([o.layer for o in dataset.records['quest_both'][1].predecessors], ['classic','sod'])

    def test_wrong_order_and_missing_families_rejected(self):
        files = source_fixture()
        files['ClassicUA_Camelot.toc'] = files['ClassicUA_Camelot.toc'].replace('entries/classic/index.xml', 'entries/forever/index.xml', 1)
        with self.assertRaises(SourceError):
            load_dataset(MemorySource(files))
        files = source_fixture()
        files['entries/sod/index.xml'] = '<Ui/>'
        with self.assertRaises(SourceError):
            load_dataset(MemorySource(files))

    def test_cyclic_and_hostile_xml_rejected(self):
        for xml in ['<Ui><Include file="index.xml"/></Ui>', '<!DOCTYPE Ui [<!ENTITY bad "x">]><Ui/>', '<Ui><Script file="../../../escape.lua"/></Ui>', '<Ui><Script/></Ui>']:
            files = source_fixture()
            files['entries/index.xml'] = xml
            with self.subTest(xml=xml), self.assertRaises(SourceError):
                loading_order(MemorySource(files))

    def test_invalid_record_shapes_rejected(self):
        for body in ['{["not-a-quest-id"]={"title"}}', '{[1]="not a row"}']:
            files = source_fixture()
            files['entries/classic/quest_both.lua'] = wrapped('quest_both', body)
            with self.subTest(body=body), self.assertRaisesRegex(SourceError, 'record'):
                load_dataset(MemorySource(files))

    def test_unsafe_paths_rejected(self):
        for path in ['../outside', '/outside', 'https://host/file', 'C:\\outside']:
            with self.subTest(path=path), self.assertRaises(SourceError):
                safe_relative(path)

    def test_revision_mismatch_before_data_read(self):
        with tempfile.TemporaryDirectory() as temp:
            subprocess.run(['git','init','-q',temp], check=True)
            subprocess.run(['git','-C',temp,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-qm','Synthetic root'],check=True)
            with patch.object(GitSource,'read',side_effect=AssertionError('Must not read data')):
                with self.assertRaisesRegex(SourceError, 'HEAD does not match'):
                    GitSource(temp)

    def test_dirty_checkout_and_subdirectory_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            subprocess.run(['git','init','-q',temp], check=True)
            (path/'fixture').write_text('invented source')
            subprocess.run(['git','-C',temp,'add','fixture'], check=True)
            subprocess.run(['git','-C',temp,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Synthetic source'], check=True)
            revision = subprocess.check_output(['git','-C',temp,'rev-parse','HEAD']).decode().strip()
            with patch('adapters.classicua.source.PINNED_REVISION', revision):
                reader = GitSource(path)
                self.assertEqual(reader.read('fixture'), 'invented source')
                (path/'nested').mkdir()
                with self.assertRaisesRegex(SourceError, 'checkout root'):
                    GitSource(path/'nested')
                (path/'fixture').write_text('changed source')
                with self.assertRaisesRegex(SourceError, 'modified'):
                    GitSource(path)

    def test_hash_mismatch_rejected(self):
        files = source_fixture()
        for path in ['scripts/entries.lua','scripts/utils.lua','entries/class.lua','entries/race.lua']:
            files[path] = '-- synthetic metadata-only fixture'
        with patch('adapters.classicua.source.GitSource',return_value=MemorySource(files)):
            with self.assertRaisesRegex(SourceError, 'hashes'):
                audit_checkout('not-used', {})

    def test_cli_rejects_output_outside_ignored_build(self):
        result = subprocess.run([sys.executable, str(ROOT/'tools/classicua_audit.py'), '--source', '/does/not/exist', '--output', '/tmp/should-not-write-classicua-report.json'], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'ignored build/', result.stderr)

    def test_cli_cannot_write_inside_source_checkout(self):
        build = ROOT/'build'
        build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build) as temp:
            output = Path(temp)/'source-must-not-change.json'
            result = subprocess.run([sys.executable, str(ROOT/'tools/classicua_audit.py'), '--source', temp, '--output',str(output)],capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(output.exists())

    def test_cli_failure_report_has_no_source_text(self):
        build = ROOT/'build'
        build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build) as temp:
            output = Path(temp)/'failure.json'
            result = subprocess.run([sys.executable, str(ROOT/'tools/classicua_audit.py'), '--source', '/does/not/exist', '--output',str(output)],capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(output.read_text())['errors'][0]['file'], '<checkout>')


if __name__ == '__main__':
    unittest.main()
