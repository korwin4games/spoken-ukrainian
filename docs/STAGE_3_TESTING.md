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

## P2 source provenance regression validation

Local verification on 2026-11-16 before committing the P2 fix on
`feat/stage3-canonical-mapping`. The earlier 127-test record remains historical;
these local results do not claim remote CI for the unpushed fix.

```text
$ python3 tools/version.py check
0.0.1

$ python3 tools/build.py
Archive: /home/korwin/projects/wow/spoken-ukrainian/dist/SpokenCommunity_ukrainian-diagnostic.zip
SHA-256: 5a2519858229c9aa004dbef075d1c8c51561e33f09828112504e0558005c8a8e
Size: 1651 bytes

$ python3 -m unittest discover -s tests -v
Ran 142 tests in 5.279s

OK

$ git diff --check
(no output)
```

All four commands exited **0**. No tests were skipped. Full local test output:
`/tmp/p2-final-tests.log`. All Stage 1, Stage 2A, Stage 2B and existing Stage 3
checks pass. Stage 2A parser/resolver code is unchanged. The diagnostic archive
matches the required byte-identical SHA-256. VERSION, `sources.lock.json`, addon
inputs and tracked files in both external checkouts are unchanged.

`SourceProvenanceTests` adds **15 regression tests** (38 Stage 3 tests total):

1. Correct source SHA, independently calculated from invented fixture bytes,
   permits approval with the exact file/field reference and valid join evidence.
2. An arbitrary syntactically valid digest is rejected even when the proof digest
   has been recomputed to include it.
3. A valid digest of a different ClassicUA file is rejected.
4. Wrong file/revision references and unvalidated alternate artifacts are rejected.
5. A reference to another field in the same correctly hashed blob is rejected.
6. A unit inconsistent with the independently supplied inventory is rejected.
7. Missing inventory, source reference or source digest is rejected.
8. Valid provenance does not replace speaker/voice/join facts or independent
   evidence and mapping reviewers.
9. Low-level mapping and retention cannot bypass the source gate; retention also
   checks contextual join facts against the actual target inventory.
10. Corrupted persisted file/revision/text/proof provenance is rejected against
    the independently audited historical inventory, including internally altered
    metadata that cannot validate itself.
11. Missing/incomplete historical evidence never becomes an approved review.
12. An existing mapping survives changed wording, revision and source blob while
    text/grammar/AI review resets and audio becomes stale; that historical proof
    cannot be reused as a **new** approval against the new source artifact.
13. File-only/comment and line-number-only drift retain prior identity/content
    review and report unchanged audio.
14. Source identity/context changes invalidate mapping and require review.
15. Reordered equivalent inputs produce identical metadata without fixture-body
    leaks in reports or review JSON.

The existing two-checkout workflow test now additionally creates a review from
an actual audited **invented** Git snapshot, persists/loads it using its historical
inventory, and assesses the second independently pinned snapshot. A hidden Classic
edit masked by Forever retains the reviewed canonical identity. Supplying only
the candidate inventory cannot authenticate the historical review. All new fixture
text and reviewer labels are explicitly invented; no real translation bodies,
reviewer attestations or historical real approvals have been added.

The original arbitrary `'b' * 64` source digest in `reviewed()` is replaced with
the SHA-256 of the actual invented source bytes. `mapping/example.synthetic.json`
is regenerated from that verified synthetic fixture. Schema version **1** is
unchanged; production loading now requires audited baseline inventories and rejects
unsupported versions, incomplete records and formerly accepted unverifiable refs.

Real-source compatibility checks (both commands exited 0):

```sh
python3 tools/stage3_report.py --classicua /tmp/stage3-classicua --spoken ../spoken-wow --output build/p2-stage3-first.json
python3 tools/stage3_report.py --classicua /tmp/stage3-classicua --spoken ../spoken-wow --output build/p2-stage3-second.json
```

Both metadata files are byte-identical and retain the previous report SHA-256:
`abfb98e05625adfedbe4f2832c6d8ac1f6f3f5a30ba03d4ca1879c45431042b6`.
Target inventory counts remain 12,594 quest identities/variants, 4,641 Gossip
identities/variants, 1,160 readable pages, 947 Places keys and 297 boss keys.
Source candidate counts remain 25,101 quests, 100 Gossip and 782 readable units;
Places/Bosses have no translated story units. **Zero real joins are approved.**
File-only changes may change reported provenance hashes; they do not change
semantic impact or retained-review status. Reproducibility means identical
metadata for identical audited inputs, independent of input ordering.

Automated provenance validation proves the referenced source blob and effective
field are the audited ones. It does **not** prove that a ClassicUA field matches
a Spoken canonical identity. Contextual cross-source evidence and independent
human review remain required; runtime readiness and manual Forever tests remain
separate and unchanged. Alternate evidence artifacts are rejected, and unavailable
historical baselines require an explicit local audit rather than a network fetch.
The user subsequently authorized committing and pushing the fix to PR #7. No PR
merge, source update, translated pack or audio generation is part of this task.
