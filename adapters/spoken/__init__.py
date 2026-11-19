"""Read-only public canonical inventory. No dialogue bodies leave this module."""
from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

from adapters.classicua.lua import Table, parse_value
from adapters.classicua.source import safe_relative
from adapters.crosswalk import VerifiedTarget, digest

ROOT = Path(__file__).resolve().parents[2]


class PublicSource:
    def __init__(self, path, manifest):
        self.path = Path(path).resolve()
        self.revision = manifest['revision']
        self.expected = manifest['files']
        self.hashes = {}
        if not re.fullmatch(r'[a-f0-9]{40}', self.revision):
            raise ValueError('invalid_public_revision')
        if self.git('rev-parse', 'HEAD').decode().strip() != self.revision:
            raise ValueError('public_revision_mismatch')
        if Path(self.git('rev-parse', '--show-toplevel').decode().strip()).resolve() != self.path:
            raise ValueError('public_checkout_root_required')
        if self.git('status', '--porcelain', '--untracked-files=no').strip():
            raise ValueError('public_checkout_modified')

    def git(self, *args):
        p = subprocess.run(['git', '--no-optional-locks', '-C', str(self.path), *args],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode:
            raise ValueError('public_git_read_failed')
        return p.stdout

    def read(self, path):
        path = safe_relative(path)
        if path not in self.expected:
            raise ValueError('public_blob_not_pinned')
        blob = self.git('show', self.revision + ':' + path)
        sha = hashlib.sha256(blob).hexdigest()
        if sha != self.expected[path]:
            raise ValueError('public_blob_digest_mismatch')
        self.hashes[path] = sha
        return blob


def literal_data(blob, global_name):
    """Only a single literal assignment is accepted; no upstream Lua executes."""
    text = blob.decode('utf-8-sig')
    # Leading comments are stripped by the existing lexer, not a Lua regex parser.
    # parse_value handles all nested tables and rejects trailing executable code.
    start = text.find(global_name + ' = ')
    if start < 0:
        raise ValueError('public_literal_assignment_missing')
    prefix = text[:start]
    if any(line.strip() and not line.lstrip().startswith('--') for line in prefix.splitlines()):
        raise ValueError('public_literal_prefix_unsupported')
    node = parse_value(text[start + len(global_name + ' = '):], '<public>')

    def convert(n):
        if isinstance(n.value, Table):
            return {k: convert(e.value) for k, e in n.value.effective().items()}
        return n.value
    return convert(node)


def stored_checksum(text):
    """Checksum of already normalized public storage bytes (not raw client HTML)."""
    data = text.encode('utf-8')
    result = len(data) % 2147483647
    for byte in data:
        result = (result * 31 + byte) % 2147483647
    return result


@dataclass(frozen=True)
class Inventory:
    targets: dict
    contexts: dict
    aliases: dict
    revision: str
    files: dict


def build_index(reader, *, corpus=None):
    targets, contexts = {}, {}

    def add(identity, family, path, context):
        target = VerifiedTarget(identity, family, reader.revision, path, reader.hashes[path])
        targets[identity] = target
        contexts.setdefault(identity, []).append(context)

    corpus_path = 'pipelines/quests/corpus/corpus.json.gz'
    if corpus is None:
        corpus = json.loads(gzip.decompress(reader.read(corpus_path)))
    factions = json.loads(reader.read('pipelines/quests/corpus/factions.json'))['sides']
    for row in corpus['lines']:
        if row['source'] not in ('accept', 'progress', 'complete', 'gossip'):
            continue
        family = 'gossip' if row['source'] == 'gossip' else 'quest'
        add(row['lineId'], family, corpus_path, {
            'npc_id': row['npcId'], 'npc_type': row['npcType'], 'voice': row['voice'],
            'faction': factions.get(str(row['questId']), 'unknown'),
            'player_gender': row['playerGender'], 'generatable': row['generatable'],
            'wording_sha256': digest(row['originalText']),
            'source': row['source'], 'quest_id': row['questId']})
    alias_path = 'pipelines/quests/corpus/gossip_aliases.json'
    aliases = json.loads(reader.read(alias_path))
    # Keep only links whose endpoints are actually exposed by this inventory.
    aliases = {'g:' + k: sorted('g:' + v for v in values if 'g:' + v in targets)
               for k, values in aliases.items() if 'g:' + k in targets}
    path = 'addons/Spoken_Readables/Data/Books.lua'
    data = literal_data(reader.read(path), 'SpokenReadablesData')
    for page, row in data['pages'].items():
        book = data['books'].get(row['book'])
        chain = list(book['pages'].values()) if book else []
        owners = sorted([kind, owner] for kind, entries in data['owners'].items()
                        for owner, book_id in entries.items() if book_id == row['book'])
        add(f'b:{page}', 'readable', path, {'book': row['book'], 'number': row['number'],
            'chain': chain, 'owners': owners, 'checksum': stored_checksum(row['text']),
            'wording_sha256': digest(row['text'])})
    path = 'pipelines/places/tools/seed/zones.json'
    zones = json.loads(reader.read(path))
    for key in zones:
        if key.isdecimal() and int(key) > 0:
            add('z:' + key, 'places', path, {'map_id': int(key), 'kind': 'zone_reference'})
    path = 'addons/Spoken_Places/Data/enUS/Subzones.lua'
    text = reader.read(path).decode('utf-8-sig')
    guard = 'if not SpokenPlaces:ShouldLoadLanguage("enUS") then\n\treturn\nend'
    tail = 'SpokenPlaces:RegisterLoreData("enUS", "subzones", subzones)'
    if text.count(guard) != 1 or not text.rstrip().endswith(tail):
        raise ValueError('public_subzone_wrapper_changed')
    text = text.replace(guard, '', 1).replace('local _, SpokenPlaces = ...', '', 1).rstrip()[:-len(tail)].rstrip()
    subzones = literal_data(text.encode(), 'local subzones')
    for map_id, rows in subzones.items():
        for key in rows:
            add(f's:{map_id}:{key}', 'places', path,
                {'map_id': map_id, 'kind': 'subzone_reference'})
    path = 'addons/Spoken_Bosses/Data/Bosses.lua'
    bosses = literal_data(reader.read(path), 'SpokenBosses')
    for map_id, rows in bosses['maps'].items():
        for row in rows.values():
            add(f'boss:{map_id}:{row["key"]}', 'bosses', path,
                {'map_id': map_id, 'creatures': sorted(row['ids'].values())})
    # Validate helper references too, even when they are used only by parity tests.
    for path in sorted(reader.expected):
        if path not in reader.hashes:
            reader.read(path)
    return Inventory(dict(sorted(targets.items())),
                     {k: sorted(v, key=digest) for k, v in sorted(contexts.items())},
                     dict(sorted(aliases.items())), reader.revision, dict(sorted(reader.hashes.items())))
