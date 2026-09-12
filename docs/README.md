# Documentation

The app watches two agents, and it reads each of them the same way: a server source for the quota
percentages, a local source for the per-model token detail the server does not disclose, and the
installed CLI and IDE extensions for the version rows in the popup footer.

| What | Claude | Codex |
|---|---|---|
| Server quotas | `api.anthropic.com` OAuth endpoints - [reference](claude-api-reference.md) | Codex app-server protocol - [reference](codex-api-reference.md) |
| Local token detail | `~/.claude/projects/**/*.jsonl` transcripts | `$CODEX_HOME/sessions/**/*.jsonl` rollouts |
| Installed versions | Native CLI, IDE extensions, plus any `cli_command` entry | Native CLI, IDE extensions |
| Credentials read | `~/.claude/.credentials.json`, used only in Authorization headers | **None** - Codex authenticates itself |

The module names follow the same split: `claude_api.py` / `codex_api.py`, `claude_sessions.py` /
`codex_sessions.py`, `claude_cli.py` / `codex_cli.py`.

## Guides

| Document | What it covers |
|---|---|
| [configuration.md](configuration.md) | Settings-file locations, every key, and which menu and popup choices are saved automatically |
| [event-commands.md](event-commands.md) | Running your own command when a quota resets, a threshold is crossed, the app starts, or you double-click the tray icon |
| [automatic-update-check.md](automatic-update-check.md) | A worked example: a script that tells you when a new release is out |

## References

| Document | What it covers |
|---|---|
| [claude-api-reference.md](claude-api-reference.md) | Example responses from the Anthropic OAuth endpoints, with field names and types |
| [codex-api-reference.md](codex-api-reference.md) | The app-server protocol methods and the fields read from each, plus how local rollouts are summarised |

## Also at the repository root

- [README.md](../README.md) - what the app does and how to start it
- [PRIVACY.md](../PRIVACY.md) - every read, every network destination, saved settings, and registry changes
- [CHANGELOG.md](../CHANGELOG.md) - what changed in each release
