# Privacy Policy

**Usage Monitor for Claude** is a local desktop application that monitors your Claude API usage.

## Data Collection

This application does **not** collect, store, or transmit any personal data.

## Network Communication

The application communicates exclusively with `api.anthropic.com` to retrieve your current API usage
data. No other network connections are made.

## Credentials

The application reads your existing Claude OAuth token from the local Claude CLI configuration file
(`~/.claude/.credentials.json`). This token is:

- Used solely in HTTP Authorization headers to authenticate with the Anthropic API
- Never logged, stored elsewhere, copied, or transmitted to any third party

## Local Storage

The application does not write any files. All usage data is kept in memory only and discarded when
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
