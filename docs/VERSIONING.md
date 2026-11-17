# Project versioning

`VERSION` is the authoritative project version. Since adding uv, the `pyproject.toml` `[project].version` and virtual project record in `uv.lock` must mirror `VERSION`; `uv run --locked python tools/version.py check` validates all three. On a version bump, edit `pyproject.toml` to the same version and run `uv lock` before the locked check. uv metadata are mirrors, never independent sources of truth. Read it with `uv run --locked python tools/version.py show`; do not maintain a second project-version constant. The initial baseline is 0.0.1, established after Stage 2A was merged into main in PR #1. This is a version assignment, not a claim that a tag or GitHub Release already exists.

## Format and validation

The project uses the numeric SemVer core `MAJOR.MINOR.PATCH`. Components are nonnegative ASCII integers without leading zeros. Prerelease/build suffixes are not used by this lightweight policy. The VERSION file contains just the triplet and normally one final LF. A missing final LF is accepted and preserved on bump; spaces, CRLF, extra blank lines, a BOM and malformed values are rejected.

```sh
uv run --locked python tools/version.py show
uv run --locked python tools/version.py check
uv run --locked python tools/version.py check --tag v0.0.1
```

`show` validates VERSION. `check` additionally requires an Unreleased changelog section first, dated version sections with real ISO dates in unique descending version order, and the newest dated section matching VERSION. `--tag` requires an exact `v` plus VERSION match. This catches inconsistent release preparation; it does not infer release approval from a version number.

## Bump policy

| Component | Use | Examples |
| --- | --- | --- |
| PATCH | Bug fixes, small compatibility/internal corrections, security fixes without a public-interface break | 0.0.1 → 0.0.2; 0.1.0 → 0.1.1; 1.0.0 → 1.0.1 |
| MINOR | New functionality/adapters/modules and backward-compatible improvements | 0.0.2 → 0.1.0; 0.1.2 → 0.2.0; 1.2.3 → 1.3.0 |
| MAJOR | First explicitly approved stable release, then breaking public-interface changes | Approved development version → 1.0.0; 1.2.3 → 2.0.0 |

Minor resets PATCH; major resets MINOR and PATCH. During 0.x development, breaking changes may increment MINOR and must be explicitly labeled **BREAKING** in the changelog. A feature addition still uses MINOR during 0.x; an internal correction uses PATCH. After 1.0.0, breaking public-interface changes use MAJOR.

Pre-1.0 `bump major` fails even in dry-run mode unless `--approve-stable` is supplied. That flag records an explicit operator decision after obtaining stable-release approval; the tool cannot determine who approved it. It must not be added to routine CI or used to bypass review.

```sh
uv run --locked python tools/version.py bump minor --dry-run
# Only after explicit stable-release approval:
uv run --locked python tools/version.py bump major --approve-stable --dry-run
```

No arbitrary set-version command is offered. Every supported bump increases the current parsed version, preventing downgrades through the tool. Manual edits and Git history remain subject to review; the tool does not audit remote release history or prevent every possible manual downgrade.

## Changelog and release preparation

`CHANGELOG.md` follows Keep a Changelog headings, with Unreleased above dated version sections and Added, Changed, Fixed (and other applicable categories) beneath them. Record changes under Unreleased while developing. Do not rewrite previously released sections. This initial baseline includes Stages 0, 1 and merged 2A; it does not imply a ClassicUA text-release grant.

A bump writes only VERSION. It never silently moves Unreleased entries or changes a historical heading. At release preparation, move the applicable Unreleased notes into a new dated section for the proposed version, retaining the empty Unreleased heading and all historical sections. Until that section and VERSION agree, `check` intentionally fails with an explanation. Prepare and commit the pair together.

Example patch preparation, with changelog editing performed manually between the bump and validation:

```sh
uv run --locked python tools/version.py show
uv run --locked python tools/version.py bump patch --dry-run
uv run --locked python tools/version.py bump patch
# Add a NEW dated section for the displayed version; move its Unreleased notes there.
uv run --locked python tools/version.py check
uv run --locked python tools/build.py
uv run --locked python -m unittest discover -s tests -v
```

Dry-run prints only the proposed version and changes no files. Mutation tests use temporary project roots. The tool does not run Git, enforce a clean working tree or mutate other files; preserve unrelated work and review VERSION/changelog together before committing. Run with ordinary write access to the repository. If VERSION is a symlink, replace it deliberately with a regular project file before updating; the tool refuses to follow it for a bump.

## Git tags and GitHub Releases

After implementing changes, running tests, preparing the changelog, bumping VERSION and obtaining review, commit the changes explicitly. Create an annotated `v<project-version>` tag on the reviewed commit, then push the reviewed branch and tag explicitly. Never move an existing version tag or rewrite published history.

For the first future baseline tag, after this versioning work has been reviewed and committed with VERSION still 0.0.1:

```sh
uv run --locked python tools/version.py check --tag v0.0.1
uv run --locked python tools/build.py
uv run --locked python -m unittest discover -s tests -v
# Commit reviewed changes separately if they are not committed yet.
git tag -a v0.0.1 -m "Spoken Ukrainian v0.0.1"
# Only after review and explicit authorization:
git push origin main
git push origin v0.0.1
```

These are future manual instructions, not operations performed by the CLI or this task. If VERSION has changed before tagging, use its current value instead. No tags currently exist at introduction of versioning.

A Git tag names a source commit. A GitHub Release is an optional published description/assets attached to a tag. A future project release should identify the matching project tag; its release title can differ. A tag or GitHub Release is never created by `show`, `check`, `bump` or CI. Future release publication requires a separate task, successful checks and all relevant content permissions.

## Project and addon versions are separate

| Version | Authority and meaning |
| --- | --- |
| Project | Root VERSION; source/tooling evolution under this policy |
| Individual addon | Its TOC/pack contract; diagnostic remains 0.1.0 |
| Git tag | Annotated reference to a reviewed project commit, convention `v<project-version>` |
| GitHub Release | Optional publication attached to a tag; not implied by a changelog heading |

Future distributable addons may have independent version schedules. Project bumps do not change addon TOCs, filenames, ZIP format or source-provenance hashes. The existing diagnostic builder and metadata tests continue to validate addon version 0.1.0. Upstream version fields in `sources.lock.json` describe pinned dependencies and are not project-version duplicates. Do not automatically replace any of these values with VERSION.

## CI

The existing workflow still runs build and all tests. It additionally runs `uv run --locked python tools/version.py check` and validates `v*` tags against VERSION using `--tag`. Its unrestricted push trigger already includes tag pushes. Tag names enter the shell through an environment variable, not interpolated shell code. Other tags are not project version tags. No release, artifact publication or automatic bump is configured.

The normal unittest discovery includes version-tool tests along with all Stage 1 and Stage 2A regressions. A remote CI run for this branch remains pending until a separately authorized push.
