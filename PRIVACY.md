# Privacy Policy

**AI Agents Usage Monitor** is a local desktop application that monitors your Claude and Codex usage.

## Data Collection

This application does **not** collect, store, or transmit any personal data.

## Network Communication

The application's own HTTP requests go to `api.anthropic.com` for Claude usage.
While the Codex view is open, it launches the installed native Codex CLI or IDE binary as an
app-server and requests account and quota information over local standard input/output.
Codex authenticates and communicates with OpenAI services using its own configuration.
Analytics and the OpenTelemetry exporter are disabled for this child process.
No prompts or model turns are submitted by the monitor.

## Credentials

The application reads your existing Claude OAuth token from the local Claude CLI configuration file
(`~/.claude/.credentials.json`). This token is:

- Used solely in HTTP Authorization headers to authenticate with the Anthropic API
- Never logged, stored elsewhere, copied, or transmitted to any third party

## Local Storage

The Codex view reads existing `sessions/**/*.jsonl` and `archived_sessions/**/*.jsonl` under
`CODEX_HOME` (or `~/.codex`). It retains only model names, timestamps and token counters in memory.
Local token records are not sent over the network. For account quota graphs, the monitor uses
Codex's `account/read` and `account/rateLimits/read` protocol methods. The monitor does not read
Codex credentials; Codex handles authentication. Email, plan and quota data remain in memory.

The monitor itself does not write files. The delegated Codex process may write its own logs,
databases or refreshed credentials under its configured home, as Codex normally does.
All usage data held by the monitor is kept in memory only and discarded when
the application closes. An optional settings file (`usage-monitor-settings.json`) is read-only.

Two values are written to the Windows registry, both under `HKEY_CURRENT_USER`:

- `Software\Classes\AppUserModelId\deuxdoom.UsageMonitorForClaude` - the display name and icon
  shown in the header of the application's notifications. Re-registered on every start.
- `Software\Microsoft\Windows\CurrentVersion\Run` - the autostart entry. Written only when you
  enable autostart from the tray menu, removed when you disable it again.

One key is deleted, once, on the first start of version 1.80.0:

- `Software\Classes\AppUserModelId\JensDuttke.UsageMonitorForClaude` - the notification identity used
  before the application was renamed. Nothing reads it any more, so it is removed rather than left
  behind. The deletion is attempted on every start and does nothing once the key is gone; a machine
  that refuses it is ignored and the application starts normally.

## Claude Code Installation

When the OAuth token has expired, the application runs `claude update` so that the Claude Code CLI
renews the token in its own credentials file. As a side effect of that command, a newer Claude Code
version may be installed. No other software on your system is modified.

## Third-Party Services

The application does not integrate with any analytics, tracking, advertising, or telemetry services.

## Contact

For questions about this privacy policy, please open an issue at
https://github.com/deuxdoom/usage-monitor-for-claude/issues
