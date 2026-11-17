# Gossip coverage audit (metadata only)

Run from the repository root after checking out the exact pinned revisions of
Spoken and ClassicUA from sources.lock.json:

```bash
uv sync --locked
uv run --locked python tools/gossip_coverage.py --classicua ../ClassicUA --spoken ../spoken-wow
```

The command uses the *committed* pinned Spoken gzip corpus, validated audited
ClassicUA layered Gossip data and the same exact English hash algorithm as the
native Gossip UI. It does not access the network, translate new text, or change
either external repository.

Outputs (ignored private files, also CI artifacts):
- build/gossip-coverage.json: distinct NPC IDs and distinct English wordings
  from corpus rows with source=gossip and npcType=creature/vehicle, including
  how many can be matched via NPC-scoped hash and via !common fallback.
- build/gossip-untranslated-npcs.csv: NPC metadata and missing-wording counts,
  sorted by largest gap, without copyrighted English or Ukrainian text.

"Covered NPC" means **at least one** corpus wording matched; "fully covered"
means *all* distinct corpus wordings matched. A fully untranslated NPC is one
with no matching wording. Hash results are **potential build-time coverage**,
not proof that the live game displays the same wording or that a particular
Gossip reply option appears in the Spoken corpus.

Out of scope: gameobjects and items, quest titles, UI translation coverage,
dynamic ClassicUA !code aliases, wordings absent from Spoken corpus, actual
client acceptance, reviewer approval, audio or caption replacement. Localized
client-side presentation and dynamic variables can further limit matches.
