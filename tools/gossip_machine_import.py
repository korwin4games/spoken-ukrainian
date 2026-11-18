#!/usr/bin/env python3
"""Auditable Gossip ClassicUA 1:1 import; private local tests only, no approval."""
import argparse
from collections import Counter
from pathlib import Path
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.gossip_machine import GossipMachineStore, NAME, candidates
from adapters.local_review_store import LocalFile
from adapters.sqlite_translation_store import DB_ENV, connection, enable_sqlite


class GossipMachineImport:
    def __init__(self, state, spoken, allowed=None):
        self.state, self.spoken = state, spoken
        self.allowed = Path(allowed or state.allowed_directory)

    def inspect(self):
        from tools.build_ukrainian import local_gossip_texts
        from tools.gossip_coverage import read_pinned_corpus
        from tools.gossip_translation_review import EMPTY, validate_ledger
        self.state.revalidate_inputs()
        lines = read_pinned_corpus(self.spoken, self.state.inventory.revision)
        enabled = "classicua" in self.state.policy.sources and self.state.policy.stores("classicua")
        lookup = local_gossip_texts(self.state) if enabled else {"byNpc": {}, "common": {}}
        rows, items, unknown = candidates(self.state, lines, lookup)
        manual = LocalFile(self.allowed / "gossip-translation-reviews.json", self.allowed,
                           EMPTY, validate_ledger).data
        statuses = {}
        for row in manual["versions"]:
            status = row["decisions"][-1]["decision"] if row["decisions"] else "pending"
            # All historical manual versions block automation, including stale ones.
            statuses.setdefault(row["english_sha256"], set()).add(status)
        source_targets = set()
        db_path = os.environ.get(DB_ENV)
        if db_path:
            with connection(db_path) as db:
                source_targets = {r[0] for r in db.execute("""SELECT DISTINCT c.target_id
                    FROM source_candidates c WHERE c.domain = 'gossip' AND
                    (EXISTS (SELECT 1 FROM source_candidate_decisions d WHERE d.candidate_id=c.id)
                    OR EXISTS (SELECT 1 FROM source_active_selections a WHERE a.candidate_id=c.id))""")}
        blocked = set()
        for item in items:
            decisions = statuses.get(item["english_sha256"], set())
            if decisions or f"gossip:{item['npc_id']}:{item['english_hash']}" in source_targets:
                blocked.add(item["target_id"])
                # A generic fallback must not bypass a reviewed/rejected NPC row.
                blocked.add(f"gossip:common:{item['english_hash']}")
                item["status"] = ("conflict" if len(decisions) > 1 else
                                  next(iter(decisions)) if decisions else "source_selected")
        for item in items:
            if item["target_id"] in blocked and item["status"] == "eligible":
                item["status"] = "conflict"
        return rows, items, unknown, blocked, manual

    def run(self):
        with self.state._lock:
            rows, _, _, blocked, _ = self.inspect()
            store = GossipMachineStore(self.allowed / NAME, self.allowed)
            count = store.run(rows, blocked)
            return {"machine_imported": count, "approval_status": "unreviewed",
                    "publication_approved": False}

    def build_lookup(self):
        rows, _, _, blocked, _ = self.inspect()
        return GossipMachineStore(self.allowed / NAME, self.allowed).lookup(rows, blocked)

    def page(self, status="all", offset=0, limit=40):
        allowed = {"all", "eligible", "machine_1to1_provisional", "approved", "pending",
                   "rejected", "deferred", "pending_update", "conflict", "untranslated",
                   "source_selected"}
        if status not in allowed or not 0 <= offset <= 200000 or limit not in (20, 40):
            raise ValueError("invalid_gossip_machine_filter")
        rows, items, unknown, blocked, manual = self.inspect()
        store = GossipMachineStore(self.allowed / NAME, self.allowed)
        current = {r["id"] for r in rows if r["target_id"] not in blocked}
        imported = {r["target_id"] for r in store.file.data["imports"] if r["version_id"] in current}
        history = {r["target_id"] for r in store.file.data["versions"]}
        historical_pairs = {(npc, int(r["target_id"].rsplit(":", 1)[1]))
                            for r in store.file.data["versions"] for npc in r["bindings"]}
        for item in items:
            if item["status"] in ("eligible", "untranslated"):
                if item["target_id"] in imported:
                    item["status"] = "machine_1to1_provisional"
                elif item["target_id"] in history or (item["npc_id"], item["english_hash"]) in historical_pairs:
                    item["status"] = "pending_update"
        counts = Counter(i["status"] for i in items)
        filtered = [i for i in items if status == "all" or i["status"] == status]
        return {"total_canonical_npc_wordings": len(items),
                "unique_english_wordings": len({i["english_sha256"] for i in items}),
                "eligible_1to1_candidates": sum(r["target_id"] not in blocked for r in rows),
                "machine_imported_records": len(imported),
                "human_imported_groups": len(manual["imports"]),
                "unknown_context_rows": unknown, "statuses_npc_wordings": dict(counts),
                "total": len(filtered), "offset": offset, "limit": limit,
                "items": filtered[offset:offset + limit],
                "approval_status": "unreviewed", "zip_inclusion": "see_import_statistics"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "import"))
    parser.add_argument("--classicua", type=Path, required=True)
    parser.add_argument("--spoken", type=Path, required=True)
    args = parser.parse_args(argv)
    from tools.review_ui_server import build_state
    state = build_state(args.classicua, args.spoken, ROOT / "build/stage4b-decisions.json",
                        None, ROOT / "build/stage3-ui-reviews.json",
                        ROOT / "build/translation-reviews.json", ROOT / "config/translation_sources.json")
    service = GossipMachineImport(state, args.spoken)
    if args.action == "import":
        service.run()
    page = service.page()
    print(json.dumps({k: v for k, v in page.items() if k != "items"}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    with enable_sqlite(os.environ.get(DB_ENV)):
        raise SystemExit(main())
