# Translation Review Agent

The local Review UI and [CLI](CLI.md) share one deterministic evaluator and one
SQLite service. The agent checks English and Ukrainian fingerprints, pinned
revisions, evidence, player placeholders, formatting, Cyrillic text, selected
Warcraft terms and AI flags. Grammar, meaning and dialogue nuance remain
human review tasks. A verified assessment means the implemented checks passed
for this exact local-test candidate.

- Quest import requires an independently reviewed Stage 3 identity and fresh
  audited source field. Quest machine hints can receive advisory assessments.
- Gossip NPC and common lookups use pinned ClassicUA effective fields and
  collision-free English hashes. Each bound NPC needs a pinned Spoken Gossip
  moment. Common stays one runtime entry. This does not create a human-reviewed
  Stage 3 Gossip join or identify arbitrary player reply options.
- External source snapshots need independently established provenance and
  rights before they can qualify. Claimed provenance is displayed as such.
  The existing Source Revision Review owns human decisions and active selection.

## Manual verification

1. Start the local Review UI using the pinned checkouts and a private database.
   Open **Агент перевірки перекладів** and load records for Gossip or Quests.
2. Select one record or mark several and review the batch. Use **Історія
   вибраного** to see previous results. An unjoined Quest hint should require
   human review. Use a fresh matching Gossip entry to exercise verified import.
3. Preview the bulk import. Confirm the import for the selected module and
   repeat it. Already imported records should remain one import each.
4. Run `translation_db.py imports` and inspect the agent route. Build with
   `build_ukrainian.py` in the same environment and inspect the latest ZIP
   inventory. An assessment by itself does not appear as an import.
5. In **Порівняння джерел і ревізій**, load the captured snapshots. Compare two
   revisions of one provider and then select **Різні джерела**. A missing
   provider needs an actual captured or ingested snapshot. Inspect both texts,
   their provenance and the change filters. Activation uses existing reviewed
   source selection and requires an explicit user action.
6. Verify the resulting private ZIP locally in Forever via the
   [game test checklist](QUEST_LOCAL_TEST_BUILD.md). Native dialog, captions,
   and audio have independent acceptance gates.

## Optional model notes

The CLI accepts a private JSON file under `build/` for `review one`.
The browser accepts the same JSON schema in the model-notes field. A user
may supply notes from a separately run model. No model executable or API is
configured or invoked by the agent. Use this schema:

```json
{
  "candidate_id": "exact candidate fingerprint from status",
  "model_version": "model and version",
  "status": "available",
  "findings": ["Verify whether the NPC speaks formally."],
  "corrections": ["Consider the formal form of address."]
}
```

Use `unavailable` with empty lists to record an unavailable model. Unknown
fields and mismatched candidate IDs are rejected. Model text is assessed as
untrusted data and shown as plain text. A model can only add advisory notes.
Its output cannot grant identity, rights, eligibility or approvals. Run a
separate deterministic review to evaluate import eligibility.

## Status and persistence

`agent_verified` means the deterministic checks passed. Format or fingerprint
failures can produce `agent_reject_recommended`. Missing evidence, unverified
linguistic findings or an available model submission require human review.
`agent_unavailable` records an explicitly provided unavailable assessment.
`stale` is derived by comparing historical fingerprints with current evidence.
The previous status and timestamp remain in history. Once a write or a build
records staleness, even an exact revert requires another explicit assessment
and import.

Schema v6 adds separate assessment rows, evidence invalidation tracking and
an append-only import/invalidation audit. Evidence carries no source text
bodies apart from explicitly submitted, private advisory notes. The existing
human and machine histories keep their own formats. SQLite backups include
agent data. Review dry runs do not add assessments. Preview does not write
imports. Opening SQLite can initialize or migrate the database and read
legacy review ledgers.

Bulk import requires a confirmed operation, skips stale/ambiguous/conflicting
records, and preserves manual edits, human decisions and source activation.
A subsequent build revalidates the imports and preserves human precedence.
Import statistics reflect the last checked evidence, with known invalidations
excluded. Latest ZIP statistics describe the actual previously built artifact.
Agent imports are eligible only for private local tests.
