---
name: code-reviewer
description: Review Spoken Ukrainian code changes, commits, pull requests, tests, build tools, security and licensing boundaries. Use for review requests before merge or release, with prioritized actionable findings and verification evidence.
---

# Findings-first code review

Review the requested diff against its base (or changed files if no base is given). Stay read-only unless explicitly asked to fix issues.

## Procedure
1. Identify branch/base, exact changed files, relevant task scope, and touched contracts. Inspect nearby code and tests; do not judge only by a PR description.
2. Check correctness, security, failure modes, compatibility, determinism, provenance and test gaps. Focus on **newly introduced** issues.
3. For ClassicUA: verify restricted parsing, real load order, whole-row overrides, Gossip `!code`, sparse quest fields, faction precedence and no committed translations.
4. For Spoken: verify public pack format, real client locale, stable IDs, no fake audio and no unsupported claims of text-only behavior.
5. If provider/order/coverage code changes: verify config permutations, omitted/English-first/empty policies, first-real-candidate semantics in both single/batch APIs, mock non-consumption, UTF-8 digest checks, deterministic metadata-only totals, and absence of real translated bodies in reports. See `.agents/skills/translation-source-pipeline/SKILL.md`.
6. For canonical mapping code: verify source-file vs field fingerprints, independent review evidence, safe persistence and effective-change invalidation. See `.agents/skills/canonical-mapping-review/SKILL.md`.
7. Check third-party rights, secrets, generated binaries, ignored `build/`/`dist/`, external writes, and unintended changes to pinned files.
8. Run relevant local tests when possible; if reviewing remotely, distinguish GitHub CI results from locally executed tests and state access limits. Verify exact head SHA and its checks, not prior-success runs; resolve existing review threads only after confirming fixes and if authorized.

## Report format
Start with findings ordered by severity (critical, high, medium, low). Each finding should contain:
- precise file and line reference;
- observable bug or risk and a realistic triggering scenario;
- smallest useful corrective direction.

Separate confirmed defects from hypotheses and from out-of-scope pre-existing issues. Avoid speculative style comments and duplicate findings. If no actionable findings, say so explicitly, then summarize residual risks, tests and limitations. Do not approve/merge a PR or modify code merely because a review was requested.
