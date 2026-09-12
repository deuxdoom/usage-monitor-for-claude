"""
AI Agents Usage Monitor
================

Displays the current Claude.ai usage as a system tray icon.
Left-click the icon to see a detailed usage popup, whose header switches
between the Claude view and a Codex view of the same shape.

Authenticates via Claude Code OAuth token from the Claude config
directory (requires Claude Code login).  Respects ``CLAUDE_CONFIG_DIR``
if set, otherwise defaults to ``~/.claude/``.  The Codex view delegates its
account and quota reads to the installed Codex app-server, which owns its
own authentication.
"""
from __future__ import annotations

__version__ = '2.1.0'
