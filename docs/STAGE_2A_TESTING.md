# Stage 2A testing

Date: 2026-11-16. The initial implementation was prepared locally on `feat/classicua-source-adapter`. Publication and merge are covered by the subsequent review task.

## Automated verification

```sh
python3 tools/build.py
python3 -m unittest discover -s tests -v
```

Result: **52 tests passed**, comprising 36 synthetic Stage 2A tests and all 16 unchanged Stage 1 regression tests. No ClassicUA checkout, translation fixture, network, database or TTS provider is required by the standard suite. Stage 1 still needs its existing pinned Spoken checkout and system Lua library.

Coverage includes long brackets and comments, escapes and UTF-8, nested/mixed/sparse tables and explicit nil, key/value source locations, whole-row replacement, empty Forever readables, SoD inheritance, Gossip per-hash/common merges and whole `!code` replacement, namesakes/`h1`, faction precedence, AI filtering, original templates, unknown fields, duplicate declarations, deterministic metadata and text redaction, unsupported executable syntax, revision/root/dirty-worktree checks, source hash mismatch, XML order/comments/cycles/entities/path traversal, and output restrictions.

The parser tests use invented text and the small grammar tokens named in the task. Synthetic data wrappers are never executed by the adapter. Stage 1's existing Lua harness remains unchanged. The restricted parser has not been proven equivalent to every Lua program; it deliberately rejects everything outside its supported data/wrapper subset.

The diagnostic build still produces the same two-file, 1651-byte ZIP:

```text
SHA-256: 5a2519858229c9aa004dbef075d1c8c51561e33f09828112504e0558005c8a8e
```

No diagnostic addon files or existing test files were modified. The Stage 0 document hashes remain unchanged.

## Optional real-source audit

The separate temporary checkout used for this task is `/tmp/spoken-uk-classicua-pinned`. It was acquired from the public repository and detached at `1770d208ad853d23d61105cf510d53804770d916`. Acquisition was separate from the adapter; the adapter never fetches or checks out source itself.

```sh
python3 tools/classicua_audit.py --source /tmp/spoken-uk-classicua-pinned
```

Result: all 25 selected data files parsed successfully in actual manifest order. The report validates 36 relevant file hashes. There are no unsupported Lua constructs, unsupported row fields, invalid field types or source errors at this pin. Three explicit warnings explain unresolved permissions, inherited SoD review and unrendered player grammar.

Two runs produced byte-identical `build/classicua-audit.json` reports. The complete report remains ignored and local; it includes metadata and hashes only, with no translation bodies. The source checkout remained clean after auditing. No source data was written into tracked project files.

## Source inventory

Counts below refer to ClassicUA source records, not canonical Spoken lines or in-game coverage. "Replacements" counts assignments to an existing category root key; for Gossip that means a merged NPC/common record, not a count of overwritten greetings.

| Category | Common | Classic declarations | SoD declarations | Forever declarations | Effective unique records | Replacements |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Quest Alliance | 0 | 937 | 205 | 557 | 1663 | 36 |
| Quest Horde | 0 | 976 | 162 | 455 | 1568 | 25 |
| Quest shared | 0 | 2362 | 569 | 616 | 3524 | 23 |
| Gossip NPC/common groups | 0 | 10 | 7 | 2 | 16 | 3 |
| Item text | 0 | 262 | 27 | 0 | 289 | 0 |
| Object text names | 0 | 9 | 7 | 0 | 16 | 0 |
| NPC terminology | 0 | 8663 | 1533 | 1751 | 11927 | 20 |
| Object terminology | 0 | 1073 | 259 | 187 | 1519 | 0 |
| Zone terminology | 3672 | 0 | 0 | 0 | 3672 | 0 |

Total effective category records: **24194**. These include terminology and grouped Gossip records, so the total is not a count of translations ready for Spoken.

Gossip has 375/47/5 raw hash declarations across Classic/SoD/Forever and 427 effective hash entries, plus 26 effective fallback-code entries. It includes `!common`, NPC greetings and menu options; no canonical moment mapping is implied. Readables contain 749 effective item-page string fields and 33 object-page string fields, with four namesake variant tables. Page-chain identity is still unresolved.

The three quest families retain their five positional meanings. Missing slots below include absent, explicit nil and empty strings; omission of progress text can be legitimate and is not automatically a source defect.

| Family | Missing title | Description | Objective | Progress | Completion | AI-marked effective rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Alliance | 0 | 123 | 121 | 553 | 88 | 533 |
| Horde | 0 | 112 | 111 | 466 | 96 | 443 |
| Shared | 0 | 677 | 671 | 1073 | 391 | 612 |

Explicit nil scalar fields: Alliance 885, Horde 785, shared 2812. No missing field inherits an old row's value.

## Faction views and grammar

Six faction/shared collisions occur in the Alliance view; all differ. The Horde view has none. Source dictionaries remain separate, and no faction eligibility inference is made.

| View | Effective with AI | AI-marked in selected view | Effective with AI disabled |
| --- | ---: | ---: | ---: |
| Alliance | 5181 | 1145 | 4041 |
| Horde | 5092 | 1055 | 4037 |

Filtering AI can expose a shared fallback, which explains why subtracting selected AI rows need not give the filtered count.

Effective scalar-string grammar inventory (including source metadata fields):

| Category | Occurrences |
| --- | ---: |
| Player name | 5335 |
| Player class | 1428 |
| Player race | 333 |
| Player gender branches | 7976 |
| Numeric captures | 36 |

The classifier understands 15069 forms. It flags 36 numeric captures as requiring original-text context and three class forms with unsupported case/arity as unknown. Original syntax is retained only in memory; report shapes, hashes and locations let a local reviewer find the source. Classification does not establish rendering or audio support.

## CI and remaining limits

No workflow modification is necessary: the existing `python3 -m unittest discover -s tests -v` discovers all Stage 2A tests. It still checks out only this project and pinned Spoken, installs Lua, builds the original diagnostic pack and runs the suite. It neither downloads ClassicUA nor uploads the audit report. The local build/test commands passed; a remote run was not performed during initial implementation because pushing was outside that task's scope. The prior main-branch CI success is not evidence of a remote Stage 2A run.

No code executes the real ClassicUA Lua, no game pack is produced from its text, and no production or publishing operation occurred. Real-corpus testing proves this pinned syntax and its recognized wrappers, not all future revisions or all game hook behavior. Gameplay eligibility, canonical page chains, source hash-to-Spoken-moment joins, unknown grammar review, and remaining text-display contracts belong to later stages.

Stage 2B should resolve permission scope and runtime display gaps. Stage 3 should build evidence-backed ID crosswalks using this in-memory model, retaining all ambiguity and review flags. No content publication or TTS should precede the applicable rights decision.

## Publication review corrections

Review reproduced a lexer/parser boundary defect: quoted punctuation could be mistaken for table syntax, and a quoted keyword could satisfy a wrapper token check. A failing synthetic regression demonstrated this before correction. Parser structural checks now require the appropriate token type as well as its value. The added test verifies quoted delimiters remain string data and malformed tables/wrappers are rejected.

After correction, 52 tests passed, including all 16 Stage 1 regressions. The pinned real-source audit still found 24194 effective records, and two fresh reports were byte-identical. The diagnostic archive remained identical to the established Stage 1 SHA-256. No source content or production data was published.
