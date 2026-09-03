---
allowed-tools: Read, Edit, Bash, Grep, Glob
description: Cut a new release - verify the version, roll the changelog, and prepare the GitHub release notes
---

Prepare a release for version **$ARGUMENTS** (a semantic version like `1.21.0`). If no version was given, ask for it before doing anything.

Work through the steps **sequentially**. Respect the project git rule: **never commit, tag, or push** - this command edits files and hands the final publish command back to the user to run.

## Step 1: Verify the version is already set

The version is **not** bumped here. It was set when the pending changelog heading was opened, so by now `__version__` in `usage_monitor_for_claude/__init__.py`, all four `version_info.py` fields and the newest `CHANGELOG.md` heading already name **$ARGUMENTS**.

Confirm that by running `python -c "import build; print(build.check_versions())"`. It prints the agreed version, or names every disagreeing source and exits non-zero.

- If it prints **$ARGUMENTS**, move on.
- If it reports a mismatch, fix the sources it names so they all state **$ARGUMENTS**, then re-run it.
- If it prints a *different* version than the one requested, stop and ask: the release being prepared is not the one the user named, and silently renaming it would misfile the accumulated changelog entries.

## Step 2: Roll the changelog

In `CHANGELOG.md`:

- Replace the pending marker on `## [x.y.z] - 배포 예정` with today's date: `## [x.y.z] - YYYY-MM-DD`.
- Do **not** open a new pending heading here - the next one is created by `/changelog` together with its version bump, when the first entry of the next cycle is written.
- Update the compare link at the bottom of the section to compare the previous tag to `vX.Y.Z`.

Do not invent entries - the section must already hold the changes accumulated during the pending period. If it is empty or looks incomplete, stop and tell the user; use `/changelog` to add entries first.

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
1. The verified version and the sources that agree on it.
2. Confirmation that the changelog was rolled and the compare link updated.
3. Test result.
4. The ready-to-run `gh release create` command.

Do not commit - suggest running `/commit-message`, and remind the user that the `gh release create` command is theirs to run once the EXE is built.
