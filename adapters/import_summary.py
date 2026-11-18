"""Metadata-only, deterministic coverage report for an inert local translation import.

Counts every canonical Spoken target, including families not yet supported by
the Quest review bridge. Never leaks original text, translation bodies or
reviewer identifiers.
"""
from collections import Counter



def unique_one_to_one_hint_pairs(hints, source_units, inventory, *, allow_ai_transations=False):
    """Conservative exact-cardinality Quest hints, NOT approved mappings.

    The reverse degree counts *all* source candidates (including excluded AI
    and ambiguous sources). Two factions or voice variants sharing a target
    therefore never qualify through partial filtering.
    """
    if type(allow_ai_transations) is not bool:
        raise ValueError("invalid_allow_ai_transations")
    target_degree = Counter(target for row in hints for target in set(row["candidates"])
                            if target in inventory.targets)
    return frozenset(
        (row["source_id"], row["candidates"][0])
        for row in hints
        if len(row["candidates"]) == 1
        and row["reason"] in (
            ("speaker_wording_eligibility_review_required", "ai_independent_review_required")
            if allow_ai_transations else ("speaker_wording_eligibility_review_required",))
        and row["source_id"] in source_units
        and (allow_ai_transations or not source_units[row["source_id"]].ai)
        and target_degree[row["candidates"][0]] == 1
    )


def one_to_one_hints(hints, source_units, inventory):
    return len(unique_one_to_one_hint_pairs(hints, source_units, inventory))


def import_summary(inventory, observations, policy, translations, hints, source_units,
                   auto_approved=0, changed=False, machine_targets=(), machine_candidate_count=None):
    """Summarize *actual current import references*, never candidate-only results."""
    total = len(inventory.targets)
    current = translations.page(observations, policy)
    imported_rows = [row for row in current["versions"] if row["imported"]]
    by_source = Counter()
    for row in imported_rows:
        if row["kind"] == "manual":
            by_source["manual"] += 1
            continue
        matches = translations.matching_observations(row, observations, policy)
        # Eligible rows may have multiple identical-text provenance providers:
        # use the currently configured order, not arbitrary dict ordering.
        providers = {m["provenance"][0]["provider"] for m in matches}
        provider = next((name for name in policy.sources if name in providers), None)
        if provider is None:
            raise ValueError("imported_version_missing_current_provider")
        by_source[provider] += 1
    verified_total = sum(by_source.values())
    machine_targets = set(machine_targets)
    human_targets = {row["target_id"] for row in imported_rows}
    if (verified_total != len(human_targets)
            or machine_targets & human_targets or not (machine_targets | human_targets)
            <= set(inventory.targets)):
        raise ValueError("invalid_import_coverage")
    by_source["classicua"] += len(machine_targets)
    imported_total = verified_total + len(machine_targets)
    if imported_total > total:
        raise ValueError("invalid_import_coverage")
    candidates = Counter(o.candidate.provider for o in observations)
    mapped = len({o.target_id for o in observations})
    rows = [{"source": name,
             "candidate_translations": candidates[name],
             "imported_translations": by_source[name],
             "machine_provisional_imports": len(machine_targets) if name == "classicua" else 0}
            for name in policy.sources if name != "original_english"]
    if by_source["manual"]:
        rows.append({"source": "manual", "candidate_translations": 0,
                     "imported_translations": by_source["manual"],
                     "machine_provisional_imports": 0})
    return {
        "schema_version": 1,
        "scope": "offline, inert local review import; NOT a WoW Community Pack",
        "total_spoken_records": total,
        "unreviewed_one_to_one_candidates": (
            one_to_one_hints(hints, source_units, inventory)
            if machine_candidate_count is None else machine_candidate_count),
        "verified_source_to_target_bindings": mapped,
        "auto_approved_now": auto_approved,
        "imported_total": imported_total,
        "human_reviewed_imported_total": verified_total,
        "machine_one_to_one_imported": len(machine_targets),
        "untranslated_total": total - imported_total,
        "coverage_percent": round(100 * imported_total / total, 2) if total else 0.0,
        "by_source": rows,
        "changed": changed,
        "activated": False,
        "saved_to_git": False,
    }


def format_import_table(report):
    """Stable human-readable console table, no source text or provenance."""
    headers = ("Джерело", "Кандидатів", "Імпортовано", "Із них машинні 1:1")
    rows = [(r["source"], str(r["candidate_translations"]),
             str(r["imported_translations"]),
             str(r.get("machine_provisional_imports", 0))) for r in report["by_source"]]
    widths = [max(len(str(value)) for value in [title] + [r[i] for r in rows])
              for i, title in enumerate(headers)]
    def line(items):
        return "| " + " | ".join(str(x).ljust(widths[i])
                                for i, x in enumerate(items)) + " |"
    sep = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    text = [
        "Підсумок імпорту Spoken Ukrainian (локальне сховище; без активації у WoW)",
        "Записів Spoken усього: " + str(report["total_spoken_records"]),
        "Можливих 1:1 зв'язків без підтвердження: " +
            str(report["unreviewed_one_to_one_candidates"]),
        "Підтверджених зв'язків з доступним перекладом: " +
            str(report["verified_source_to_target_bindings"]),
        "Автоматично схвалено за запуск: " + str(report["auto_approved_now"]),
        sep, line(headers), sep,
    ]
    text.extend(line(row) for row in rows)
    text.extend([sep,
                 "Імпортовано: " + str(report["imported_total"]),
                 "Машинні 1:1 без людського mapping review: " +
                     str(report.get("machine_one_to_one_imported", 0)),
                 "Без імпорту: " + str(report["untranslated_total"]),
                 "Покриття: " + str(report["coverage_percent"]) + "%",
                 "Вихід: приватний build/; не Git, не активний аддон",
                 "Машинні 1:1 є попередніми: потрібне незалежне mapping/content review перед паком."])
    return "\n".join(text)
