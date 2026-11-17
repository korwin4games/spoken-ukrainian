"""Metadata-only, deterministic coverage report for an inert local translation import.

Counts every canonical Spoken target, including families not yet supported by
the Quest review bridge. Never leaks original text, translation bodies or
reviewer identifiers.
"""
from collections import Counter



def unique_one_to_one_hint_pairs(hints, source_units, inventory):
    """Conservative exact-cardinality Quest hints, NOT approved mappings.

    The reverse degree counts *all* source candidates (including excluded AI
    and ambiguous sources). Two factions or voice variants sharing a target
    therefore never qualify through partial filtering.
    """
    target_degree = Counter(target for row in hints for target in set(row["candidates"])
                            if target in inventory.targets)
    return frozenset(
        (row["source_id"], row["candidates"][0])
        for row in hints
        if len(row["candidates"]) == 1
        and row["reason"] == "speaker_wording_eligibility_review_required"
        and row["source_id"] in source_units
        and not source_units[row["source_id"]].ai
        and target_degree[row["candidates"][0]] == 1
    )


def one_to_one_hints(hints, source_units, inventory):
    return len(unique_one_to_one_hint_pairs(hints, source_units, inventory))


def import_summary(inventory, observations, policy, translations, hints, source_units,
                   auto_approved=0, changed=False):
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
    imported_total = sum(by_source.values())
    if imported_total != len({row["target_id"] for row in imported_rows}) or imported_total > total:
        raise ValueError("invalid_import_coverage")
    candidates = Counter(o.candidate.provider for o in observations)
    mapped = len({o.target_id for o in observations})
    rows = [{"source": name,
             "candidate_translations": candidates[name],
             "imported_translations": by_source[name]}
            for name in policy.sources if name != "original_english"]
    if by_source["manual"]:
        rows.append({"source": "manual", "candidate_translations": 0,
                     "imported_translations": by_source["manual"]})
    return {
        "schema_version": 1,
        "scope": "offline, inert local review import; NOT a WoW Community Pack",
        "total_spoken_records": total,
        "unreviewed_one_to_one_candidates": one_to_one_hints(hints, source_units, inventory),
        "verified_source_to_target_bindings": mapped,
        "auto_approved_now": auto_approved,
        "imported_total": imported_total,
        "untranslated_total": total - imported_total,
        "coverage_percent": round(100 * imported_total / total, 2) if total else 0.0,
        "by_source": rows,
        "changed": changed,
        "activated": False,
        "saved_to_git": False,
    }


def format_import_table(report):
    """Stable human-readable console table, no source text or provenance."""
    headers = ("Джерело", "Кандидатів", "Імпортовано")
    rows = [(r["source"], str(r["candidate_translations"]),
             str(r["imported_translations"])) for r in report["by_source"]]
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
                 "Без імпорту: " + str(report["untranslated_total"]),
                 "Покриття: " + str(report["coverage_percent"]) + "%",
                 "Вихід: приватний build/; не Git, не активний аддон"])
    return "\n".join(text)
