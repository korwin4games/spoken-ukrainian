# Stage 3 specification — canonical mapping and update-ready ClassicUA integration

**Status:** planned, not implemented. Stage 2A provides the restricted pinned-source parser, effective-record resolver and metadata-only audit. Stage 2B must establish runtime text-display requirements separately. This document adds a long-term **translation updateability** requirement to Stage 3; it does not authorize source import, generated packs, automatic sync or publication.

See [implementation plan](IMPLEMENTATION_PLAN.md), [source integration](SOURCE_INTEGRATION.md), [Stage 2A implementation](STAGE_2A_IMPLEMENTATION.md), [compatibility](COMPATIBILITY_MATRIX.md), [rights](LEGAL_AND_ATTRIBUTION.md) and [versioning](VERSIONING.md).

## Objective

ClassicUA remains the upstream authority for its Ukrainian translations. Spoken Ukrainian must be able to **reprocess newer, explicitly reviewed ClassicUA revisions** without remapping every unchanged record or maintaining a parallel editable translation corpus. Stable, evidence-backed crosswalks link effective ClassicUA records to **existing canonical Spoken identities**, and later rebuilds can identify which translated units require review or packaging changes.

Stage 3 primarily delivers mapping and update-aware data contracts. A fully automated updater, licensed content packaging, audio generation, GitHub releases and user-facing pack updates are **later stages** and must not be silently added here.

## Inputs and boundaries

- ClassicUA and Spoken inputs are immutable, explicitly pinned repository commits with relevant file SHA-256 values in `sources.lock.json`. Stage 2A currently pins ClassicUA `1770d208ad853d23d61105cf510d53804770d916` and Spoken `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`.
- Analyze ClassicUA from a **separate clean local checkout** using the existing Stage 2A adapter; do not execute arbitrary Lua, modify upstream, fetch production data or silently advance a lock in a normal build.
- Canonical Spoken identities and matching evidence must come from pinned, authorized **public** references. When evidence is absent or ambiguous, reject and report the mapping rather than manufacture an ID.
- Store only minimal hand-reviewed mapping decisions, exclusions, evidence references, hashes and review attestations in Git. Avoid tracked copies of ClassicUA translation text or large normalized records.
- The ClassicUA maintainer granted permission for project-specific translation use, adaptation, AI TTS and distribution ([permission record](CLASSICUA_PERMISSION.md)). This approval does not itself establish third-party lore/font rights or authorize our tooling to publish or call providers. Use invented synthetic text in committed tests and metadata-only reports for real-source analysis.

## Proposed mapping model (design contract, not a final schema)

Each reviewable mapping decision should retain at least:

| Field | Purpose |
| --- | --- |
| `source_identity` | Stable ClassicUA family and key plus event/field or page position as appropriate, separate from the text itself. |
| `source_revision` / `source_file_sha256` | Source provenance and the reviewed baseline. |
| `effective_field_sha256` | Detect changes in effective translated text, including change of layer/origin; do not store the raw text. |
| `source_origin` | Resolved Classic/SoD/Forever layer, source path, located key/field and overridden predecessor references. |
| `target_identity` | Existing canonical Spoken ID, not a re-minted translation hash. |
| `match_evidence` | Verified quest/event/speaker, gossip moment/voice, readable owner/page chain, or map/encounter evidence, as applicable. |
| `review` | Mapping approval separate from text/grammar approval, AI status, review provenance and observed input hashes. |
| `status` / `reason` | Mapped, unresolved, ambiguous, excluded or invalidated, with machine-readable reasons. |

The eventual schema may evolve, but it must separate **mapping identity validity** from **translation content approval**. A text edit does not by itself prove that a canonical Spoken ID changed; a source ID or upstream target-identity change must not be treated as a harmless wording update.

## Canonical mapping requirements

- **Quests:** retain `q:<questID>:accept/progress/complete` and verified wording/voice variants, faction eligibility and speaker evidence; sparse source slots 2/4/5 map to dialogue events. Source filename alone does not prove game eligibility.
- **Gossip:** resolve NPC/object and original moment/voice against Spoken's canonical `g:` identifiers. ClassicUA numeric hashes are not Spoken MD5 identities; options are not automatically spoken pages.
- **Readables:** map ClassicUA item IDs or object-name/`h1` namesakes to verified Spoken owners, page chains and `b:` page IDs. Do not use item IDs, book titles or page numbers as page IDs.
- **Places:** preserve `z:<uiMapID>` and `s:<uiMapID>:<EnglishCanonicalKey>`. ClassicUA zone names are terminology, **not** translated lore stories.
- **Bosses:** resolve encounter/creature evidence to existing `boss:<map>:<key>` identities. NPC names alone do not establish stories or IDs.

Preserve known aliases, stable existing IDs, speaker variants, and partial/unknown matches. Document the exact reference baseline and matching algorithms. Coverage must use explicit denominators (effective source units, target units, mapped intersections), not raw ClassicUA declaration totals.

## Change detection and update behavior

An eventual update candidate compares **two independently pinned ClassicUA snapshots** through the same effective resolver. The semantic diff is over effective records **after** actual TOC/XML load order, whole-row replacements, Gossip one-level merges, AI filtering and faction/shared precedence — never solely `git diff` of Lua files.

Classify changes at the appropriate family/key/field granularity:

| Classification | Expected behavior |
| --- | --- |
| Unchanged effective content and matching evidence | Reuse an approved mapping and relevant review; avoid unnecessary pack/audio rebuilds. |
| Source-only edit hidden by an effective override | Report source drift if useful, but do not claim a changed effective translation. |
| Wording, grammar or origin changed; same validated target identity | Keep the canonical mapping provisionally; invalidate **content-dependent** review and flag any existing audio take as stale. |
| Identity, page chain, speaker, voice, locale-matching or reference evidence changed | Revalidate the mapping; reject ambiguous joins rather than silently reassign IDs. |
| Newly effective unit | Attempt evidence-backed matching; otherwise report unmapped. |
| Removed or no-longer-effective unit | Report removal, review fallback/eligibility; never silently leave an outdated translated entry in a future pack. |
| AI flag or review policy changed | Re-evaluate publication eligibility even if wording is unchanged. |

**Important edge cases:** Classic row edits masked by Forever; sparse later quest rows; inherited SoD readables; empty Forever tables; Gossip hash/`!code` overrides; different Alliance/Horde views; namesakes with identical titles; missing middle pages; unchanged text with changed speaker identity; template changes without visible wording changes.

Use stable deterministic ordering and report all reasons for invalidation. Compare the **generated effective translation data**, not only source file hashes. Changing file hashes is a reason to re-audit and reevaluate impacted provenance, not a reason to discard every reviewed ID mapping without checking its evidence.

## Intended updater workflow (future, not implemented in Stage 3)

1. **Check:** find an upstream candidate revision in a separately authorized workflow; record commit and relevant hashes without changing the active lock.
2. **Analyze:** run the pinned parser/resolver twice (old and candidate), derive metadata-only effective diffs and impacted mapping/review/audio records.
3. **Review:** present added/modified/removed/unchanged counts, uncertain mappings, AI/grammar issues, source provenance and licensing status. Do not include translation bodies in public logs or PRs.
4. **Approve:** require a human-reviewed update PR for new source pin/hash values and affected mapping decisions; no automatic merges.
5. **Build later:** when permissions and module runtime contracts permit, rebuild only the impacted authorized pack content, with stable canonical identities.
6. **Audio later:** invalidate or regenerate changed takes only under approved provider, processing rights and budget. Never pair newly edited captions with stale audio unnoticed.
7. **Publish later:** release new independently versioned packs after tests, content-rights checks and an explicit publication decision. Do not equate the root project `VERSION` with every pack's `.toc` version.

The suggested CLI names (`check`, `diff`, `apply`) are *design ideas only*. No updater CLI or scheduled workflow currently exists. In particular, normal `tools/build.py` and `tools/classicua_audit.py` must remain offline/read-only with no silent network fetch or lock mutation.

## Stage 3 acceptance criteria

1. Deterministic, evidence-based crosswalks for the scoped categories; ambiguous identities have explicit rejected reasons.
2. The model records reviewed source/target identity, provenance, hashes and **separate** mapping/content/grammar/AI statuses, without committing third-party translation bodies.
3. Synthetic tests show that an unchanged record retains its mapping across source revisions, while changed text invalidates content-dependent review and flags audio impact **without** changing the canonical ID automatically.
4. A later-layer override masks an earlier source edit in the effective diff; whole-row quest replacement, Gossip merge/`!code`, faction fallback and inherited readables remain correct.
5. Additions, removals, identity changes, speaker/page-chain changes, AI status and template changes produce explicit impact reports.
6. Reports distinguish raw source inventory from mapped Spoken coverage and are deterministic, metadata-only and safe for Git/CI.
7. Normal builds never update source pins silently, publish content, call production services or generate TTS.
8. Existing project version checks, Stage 1 diagnostic ZIP regression and Stage 2A tests remain valid.
9. Stage 2B runtime display limitations, required review/attribution, unrelated content rights and explicit release authorization remain gates for affected pack publication; ClassicUA's translation permission is recorded separately. Successful mapping is **not** proof of a display-capable addon.

## Out of scope now

No ClassicUA translation files, original or generated audio, bulk JSON/Lua translation exports, live synchronization, release automation, direct edits to Spoken Player, private database access, production APIs or unapproved TTS calls. Changes to the source lock, release assets and public packs require their own explicitly authorized tasks.

This specification supplements the historical Stage 0 plan; it does not rewrite Stage 0 evidence or imply that Stage 3 is already implemented.
