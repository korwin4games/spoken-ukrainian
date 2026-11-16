"""Inventory templates without expanding or rewriting their source syntax."""
from dataclasses import dataclass

CASES = frozenset({"н", "р", "д", "з", "о", "м", "к"})


@dataclass(frozen=True)
class Finding:
    syntax: str
    category: str
    status: str
    line_offset: int
    detail: str = ""


def inventory(text):
    findings, stack = [], []
    for position, char in enumerate(text):
        if char == "{":
            stack.append(position)
        elif char == "}":
            if not stack:
                findings.append(Finding("}", "malformed", "problematic", text[:position].count("\n"), "unmatched_close"))
                continue
            start = stack.pop()
            syntax = text[start:position + 1]
            parts = syntax[1:-1].split(":")
            name = parts[0].lower()
            category, status, detail = "unknown", "unknown", "unrecognized_template"
            if "{" in syntax[1:] or stack:
                category, status, detail = "nested", "problematic", "nested_braces"
            elif name in {"ім'я", "клас", "раса"}:
                category = {"ім'я": "player_name", "клас": "player_class", "раса": "player_race"}[name]
                status = "supported" if len(parts) == 1 or (len(parts) == 2 and parts[1] in CASES) else "unknown"
                detail = "player_dependent" if status == "supported" else "unsupported_case_or_arity"
            elif name == "стать":
                category = "player_gender"
                status = "supported" if len(parts) == 3 and parts[1] and parts[2] else "problematic"
                detail = "player_dependent" if status == "supported" else "gender_branch_arity_or_empty"
            elif len(parts) == 1 and name.isascii() and name.isdigit() and int(name) > 0:
                category, status, detail = "numeric_capture", "problematic", "requires_original_text_capture_context"
            findings.append(Finding(syntax, category, status, text[:start].count("\n"), detail))
    for start in stack:
        findings.append(Finding("{", "malformed", "problematic", text[:start].count("\n"), "unmatched_open"))
    return findings
