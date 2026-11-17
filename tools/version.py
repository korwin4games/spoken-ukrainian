"""Manage the project SemVer core independently of addon and upstream versions."""
import argparse
from datetime import date
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]
CORE = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"


def parse(value):
    """The project uses strict numeric MAJOR.MINOR.PATCH, without suffixes."""
    if not re.fullmatch(CORE, value, flags=re.ASCII):
        raise ValueError("Expected MAJOR.MINOR.PATCH with no leading zeros, suffixes or whitespace")
    return tuple(int(part) for part in value.split('.'))


def read_version(root=ROOT):
    data = (Path(root) / 'VERSION').read_bytes()
    try:
        text = data.decode('ascii')
    except UnicodeDecodeError:
        raise ValueError('VERSION must contain ASCII digits and dots') from None
    value = text[:-1] if text.endswith('\n') else text
    parse(value)
    return value


def proposed(current, kind, approve_stable=False):
    major, minor, patch = parse(current)
    if kind == 'patch':
        result = major, minor, patch + 1
    elif kind == 'minor':
        result = major, minor + 1, 0
    elif kind == 'major':
        if major == 0 and not approve_stable:
            raise ValueError('Pre-1.0 major bump requires explicit stable-release approval; use minor for development breaking changes, or --approve-stable after approval')
        result = major + 1, 0, 0
    else:
        raise ValueError('Bump type must be patch, minor or major')
    if result <= (major, minor, patch):
        raise ValueError('Version downgrades and unchanged versions are forbidden')
    return '.'.join(map(str, result))


def bump(root, kind, dry_run=False, approve_stable=False):
    root = Path(root)
    path = root / 'VERSION'
    if path.is_symlink():
        raise ValueError('VERSION must be a regular project file, not a symlink')
    current = read_version(root)
    next_version = proposed(current, kind, approve_stable)
    if not dry_run:
        original = path.read_bytes()
        # Preserve the existing final-newline convention; reject malformed whitespace on read.
        path.write_bytes((next_version + ('\n' if original.endswith(b'\n') else '')).encode('ascii'))
    return next_version


def check(root=ROOT, tag=None):
    root = Path(root)
    current = read_version(root)
    text = (root / 'CHANGELOG.md').read_text(encoding='utf-8')
    headings = [line for line in text.splitlines() if line.startswith('## ')]
    if not headings or headings[0] != '## [Unreleased]':
        raise ValueError('CHANGELOG.md must start its sections with ## [Unreleased]')
    versions = []
    for heading in headings[1:]:
        match = re.fullmatch(r'## \[([^\]]+)\] - ([0-9]{4}-[0-9]{2}-[0-9]{2})', heading)
        if not match:
            raise ValueError('Malformed or duplicate Unreleased changelog heading')
        value, day = match.groups()
        parsed = parse(value)
        date.fromisoformat(day)
        if versions and parsed >= versions[-1]:
            raise ValueError('Changelog versions must be unique and descending')
        versions.append(parsed)
    if not versions or versions[0] != parse(current):
        raise ValueError('Newest dated changelog section must match VERSION; prepare the new section without rewriting historical entries')
    if tag is not None and tag != 'v' + current:
        raise ValueError('Version tag must equal v' + current)
    # VERSION remains canonical. uv's PEP 621 metadata and lockfile are
    # secondary mirrors, both checked on every project version validation.
    pyproject = root / 'pyproject.toml'
    if pyproject.exists():
        info = tomllib.loads(pyproject.read_text(encoding='utf-8'))
        if info.get('project', {}).get('version') != current:
            raise ValueError('pyproject.toml project.version must match VERSION')
        lockfile = root / 'uv.lock'
        if not lockfile.is_file():
            raise ValueError('uv.lock missing for uv-managed project')
        lock = tomllib.loads(lockfile.read_text(encoding='utf-8'))
        project_name = info['project']['name']
        projects = [pkg for pkg in lock.get('package', [])
                    if pkg.get('name') == project_name
                    and pkg.get('source') == {'virtual': '.'}]
        if len(projects) != 1 or projects[0].get('version') != current:
            raise ValueError('uv.lock project version must match VERSION')
    return current


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('show')
    validation = commands.add_parser('check')
    validation.add_argument('--tag', help='Exact project version tag, such as vMAJOR.MINOR.PATCH')
    update = commands.add_parser('bump')
    update.add_argument('kind', choices=('patch', 'minor', 'major'))
    update.add_argument('--dry-run', action='store_true')
    update.add_argument('--approve-stable', action='store_true', help='Explicitly confirm prior approval for the first stable major version')
    args = parser.parse_args(argv)
    try:
        if args.command == 'show':
            value = read_version(root)
        elif args.command == 'check':
            value = check(root, args.tag)
        else:
            if args.approve_stable and args.kind != 'major':
                raise ValueError('--approve-stable is only valid for a major bump')
            value = bump(root, args.kind, args.dry_run, args.approve_stable)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Version error: {error}\n')
    print(value)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
