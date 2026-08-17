---
allowed-tools: Read, Edit, Bash, Grep, Glob
description: Cut a new release - bump the version, roll the changelog, and prepare the GitHub release notes
---

Prepare a release for version **$ARGUMENTS** (a semantic version like `1.21.0`). If no version was given, ask for it before doing anything.

Work through the steps **sequentially**. Respect the project git rule: **never commit, tag, or push** - this command edits files and hands the final publish command back to the user to run.

## Step 1: Bump the version

Set the new version in **both** places (all fields must match exactly):

- `usage_monitor_for_claude/__init__.py` - `__version__`
- `version_info.py` - all four fields: `filevers`, `prodvers`, `FileVersion`, `ProductVersion`

`filevers`/`prodvers` are tuples (e.g. `(1, 21, 0, 0)`); `FileVersion`/`ProductVersion` are strings (e.g. `'1.21.0.0'`). Read both files first to match their existing shape, then edit.

## Step 2: Roll the changelog

In `CHANGELOG.md`:

- Rename `## [Unreleased]` to `## [x.y.z] - YYYY-MM-DD` (today's date).
- Add a fresh, empty `## [Unreleased]` section **above** it.
- Update the compare links at the bottom: the `[Unreleased]` link now compares `vX.Y.Z...HEAD`, and add a new `[x.y.z]` link comparing the previous tag to `vX.Y.Z`.

Do not invent entries - the section must already hold the changes accumulated during the unreleased period. If it is empty or looks incomplete, stop and tell the user; use `/changelog` to add entries first.

## Step 3: Run the tests

Activate the virtual environment, then run `python -m unittest discover -s tests` and confirm everything passes. If anything fails, stop and report - do not proceed to a release with failing tests.

## Step 4: Prepare (do not run) the GitHub release command

The release publishes a tag, which the git rule forbids this command from doing. Instead, **output** the exact command for the user to run themselves.

- The notes must use the **exact** content from the new version's `CHANGELOG.md` section (the `### Added` / `### Changed` / `### Fixed` / `### Removed` blocks), followed by:
  - a `[Full changelog](<compare-url>)` link, and
  - a `[README for this version](https://github.com/deuxdoom/usage-monitor-for-claude/blob/vX.Y.Z/README.md)` link.
- The build artifact `dist/UsageMonitorForClaude.exe` is produced by the user's build step - note it as a prerequisite; do not attempt to build it here.

Present the command in this shape (filled in with the real version and notes):

```
gh release create vX.Y.Z dist/UsageMonitorForClaude.exe --title "vX.Y.Z" --notes "<changelog section + links>"
```

## Summary

Report:
1. Which files were edited and the old -> new version.
2. Confirmation that the changelog was rolled and the compare links updated.
3. Test result.
4. The ready-to-run `gh release create` command.

Do not commit the version bump - suggest running `/commit-message` for it, and remind the user that the `gh release create` command is theirs to run once the EXE is built.
