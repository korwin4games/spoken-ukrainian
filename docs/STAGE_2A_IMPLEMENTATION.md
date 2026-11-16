# Stage 2A implementation

Implemented locally on `feat/classicua-source-adapter`, 2026-11-16. This stage prepares and audits ClassicUA data in memory. It does not map to Spoken IDs, create translated packs, generate audio, or establish redistribution permission. The initial implementation did not include publication; the subsequent review task authorizes publishing and merging the code.

## Files and entry points

```text
adapters/
  __init__.py
  classicua/
    __init__.py
    lua.py                 restricted lexer/parser and located table nodes
    grammar.py             non-expanding template classifier
    model.py               normalized records, provenance and merge engine
    source.py              pinned Git reads, TOC/XML order and metadata reports
tools/classicua_audit.py    local audit CLI
tests/test_classicua.py     synthetic parser/adapter/source tests
sources.lock.json          adds ClassicUA pin and 36 file hashes
build/classicua-audit.json  ignored metadata-only local audit
```

`README.md` documents the new commands. Stage 0 documents, Stage 1 code/tests, and the diagnostic addon are preserved. The existing CI test-discovery command already includes the new synthetic tests; the workflow needs no change and does not acquire ClassicUA or upload audit artifacts.

## Source acquisition and validation

The adapter accepts an explicit local checkout root. Its only production pin is ClassicUA `1770d208ad853d23d61105cf510d53804770d916`, version 7.1.1, from `https://github.com/greenya/ClassicUA`. It validates HEAD and checkout root before reading source data, rejects tracked worktree/index modifications, then reads the immutable Git blobs with `git show <pin>:<path>`. Untracked files are not inputs. Git operations use `--no-optional-locks`; the adapter never writes to the source checkout or fetches revisions.

`sources.lock.json` records SHA-256 for the 25 supported data files, the Camelot TOC, six traversed XML files, the entries runtime resolver and utility implementation, and the common class/race grammar inputs. The audit compares the complete relevant hash set with the lock. It does not silently update the lock, accept another revision, or use a moving branch. Common class/race files and runtime Lua are inspected and hashed as semantic evidence; they are not executed by the adapter.

A separate checkout can be acquired manually, outside this repository, then detached at the pin. The checkout used during implementation is `/tmp/spoken-uk-classicua-pinned`; it is temporary and is not a project dependency or committed input. The project contains no source translation snapshot.

## Parser design and supported syntax

`lua.py` uses a character lexer and recursive descent for nested literals. Regular expressions recognize only flat number/identifier tokens, not Lua structures. The parser supports:

- Numeric and string keys, named fields and implicit positional fields in the same table.
- Nested tables, sparse numeric indexes and explicit nil slots. Implicit positions advance even when the value is nil; named fields do not advance them.
- Quoted strings, standard Lua escapes, decimal byte escapes, escaped newlines, Unicode and UTF-8 validation.
- Long-bracket strings/comments with arbitrary matching `=` delimiters, line comments, first-newline omission and source newline normalization.
- Decimal, hexadecimal integer and exponent literals, unary minus, booleans, commas/semicolons and trailing separators.
- Source file, line and column on keys and values. File hashes cover the original bytes before normalization.

Numbers outside the exact finite range ±2^53 are rejected. Table nesting is limited to 128. Non-UTF-8 byte strings are rejected rather than silently changed. No arithmetic, concatenation, function calls, identifier-valued expressions or general Lua statements are supported. Collisions between explicit keyed fields and implicit positional fields are rejected because Lua does not specify assignment order in such constructors. Duplicate explicit keys retain raw declarations and produce a metadata warning; effective table values follow the final declaration, including nil deletion.

The file parser recognizes the exact token shapes of the pinned header and initialization/merge wrappers. Whitespace and comments can vary. The wrappers are validated as syntax, not interpreted: unexpected trailing code, altered loops or function calls fail with `file:line` diagnostics. Diagnostics do not include source string bodies. No `eval`, Lua interpreter, external parser or third-party Python package is used by the adapter.

## Manifest and override semantics

The adapter walks Camelot's TOC and nested XML in declaration order, excluding commented elements. XML is read with the standard-library Expat parser, without namespace expansion because the source uses WoW's unbound `xsi` prefix. DTDs/entities, cycles, missing script paths and paths escaping the source root are rejected. UI XML is traversed for file references without executing scripts or frame definitions. Unsupported source families remain outside normalization, even when their filenames are recorded in the complete Lua load order.

All 25 required family files must be present. Observed content layers must be Classic, SoD, Forever in that order. Common zone terminology precedes them. No directory sorting determines override precedence.

| Family | Effective behavior |
| --- | --- |
| Quest Alliance/Horde/shared, NPC and item text | Each later top-level key replaces the entire previous row. Missing fields do not inherit. |
| Object text | Later object-name entry replaces the entire page/variant entry. Namesakes and `h1` remain nested data. |
| Object terminology | Classic initializes the dictionary; SoD/Forever assign their keys. |
| Zone terminology | Common name-keyed dictionary initialized from `entries/zone.lua`. |
| Gossip | NPC and `!common` table entries merge one level deeper. Each supplied hash or `!code` value replaces its predecessor. `!code` is not recursively merged. |

Lua `pairs` sees a completed table; nil constructor fields are absent and therefore do not delete a previously loaded row/hash during an overlay loop. Empty Forever readable tables perform no assignments and preserve all inherited data. Declaration counts include literals that later constructor assignments replace; effective counts do not.

Alliance and Horde runtime views are resolved independently from the retained source dictionaries. A faction row beats a shared row with the same quest ID. Conflicts remain visible; filename membership is not a guess at actual game eligibility. The model also exposes views with AI disabled: ClassicUA removes AI rows before faction/shared lookup, so a surviving shared row can then answer. It never restores an older Classic row overwritten by an AI-marked Forever row.

## Normalized in-memory records

`audit_checkout(path, expected_hashes)` returns a `Dataset` and metadata report. `Dataset.records[category][source_key]` contains `Record` objects:

- `category`, original `key`, and `identity` in a `classicua:` namespace, not a Spoken identifier.
- Located original `node`, preserving nested table entries, namesake metadata, keys and explicit nil declarations.
- `origin`: source repository, commit, file/line/column, layer, source file SHA-256 and original source key.
- `predecessors`: provenance references for replaced rows, without inheriting their missing fields.
- `fields`: paths of original numeric/string keys to located scalar nodes, source origin, overwritten field origins and grammar findings. Retained Gossip fields retain their original source location.
- `ai`, `missing_fields`, and `unsupported_fields` for schema review. The five quest slots remain title, description, objective, progress, completion; task labels and `en` remain metadata.

Table declaration nodes preserve nil even though effective Lua lookup omits it. Missing slot, explicit nil and empty string are distinguishable in memory; the missing-field coverage summary groups all three as unavailable text. Unsupported row fields remain in memory and are flagged rather than discarded. Unexpected top-level record types are errors.

No API serializes translated records to a pack or bulk text file. Downstream mapping must consume records in memory and remain subject to the permission boundary.

## Grammar inventory

The classifier retains the original syntax in memory and performs no substitution. It recognizes name/class/race templates, seven grammatical cases, capitalization variants and two-branch player-sex templates. "Supported" means understood by the classifier, not supported by Spoken or rendered for a character.

Positive numeric captures are flagged as problematic because they require original-text context. Unknown names/cases/arity, nested braces, unmatched braces and malformed gender branches are reported for review. The real corpus contains three class-case forms absent from ClassicUA's common case tables. No character name, class, race or gender is substituted, and no template is converted to Spoken syntax.

## Metadata-only output

The JSON report includes revision/file hashes, actual Lua load order, raw declarations by category/layer, effective counts, origin-layer counts, replacement events, missing quest slots, AI flags, field/schema findings, Gossip hash/code counts, namesake counts, faction conflicts, grammar totals and warnings/errors.

`provenance` carries record/field locations, file hashes, predecessor locations and scalar text hashes. Numeric source keys remain numeric; string source keys and field names become SHA-256 references so object names, task strings and source metadata do not reproduce source text. Grammar reports retain category/shape/count and hashed syntax/location for review; literal gender branches and unknown template bodies are not emitted. An in-memory caller can inspect the preserved original syntax against its separately obtained source.

Reports contain no translated bodies, timestamps or local checkout paths. JSON ordering is stable. The CLI only writes inside ignored `build/`, and refuses output inside the source checkout even if that checkout happens to live under `build/`. A failed audit writes location/message metadata and exits nonzero. Syntax failures are separated from revision/hash/manifest errors.

The detailed local report is about 52 MB because every effective field has provenance. It is ignored and not a CI artifact. No result is described as Spoken translation coverage.

## Usage and remaining scope

```sh
python3 tools/classicua_audit.py --source /absolute/path/to/ClassicUA
python3 tools/classicua_audit.py --source /absolute/path/to/ClassicUA --output build/review/audit.json
python3 tools/build.py
python3 -m unittest discover -s tests -v
```

Tests do not require ClassicUA to exist. The optional audit requires a clean checkout at the exact pin. See [STAGE_2A_TESTING.md](STAGE_2A_TESTING.md) for effective inventory and results.

Stage 2B must resolve source redistribution/TTS permissions and verify the remaining runtime text-display contracts. Stage 3 needs canonical quest/Gossip/readable/map/encounter crosswalks and reviewed grammar decisions. NPC/object/zone terms are not unique Spoken identities; item IDs are not page IDs; Gossip hashes are not Spoken moment IDs. None of those mappings is attempted here.
