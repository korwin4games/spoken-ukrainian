"""Version mutations use temporary project roots, never the real VERSION file."""
from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('project_version', ROOT/'tools/version.py')
version = importlib.util.module_from_spec(spec)
spec.loader.exec_module(version)


def changelog(current='0.0.1'):
    return '# Changelog\n\n## [Unreleased]\n\n### Added\n\n## [' + current + '] - 2026-11-16\n\n### Added\n\n- Invented baseline.\n'


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'VERSION').write_bytes(b'0.0.1\n')
        (self.root/'CHANGELOG.md').write_text(changelog())
        (self.root/'unrelated').write_bytes(b'preserve me')

    def call(self, args):
        output = io.StringIO()
        with redirect_stdout(output):
            version.main(args, self.root)
        return output.getvalue()

    def test_read_and_show(self):
        self.assertEqual(version.read_version(self.root), '0.0.1')
        self.assertEqual(self.call(['show']), '0.0.1\n')

    def test_core_parsing(self):
        for text, expected in [('0.0.0',(0,0,0)), ('0.0.1',(0,0,1)), ('1.22.333',(1,22,333))]:
            self.assertEqual(version.parse(text), expected)

    def test_invalid_version_syntax(self):
        for text in ['', '1', '1.2', '1.2.3.4', '-1.0.0', '01.0.0', '1.01.0', '1.0.01', 'v1.0.0', '1.0.0-alpha', '1.0.0+build', ' 1.0.0', '1.0.0 ', '1.0.0\n', '１.0.0']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                version.parse(text)

    def test_invalid_file_whitespace(self):
        for data in [b'0.0.1\n\n', b'0.0.1\r\n', b' 0.0.1\n', b'0.0.1 \n', b'0.0.1\t', b'\xef\xbb\xbf0.0.1\n']:
            (self.root/'VERSION').write_bytes(data)
            with self.subTest(data=data), self.assertRaises(ValueError):
                version.read_version(self.root)

    def test_patch_examples(self):
        for current, expected in [('0.0.1','0.0.2'),('0.1.0','0.1.1'),('1.0.0','1.0.1')]:
            self.assertEqual(version.proposed(current,'patch'), expected)

    def test_minor_resets_patch(self):
        for current, expected in [('0.0.2','0.1.0'),('0.1.2','0.2.0'),('1.2.3','1.3.0')]:
            self.assertEqual(version.proposed(current,'minor'), expected)

    def test_major_resets_lower_components(self):
        self.assertEqual(version.proposed('1.2.3','major'), '2.0.0')

    def test_pre_stable_requires_approval_even_dry_run(self):
        with self.assertRaisesRegex(ValueError, 'stable-release approval'):
            version.bump(self.root,'major',dry_run=True)
        self.assertEqual(version.proposed('0.9.7','major',approve_stable=True),'1.0.0')
        self.assertEqual((self.root/'VERSION').read_bytes(),b'0.0.1\n')

    def test_pre_stable_breaking_changes_can_use_minor(self):
        self.assertEqual(version.proposed('0.0.1','minor'),'0.1.0')

    def test_dry_run_changes_nothing(self):
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        self.assertEqual(self.call(['bump','patch','--dry-run']), '0.0.2\n')
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_bump_only_writes_version_preserving_format(self):
        for data in [b'0.0.1\n', b'0.0.1']:
            (self.root/'VERSION').write_bytes(data)
            previous = (self.root/'CHANGELOG.md').read_bytes()
            self.assertEqual(self.call(['bump','patch']), '0.0.2\n')
            self.assertEqual((self.root/'VERSION').read_bytes(),data.replace(b'0.0.1',b'0.0.2'))
            self.assertEqual((self.root/'CHANGELOG.md').read_bytes(),previous)
            self.assertEqual((self.root/'unrelated').read_bytes(),b'preserve me')

    def test_invalid_bump(self):
        with self.assertRaises(ValueError):
            version.proposed('0.0.1','downgrade')
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            version.main(['bump','invalid'], self.root)
        self.assertEqual(result.exception.code, 2)

    def test_all_bumps_increase_version(self):
        for kind in ['patch','minor','major']:
            self.assertGreater(version.parse(version.proposed('1.2.3',kind)),(1,2,3))

    def test_no_git_or_network_operations(self):
        with patch('subprocess.run',side_effect=AssertionError('Unexpected Git operation')), patch('subprocess.Popen',side_effect=AssertionError('Unexpected subprocess')):
            self.call(['bump','patch'])
        self.assertFalse((self.root/'.git').exists())

    def test_check_and_matching_tag(self):
        self.assertEqual(self.call(['check']), '0.0.1\n')
        self.assertEqual(self.call(['check','--tag','v0.0.1']), '0.0.1\n')

    def test_tag_mismatch(self):
        for tag in ['v0.0.2','0.0.1','v0.0.1-extra']:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                version.check(self.root, tag)

    def test_missing_version(self):
        (self.root/'VERSION').unlink()
        with self.assertRaises(OSError):
            version.check(self.root)

    def test_changelog_mismatch_duplicates_order_date(self):
        for content in [changelog('0.0.2'), changelog().replace('## [Unreleased]','## Unreleased'), changelog()+'\n## [0.0.1] - 2026-11-16\n', changelog()+'\n## [0.1.0] - 2026-11-16\n', changelog().replace('2026-11-16','2026-02-30')]:
            (self.root/'CHANGELOG.md').write_text(content)
            with self.subTest(content=content), self.assertRaises(ValueError):
                version.check(self.root)

    def test_bump_requires_manual_changelog_preparation(self):
        version.bump(self.root,'patch')
        with self.assertRaisesRegex(ValueError, 'Newest dated'):
            version.check(self.root)
        old = (self.root/'CHANGELOG.md').read_text()
        (self.root/'CHANGELOG.md').write_text(old.replace('## [0.0.1]', '## [0.0.2] - 2026-11-17\n\n### Fixed\n\n- Invented fix.\n\n## [0.0.1]',1))
        self.assertEqual(version.check(self.root),'0.0.2')

    def test_symlink_update_rejected(self):
        target=self.root/'target'
        target.write_bytes(b'0.0.1\n')
        (self.root/'VERSION').unlink()
        (self.root/'VERSION').symlink_to(target)
        with self.assertRaisesRegex(ValueError,'symlink'):
            version.bump(self.root,'patch')
        self.assertEqual(target.read_bytes(),b'0.0.1\n')

    def test_real_project_metadata_is_consistent_read_only(self):
        self.assertEqual(version.check(ROOT),version.read_version(ROOT))
