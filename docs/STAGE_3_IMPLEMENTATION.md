# Stage 3 implementation — public identities and reviewed crosswalks

Implemented locally on `feat/stage3-canonical-mapping`, 2026-11-16.
**Offline tooling is implemented; real mapping acceptance remains blocked by
independent identity review. Zero real joins are approved.** This report supersedes
the foundation's implementation inventory, not its historical validation record.
The project VERSION remains 0.0.1. No Stage 4 work is included.

## Implementation

| Package | Delivered | Remaining gate |
| --- | --- | --- |
| 3A | Effective resolver reuse, strict narratable field shapes, faction/AI views, hashed namesake identities, source category/context and predecessor provenance | Gossip hash entries are candidates, not proven greetings; sparse readable chains need review |
| 3B | Immutable public Spoken inventory with exact revision/blob validation; quest/Gossip variants and voices, readable owners/chains/checksums, Places canonical keys and boss creature IDs | Target existence does not prove a source-to-target join; no independent human attestations were supplied |
| 3C | Versioned persistent reviews, contextual proof gate, independent mapping/content/grammar/AI states, stable IDs across wording/revision changes, audio impact flags, opt-in two-checkout effective comparison | No newer real ClassicUA revision is approved; two-revision validation uses invented Git snapshots |
| 3D | Sorted metadata-only coverage/impact CLI, synthetic example, machine reasons, distinct coverage denominators and runtime gates | Actual translated coverage remains zero; no content readiness or publication claim |

`adapters/crosswalk.py` consumes the existing `Dataset`, never a second ClassicUA
parser. Quest slots 2/4/5 are accept/progress/complete. Title, objective, `en`, tasks,
nil and empty fields are excluded. Faction-specific rows replace whole shared rows;
AI-disabled views perform the existing pre-lookup filter, including shared fallback.
An overwritten human row is never restored.

Gossip units require a numeric NPC owner and a single numeric hash field containing
text. `!common`, `!code` and unsupported nested option structures are excluded.
Flat numeric entries may still be menu options: they are explicitly unresolved
until reviewed as greetings. Numeric hashes never become `g:` IDs. The resolver's
one-level merge and whole `!code` replacement remain unchanged.

Readables accept positive page positions at the verified item/direct-object or
object-variant depth. `h1` is matching metadata, never narrated. Namesake source
keys are hashed. Position/variant source identities remain stable across wording
and line-number changes; a separate context digest includes page-position layout,
source category, hashed English identity metadata and namesake `h1` fingerprints. Changed namesake/chain context
invalidates identity review conservatively. Missing middle pages are retained as
sparse evidence, never renumbered. Empty Forever tables preserve Classic/SoD rows.
`adapters/classicua/fingerprint.py` implements the reviewed numeric `string_hash`
arithmetic only; language-specific preprocessing is a separate review step.

`adapters/spoken/` validates a clean local checkout at the root lock's Spoken pin
and reads only `git show <pin>:<path>` blobs with SHA-256 checks. Supplemental
public-reference hashes live in `tests/stage3_sources.json`, following the Stage 2B
evidence-manifest convention; **sources.lock.json is unchanged**. Literal Lua data
is read with the restricted parser and exact inspected assignment/wrapper shapes.
Neither ClassicUA Lua nor addon Lua is executed by the adapters.

Public reference inputs at Spoken `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`:

- `pipelines/quests/corpus/corpus.json.gz`, `factions.json`, `gossip_aliases.json`:
  existing line IDs, event, NPC/type, faction evidence, original-wording digest,
  voice and player-gender variants. Followup/chatter are outside this scope.
  Aliases link exposed existing endpoints; they do not rename moments or establish
  Ukrainian joins. Unknown faction eligibility is never sufficient for approval.
- `addons/Spoken_Readables/Data/Books.lua`: existing page IDs, book/position,
  ordered chains, item/object owners and text fingerprints. The stored checksum
  uses UTF-8 storage bytes; client HTML normalization is separately characterized
  with actual pinned `Checksum.lua`. A title alone is never matching proof.
- Places `seed/zones.json` and `Data/enUS/Subzones.lua`: `z:` and English canonical
  `s:` keys. Their presence is public-reference inventory, not verification of
  every zone on Forever or authorization to translate its lore.
- `addons/Spoken_Bosses/Data/Bosses.lua`: `boss:<map>:<key>` plus creature IDs.
  ClassicUA NPC/zone dictionaries do not supply translated stories.

## Review and update procedure

1. Audit the clean pinned ClassicUA checkout. Inspect the source field and its
   resolved category/layer/predecessors privately. Do not paste bodies into JSON,
   logs or Git. Record the field hash and source context digest.
2. An evidence reviewer independently inspects pinned public references proving
   that source field and target describe the same moment. Record public reference
   paths/digests and exact identity facts. English comments/title similarity alone
   are insufficient. A second, distinct mapping reviewer approves the join with
   `approve_review()`. This validates attestation consistency, not human truth.
3. For quests verify numeric quest/event, actual faction eligibility, speaker/type,
   voice, original wording and player-gender/wording variant together. Do not mix
   the speaker from one variant with another variant's voice. Source filename is
   not proof of game eligibility.
4. For Gossip prove NPC/object identity and greeting versus option, original moment
   and voice. Where a ClassicUA hash is used, independently reproduce its exact
   normalization and numeric hash; it is never the canonical MD5. Preserve known
   canonical aliases/voice variants rather than minting replacement IDs.
5. For Readables prove owner/book and complete actual server page chain, including
   shared pages and missing middle pages, original-page checksum and position.
   Independently validate `h1` against the first English page when namesakes exist.
   Reused titles/unknown owners remain unresolved; never equate item or ordinal
   with a pageTextID. Facts must match one complete target context.
6. Places/Bosses reference keys can be inventoried but ClassicUA terminology cannot
   be approved as translated lore/story. Separately authored or cleared stories
   belong to a later scoped task. Do not invent source units for these families.
7. Review Ukrainian fidelity and grammar separately: case, capitalization, gender,
   class/race/name and unsupported/numeric templates. AI-marked units require an
   independent AI decision. Identity approval leaves all content states pending.
8. For an authorized update, provide a second clean checkout plus a separate JSON
   manifest containing `revision` (full commit), `files` (complete relevant SHA-256
   set) and `review_by`. The same resolver audits both inputs. No fetch/apply,
   branch tracking, lock writes, merge or release occurs.
9. Reuse approved identity on text changes with unchanged matching evidence, while
   resetting content/grammar/AI review and flagging audio stale. Origin/template
   changes invalidate dependent review/audio; AI-only changes reset AI eligibility
   without declaring unchanged recording bytes stale. Speaker/voice/owner/chain,
   alias context or target revision changes invalidate mapping and audio. Removed
   units require fallback/eligibility review. Source-file-only drift retains
   content review; masked prior-layer edits produce unchanged effective units.

`MappingDecision` remains a foundation primitive. The persisted schema additionally
stores source/target context, baseline grammar/AI/origin and the structured proof.
`load_reviews()` rejects unknown fields/versions and duplicate source approvals;
`assess_review()` reruns the contextual proof checks against current inventories.
An external attestation is a human input, not a cryptographic or automated proof
that its reviewer inspected the evidence. No real reviewer identities are invented.
The only committed review example is explicitly synthetic.

## Commands and verified coverage

```sh
python3 tools/stage3_report.py --classicua /tmp/stage3-classicua --spoken ../spoken-wow
# Optional local update analysis:
python3 tools/stage3_report.py --classicua /path/to/baseline --spoken /path/to/spoken --candidate /path/to/reviewed-candidate --candidate-manifest /path/to/reviewed-manifest.json
```

Optional `--reviews` reads reviewed schema version 1. Output defaults to ignored
`build/stage3-report.json`; paths outside repository `build/` or inside an input
checkout are rejected. Errors are sanitized to a fixed machine message. Raw source
bodies and unreviewed English dialogue are never serialized by the report.

Real-source audit: ClassicUA `1770d208ad853d23d61105cf510d53804770d916`, all 36
locked file digests validated, clean detached temporary checkout. The report counts
24,301 raw declarations across **all adapter categories**, not narratable units.

| Family | Resolved source candidates | Public canonical target IDs/variants | Approved source joins / unique canonical intersections |
| --- | ---: | ---: | ---: |
| Quests | 25,101 (two faction views) | 12,594 | 0 / 0 |
| Gossip | 100 (greeting classification pending) | 4,641 | 0 / 0 |
| Readables | 782 | 1,160 | 0 / 0 |
| Places | 0 story units | 947 zone/subzone keys | 0 / 0 |
| Bosses | 0 story units | 297 | 0 / 0 |

Total source candidates: **25,983**. AI-marked quest units: **4,291**. The AI-disabled
resolver produces **21,705** total units; shared fallback means this is not simple
subtraction. These are explicit source/target denominators, not a Forever completion
percentage. Target variants and faction source views can describe the same canonical
moment; only reviewed unique intersections count as mapped target coverage.

Candidate machine-reason counts (mutually exclusive, with AI exclusion first):

| Reason | Units |
| --- | ---: |
| `speaker_wording_eligibility_review_required` | 14,545 |
| `faction_eligibility_conflict` | 2,169 |
| `multiple_wording_or_voice_variants` | 245 |
| `target_unavailable` | 3,851 |
| `ai_independent_review_required` | 4,291 |
| `greeting_moment_voice_evidence_required` | 100 |
| `owner_page_chain_checksum_evidence_required` | 782 |

The extraction-exclusion report separately records 34,400 quest title/objective/
metadata fields, 5,718 empty/nil/nontext quest slots, 353 Gossip common/code/
unsupported fields, 4 readable `h1` metadata fields, 3,672 zone terminology records
and 11,927 NPC terminology records. These mixed field/record denominators are
explicit exclusions, not additional candidate units or percentages.

No independent real join review was supplied by this task or found in the existing
foundation. Therefore no real mapping is promoted. Full Stage 3 mapping acceptance
cannot truthfully be declared complete merely because tooling and tests pass.

## Runtime, rights and validation

Stage 2B remains unchanged: Ukrainian Quest/Gossip independent captions on `enUS`
are blocked; Readables text-only entries remain unsafe for audio resolution and
English-client Compendium selection remains blocked; Bosses story selection stays
client-gated. Places diagnostic text works under its existing contract. Manual
Forever tests remain pending for the other surfaces. Mapping is not display support.

ClassicUA permission/attribution remain as recorded in `CLASSICUA_PERMISSION.md`.
Unrelated lore/font/provider rights and explicit release authorization remain gates.
No source pins, upstream repositories, installed AddOns, audio, translated packs,
production services, versions, Git commits, pushes, PRs, merges or releases changed.

Exact required validation output and test scope are in
[STAGE_3_TESTING.md](STAGE_3_TESTING.md). Local final review found no additional
actionable defect after the fixes covered by the tests. Residual limits are the
missing independent real joins, pending content review and pending client tests.
