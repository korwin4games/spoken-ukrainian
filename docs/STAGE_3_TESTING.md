# Stage 3 testing

Local verification on 2026-11-16; no remote CI or in-game validation is claimed.
Source revisions and coverage are recorded in [implementation](STAGE_3_IMPLEMENTATION.md).

Required commands:

```text
$ python3 tools/version.py check
0.0.1

$ python3 tools/build.py
Archive: /home/korwin/projects/wow/spoken-ukrainian/dist/SpokenCommunity_ukrainian-diagnostic.zip
SHA-256: 5a2519858229c9aa004dbef075d1c8c51561e33f09828112504e0558005c8a8e
Size: 1651 bytes

$ python3 -m unittest discover -s tests -v
Ran 127 tests in 4.899s

OK
```

All commands exited 0. Full per-test output was retained locally in
`/tmp/stage3-final-tests.log`. The diagnostic archive is byte-identical to the
required Stage 1 SHA-256. `sources.lock.json`, VERSION and diagnostic inputs remain
unchanged. System Lua 5.4 and the actual pinned Spoken checkout were available.

`tests/test_stage3.py` adds **23 tests** to the existing 104:

- Restricted public reference indexing, exact pinned blob digests, expected public
  inventory counts, no body fields exported, unknown/unavailable IDs and strict
  canonical syntax.
- Actual pinned quest naming functions, including wording/player-gender/voice
  suffixes; actual pinned Lua checksum over invented ASCII, Ukrainian and NBSP
  strings; independent ClassicUA numeric fingerprint vector; actual pinned Places
  naming helper with a synthetic subzone filename collision. Node was available.
- Persistent schema round-trip, rejected unknown/versioned/duplicate fields,
  independent reviewers, incomplete proof, mismatched speaker/voice, unproven
  Gossip options, exact greetings with several voices, owner/book/page-chain
  changes, missing-middle/shared/reused-title context, alias/target revision drift
  and tampered stored evidence.
- Harmless wording/revision/file-hash drift versus source identity change;
  independent text/grammar/AI review, origin-only changes, stale-if-present audio,
  removed source, masked Forever overrides, line drift and predecessor provenance.
- Faction/AI fallback, unsupported fields, numeric nested Gossip fields, `!code`/
  `!common` exclusion, Unicode templates and metadata-only determinism.
- Two complete independently committed invented ClassicUA snapshots, each audited
  through the real Git reader and existing effective resolver with its own
  reviewed manifest. A changed Classic layer masked by Forever stays unchanged.
  Missing manifest review and using an unapproved revision as the default source
  are rejected. No real source pin is advanced.
- CLI output-boundary enforcement and fixed error output without source bodies.

Existing Stage 2A tests additionally cover the one-level Gossip merge, whole
`!code` replacement, sparse whole-row replacement, inherited SoD readables, empty
Forever tables, explicit nil, duplicate titles/namesakes and parser security.
Existing Stage 1 and Stage 2B Lua tests remain unchanged and pass.

Additional exact results (exit 0):

```text
$ python3 tools/classicua_audit.py --source /tmp/stage3-classicua
Metadata audit written to /home/korwin/projects/wow/spoken-ukrainian/build/classicua-audit.json

$ sha256sum build/stage3-report.json
abfb98e05625adfedbe4f2832c6d8ac1f6f3f5a30ba03d4ca1879c45431042b6  build/stage3-report.json

$ git diff --check
(no output)
```

Real-source Stage 3 CLI validation ran repeatedly against the same clean ClassicUA and
pinned Spoken inputs; the metadata output was byte-identical. Coverage and granular
reason counts are in the implementation report. Derived output stays in ignored
`build/`. The raw declaration denominator includes all source categories and is
not translated coverage. No real approved reviews were supplied; approved joins
and unique canonical intersections are zero for every family.

The synthetic review example (`mapping/example.synthetic.json`) contains invented
reviewers/reference labels and hashes only. It cannot approve any real source unit.
For example, an invented `q:42:accept` proof matches an invented speaker/voice;
changing its wording hash resets content/grammar review without changing that ID.
Changing its speaker or book chain invalidates identity and stale-audio status.

These tests prove offline contract behavior, not Ukrainian display in Forever,
translation quality, rights for independent stories, or successful audio playback.
Stage 2B manual acceptance and Readables text-only blockers remain unchanged.
