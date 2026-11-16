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
5. Check third-party rights, secrets, generated binaries, ignored `build/`/`dist/`, external writes, and unintended changes to pinned files.
6. Run relevant local tests when possible; if reviewing remotely, distinguish GitHub CI results from locally executed tests and state access limits.

## Report format
Start with findings ordered by severity (critical, high, medium, low). Each finding should contain:
- precise file and line reference;
- observable bug or risk and a realistic triggering scenario;
- smallest useful corrective direction.

Separate confirmed defects from hypotheses and from out-of-scope pre-existing issues. Avoid speculative style comments and duplicate findings. If no actionable findings, say so explicitly, then summarize residual risks, tests and limitations. Do not approve/merge a PR or modify code merely because a review was requested.
