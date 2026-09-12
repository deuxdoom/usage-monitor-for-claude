---
allowed-tools: Read, Edit, Bash, Grep, Glob, Agent
description: Critical review of all staged changes, documentation updates, and final cleanup
---

Perform a systematic quality review of all staged changes. Work through the following steps **sequentially**. Use the full context of this conversation to understand WHY the changes were made.

## Step 1: Critical Code Review

Run `git diff --staged` and critically review EVERY changed file:

### Correctness & Logic
- Are all changes meaningful and actually necessary for the intended implementation?
- Off-by-one errors, boundary conditions, edge cases (empty inputs, None values, zero-length collections)?
- State management - can objects be left in invalid states?
- Order dependencies - do operations assume a specific sequence without enforcing it?

### Code Quality
- Can existing code be simplified or removed as a result of these changes (dead code, duplicates)?
- Is there optimization potential (performance, readability, maintainability)?
- Are naming conventions and code style consistent with CLAUDE.md rules?
- When a comment is corrected because the described behavior changed, check immediately whether the same outdated concept is also encoded in nearby variable, parameter, or function names - and rename them too.
- No ambiguous names like `other`, `data2`, `flag` - every name must be immediately clear.

### Security (especially for changes touching `api.py`)
- No credentials in logs, error messages, or anywhere outside HTTP Authorization headers.
- All URLs and API endpoints are top-level constants - no dynamic URL construction.
- No `eval()`, `exec()`, `compile()`, or dynamic imports.
- File writes stay in `settings_store.py`, limited to the four stored choices and same-directory temporary replacement files; preserve other keys and never overwrite an unreadable or malformed settings file. Check README.md and PRIVACY.md against the actual write scope.
- No obfuscation, no base64-encoded strings, no encoded URLs or tokens.
- Network communication exclusively with `api.anthropic.com`.

### Concurrency & Resource Management
- Race conditions in threading code (check-then-act patterns, shared mutable state)?
- Proper cleanup of resources in error paths (context managers, finally blocks)?
- Timeout handling on blocking operations?

### Error Handling & Resilience
- Proper input validation at function boundaries?
- Early returns and guard clauses used consistently?
- Error messages provide enough context for debugging without leaking sensitive data?

### Type Safety & Imports
- `from __future__ import annotations` present as first import (after module docstring)?
- Type hints in function signatures (not in docstrings)?
- Import grouping correct (stdlib / third-party / local), relative imports within the package?
- No circular dependencies, no unused imports?

### Style & Formatting (per CLAUDE.md)
- Single quotes default, double when containing singles, triple-double for docstrings?
- Hyphens for dashes in text, never em dashes or en dashes?
- PEP8-based with 140-160 char line length?
- No deep indentation aligning with opening brackets?
- `# type: ignore` only with specific error code and short reason?

Summarize your findings before moving to the next step.

## Step 2: Documentation Updates

> Note: do NOT check `CHANGELOG.md` and do NOT flag a missing changelog entry - it is handled outside `/review`.

### README.md
- If features were added, changed, or removed: is README.md updated to reflect this?
- Is the feature list accurate? Are descriptions still correct?
- If locale files changed: is the language list in sync?

### docs/configuration.md
- If settings were added, changed, or removed: is `docs/configuration.md` updated?
- If locale files changed: is the language list in the `language` setting description still in sync?

### CLAUDE.md
- Does CLAUDE.md need updates based on insights from this conversation?
- New conventions or patterns established?
- Changed project structure or dependencies?
- Important architectural decisions made?

Apply necessary changes directly.

## Step 3: Test Coverage Check

Review test coverage for the staged changes:

- Does every new function or changed behavior have corresponding tests in `tests/`?
- Are edge cases covered (boundary values, empty/missing data, concurrent events)?
- Are error paths tested, not just the happy path?
- Do existing tests still match the changed behavior, or do they need updating?
- Run `python -m unittest discover -s tests` to verify all tests pass.

If tests are missing or failing, fix them directly.

## Step 4: Final Cleanup

Run `git diff --staged` again and review ALL staged files one last time:

- Is ONLY code present/changed that is actually necessary for the intended implementation?
- No accidental debug logs, `print()` statements, commented-out code blocks, or leftover TODO comments?
- No unintended formatting or whitespace-only changes?
- No changes to files unrelated to the current feature?
- No `# type: ignore` without specific error code?
- No docstrings or comments mentioning "changes", "improvements", or "type hints"?

If you find issues in this step, fix them directly.

## Summary

Provide a brief summary:
1. What was reviewed
2. Which issues were found and fixed
3. Which documentation was updated
4. Whether the staged changes are now ready to commit

Do NOT commit directly. If the changes are ready, run the `/commit-message` slash command to generate a properly formatted commit message.
