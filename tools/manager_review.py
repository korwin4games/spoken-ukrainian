"""Apply an explicit reviewer decision in the manager's staged database."""
import re

from adapters.classicua.grammar import inventory
from adapters.crosswalk import quest_moment
from adapters.source_revision_store import CHECKS, SourceReviewStore, sha
from adapters.translation_agent import CLIENT_TOKENS, placeholders
from tools.build_ukrainian import MODULE_DOMAINS, local_gossip_texts
from tools.gossip_coverage import read_pinned_corpus
from tools.gossip_translation_review import GossipReviews, discover_groups, normalized, version_status
from tools.source_revision_review import gossip_contexts, quest_contexts
from tools import quest_runtime_review


def validate_text(english, text):
    if (type(text) is not str or not text.strip() or len(text) > 60000
            or placeholders(english) != placeholders(text)
            or CLIENT_TOKENS.search(text)
            or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text)
            or any(form.status != "supported" for form in inventory(text))):
        raise ValueError("manager_invalid_translation_format")


def validate_quest_text(originals, text):
    for original in originals:
        validate_text(original, text)
    if re.search(r"\|[cCrRhHtTaA]", text):
        raise ValueError("manager_invalid_translation_format")


def apply_review(action, payload, module, row, state, spoken, db_path):
    domain = MODULE_DOMAINS[module]
    if action in ("choose_quest", "save_quest"):
        if domain != "quest":
            raise ValueError("manager_invalid_review_request")
        from tools.quest_simple import apply_choice
        return apply_choice(action, payload, row, state, db_path)
    if action == "review_mapping":
        proof = payload.get("join")
        if (set(payload) != {"identity", "join", "confirm"} or payload["confirm"] is not True
                or domain != "quest" or type(proof) is not dict
                or type(proof.get("target_id")) is not str
                or proof["target_id"] not in {v["target_id"] for v in row.get("original_variants", [])}):
            raise ValueError("manager_invalid_review_request")
        state.approve_mapping(proof)
        return None

    expected = {"identity", "candidate", "reviewer", "confirm"}
    if action == "confirm_candidate":
        expected.add("checks")
    elif action == "save_translation":
        expected.add("text")
    elif action not in ("register_candidate", "withdraw_quest_approval"):
        raise ValueError("manager_invalid_review_request")
    if domain == "quest" and "review_binding" in row:
        expected.add("binding")
    if (set(payload) != expected or payload["confirm"] is not True
            or type(payload["reviewer"]) is not str or not 0 < len(payload["reviewer"].strip()) <= 120
            or type(payload["candidate"]) is not str):
        raise ValueError("manager_invalid_review_request")
    quest_binding = domain == "quest" and "review_binding" in row
    if (quest_binding and (not row["review_binding"] or payload["binding"] != row["review_binding"])
            or not quest_binding and len(row["originals"]) != 1) or row["mapping_state"] in (
            "invalid_context", "mapping_conflict", "mapping_rejected", "stale"):
        raise ValueError("manager_review_context_blocked")
    reviewer, candidate_id = payload["reviewer"], payload["candidate"]
    original = row["originals"][0]
    choice = next((c for c in row["candidates"] if c.get("review_id") == candidate_id), None)
    runtime_confirmation = False
    if action == "withdraw_quest_approval" and not quest_binding:
        raise ValueError("manager_invalid_review_request")
    if quest_binding:
        if state.revalidate_inputs is not None:
            state.revalidate_inputs()
        targets = {variant["target_id"] for variant in row["original_variants"]}
        binding, originals = quest_runtime_review.binding(state, row["id"], targets)
        if action == "withdraw_quest_approval":
            candidate = quest_runtime_review.candidate_key(choice) if choice else None
            decision = next((r for r in quest_runtime_review.current_decisions(quest_runtime_review.history(db_path))
                             if r["candidate"] == candidate and r["evidence"] == binding), None)
            if not decision:
                raise ValueError("manager_candidate_unavailable")
            quest_runtime_review.save(db_path, row["id"], candidate, binding, decision["text"],
                                      "withdrawn", reviewer, {})
            return None
        if action == "save_translation" and (not candidate_id or choice and choice["review_kind"] == "runtime"):
            if candidate_id and choice.get("eligibility") != "selectable":
                raise ValueError("manager_candidate_unavailable")
            validate_quest_text(originals, payload["text"])
            quest_runtime_review.save(db_path, row["id"], "manual", binding, payload["text"],
                                      "pending", reviewer, {})
            return None
        runtime_confirmation = action == "confirm_candidate"
        if action == "save_translation" and (not choice or choice.get("eligibility") != "selectable"):
            raise ValueError("manager_candidate_unavailable")
    if action == "register_candidate" or (action == "save_translation" and domain == "quest" and not candidate_id):
        if domain != "quest" or row["mapping_state"] != "mapping_verified":
            raise ValueError("source_quest_selection_requires_approved_stage3_mapping")
        if state.revalidate_inputs is not None:
            state.revalidate_inputs()
        keys = {c["registration_key"] for c in row["candidates"] if "registration_key" in c
                and (not candidate_id or c["registration_key"] == candidate_id)}
        observations = state.translation_observations()
        matches = [o for o in observations if o.row()["id"] in keys and quest_moment(o.target_id) == row["id"]
                   and o.original in row["originals"] and o.row()["rights_status"] == "reviewed"
                   and state.policy.stores(o.row()["provenance"][0]["provider"])]
        if len(matches) != 1 or (action == "register_candidate" and not candidate_id):
            raise ValueError("manager_candidate_unavailable")
        base = matches[0].row()
        validate_quest_text(row["originals"], base["text"] if action == "register_candidate" else payload["text"])
        state.translations.observe(matches, state.policy, one_to_one_pairs=set())
        if action == "save_translation":
            state.translation_action("edit", {"identity": base["id"], "text": payload["text"], "reviewer": reviewer})
        return None
    if action == "confirm_candidate":
        checks = payload["checks"]
        if type(checks) is not dict or set(checks) != set(CHECKS) or any(v is not True for v in checks.values()):
            raise ValueError("manager_review_checks_required")
        if (choice is None or choice.get("eligibility", "selectable") != "selectable"
                or choice["review"] in ("rejected", "deferred", "stale", "pending_update")):
            raise ValueError("manager_candidate_unavailable")
        text = choice["text"]
    else:
        text = payload["text"]
    if domain == "quest":
        validate_quest_text(row["originals"], text)
    else:
        validate_text(original, text)

    if choice and choice["review_kind"] == "source":
        if action != "confirm_candidate":
            raise ValueError("manager_invalid_review_request")
        store = SourceReviewStore(db_path)
        selected = next((c for c in store.candidates() if c["id"] == candidate_id), None)
        if (selected is None or selected["domain"] != domain
                or selected["text_sha256"] != sha(text) or selected["ukrainian_text"] != text):
            raise ValueError("manager_candidate_unavailable")
        target = selected["target_id"]
        if selected["provider"] == "classicua" and selected["revision"] != state.source.revision:
            raise ValueError("manager_candidate_unavailable")
        if domain == "quest":
            if (quest_moment(target) != row["id"]
                    or target not in {o.target_id for o in state.translation_observations()}):
                raise ValueError("source_quest_selection_requires_approved_stage3_mapping")
            trusted = quest_contexts(state)
            if any(quest_moment(s["target_id"]) == row["id"] and s["text_sha256"] != sha(text)
                   for s in store.active(trusted, domain="quest", skipped=[])):
                raise ValueError("conflicting_quest_runtime_variants")
        else:
            if target != f"gossip:{row.get('npc_id')}:{row.get('english_hash')}":
                raise ValueError("manager_review_context_blocked")
            trusted = gossip_contexts(read_pinned_corpus(spoken, state.inventory.revision))
        if not runtime_confirmation:
            if choice["review"] not in ("approved", "source_selected"):
                store.decide(candidate_id, "approved", reviewer, checks, trusted)
            if choice["review"] != "source_selected":
                store.activate(candidate_id, reviewer, trusted)
    elif domain == "quest" and not runtime_confirmation:
        if not choice or choice["review_kind"] != "quest":
            raise ValueError("source_quest_selection_requires_approved_stage3_mapping")
        if action == "save_translation":
            state.translation_action("edit", {"identity": candidate_id, "text": text, "reviewer": reviewer})
        elif choice["review"] != "approved":
            state.translation_action("decide", {"identity": candidate_id, "decision": "approved",
                "reviewer": reviewer, "checks": {k: v for k, v in checks.items() if k != "all_contexts"}})
    elif domain == "gossip":
        lines = read_pinned_corpus(spoken, state.inventory.revision)
        groups, _ = discover_groups(lines, local_gossip_texts(state), state.inventory.revision,
                                    state.source.revision)
        reviews = GossipReviews(groups, state.inventory.revision, state.source.revision)
        group_id = sha(normalized(original))
        group = reviews.groups.get(group_id)
        if group is None or not any(
                (c["npc_id"], c["english_hash"]) == (row.get("npc_id"), row.get("english_hash"))
                for c in group["contexts"]):
            raise ValueError("manager_review_context_blocked")
        if action == "save_translation":
            if candidate_id and (not choice or choice["review_kind"] != "gossip"):
                raise ValueError("manager_candidate_unavailable")
            reviews.propose([{"group_id": group_id, "english_sha256": group["english_sha256"],
                "context_sha256": group["context_sha256"], "ukrainian_text": text}], "manual")
        else:
            version = next((v for v in reviews.file.data["versions"] if v["id"] == candidate_id), None)
            if version is None or version["group_id"] != group_id or not reviews.current(version):
                raise ValueError("manager_candidate_unavailable")
            if version_status(version) != "approved":
                reviews.decide(candidate_id, "approved", reviewer, checks)
    if runtime_confirmation:
        quest_runtime_review.save(db_path, row["id"], quest_runtime_review.candidate_key(choice),
                                  binding, text, "approved",
                                  reviewer, checks)
    return sha(text) if action == "confirm_candidate" else None
