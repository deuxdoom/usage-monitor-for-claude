---
allowed-tools: Read, Edit, Bash, Grep, Glob
description: Add or refine a CHANGELOG.md entry for the current user-facing changes
---

Add the correct `CHANGELOG.md` entry (or entries) for the changes in this conversation. The **decision rule** for whether a change deserves an entry lives in `CLAUDE.md` - this command is the procedure for writing the entry once you know it belongs.

## Step 1: Decide whether an entry is warranted

- User-facing changes (new features, bug fixes, behavior changes, UI changes) **get** an entry.
- Internal refactors, code style changes, and documentation-only changes **do not** - unless they affect the user.
- Changes to `CLAUDE.md` and the command files are invisible to users - **never** mention them.

If nothing user-facing changed, say so and stop.

## Step 2: For a fix, verify the bug shipped

Entries describe changes **relative to the latest release tag**, not intermediate commits.

- Before writing a **fix** entry, run `git log` (and compare against the latest `vX.Y.Z` tag) to confirm the bug existed in the latest release.
- If the bug was introduced **and** fixed within the current unreleased period, it gets **no** entry - the user never saw it.

## Step 3: Write the entry

- Add it under the `## [Unreleased]` section, grouped by: **Added**, **Changed**, **Fixed**, **Removed** (create the subheading only if it does not exist yet).
- Write from the **user's perspective** - what changed and why it matters, not how the code changed.
- One bullet per logical change; keep it to a single concise sentence.
- When a change implements a GitHub Discussion or resolves a GitHub Issue, link it in the entry text, e.g.
  `- [Feature name](https://github.com/deuxdoom/usage-monitor-for-claude/discussions/12) - description`

## Step 4: Confirm

Show the added entry (or entries) and which group each landed in. Do not commit - suggest `/commit-message` when ready.
