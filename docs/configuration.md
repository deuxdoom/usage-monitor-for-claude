# Configuration

All settings work out of the box - no configuration file needs to be created by hand. The app saves menu and popup choices in `config.json`. To customize other settings, edit that file or create one containing only the keys you want to change:

```json
{
  "poll_interval": 300,
  "bar_fg": "#00cc66",
  "bar_fg_warn": "#ff6600"
}
```

The app searches these directories in order (first file found wins):

1. **`$CLAUDE_CONFIG_DIR/`** (only if a custom config directory is set via `--config-dir` or `CLAUDE_CONFIG_DIR` and differs from `~/.claude/`) - this lets every instance have its own settings when running one instance per Claude account
2. **Next to the EXE** (or project root when running from source)
3. **`~/.claude/`**

Within each directory, `config.json` is checked before the legacy `usage-monitor-settings.json`. Directory priority comes first: a legacy file in an earlier directory takes precedence over a new-name file in a later one. Existing files do not need to be renamed, and files are not merged.

The app saves only `tray_provider`, `poll_interval`, `popup_font` and `popup_view`, preserving the values of every other key. It updates the file read at startup, including a legacy-name file. If none was read, it creates `config.json` in the first directory above. If writing there fails, it tries `~/.claude/config.json`. Required directories may be created. Saving uses a temporary file in the same directory followed by an atomic replacement; JSON whitespace may change.

An existing file that cannot be read or parsed as a JSON object is left untouched. Empty files are treated as empty settings. If saving fails, the choice still applies to the running app but may not survive a restart. A higher-priority existing file still takes precedence over a fallback file at the next start.

Menu and popup choices apply immediately. Settings edited by hand are read at startup - after editing the file, quit from the tray context menu and start the app again to apply changes.

## Alert thresholds

Configure usage percentage thresholds that trigger Windows notifications. Session and weekly quotas have separate thresholds since their time horizons differ significantly. Set to an empty array `[]` to disable alerts for a specific quota type.

| Key | Default | Description |
|-----|---------|-------------|
| `alert_thresholds_five_hour` | `[50, 80, 95]` | Thresholds (%) for Session (5hr) |
| `alert_thresholds_seven_day` | `[95]` | Thresholds (%) for Weekly quotas (7 day and all variants) |
| `alert_thresholds_extra_usage` | `[50, 80, 95]` | Thresholds (%) for Extra Usage (paid overage) |
| `alert_extra_usage_spent` | `[]` | Absolute Extra Usage spending amounts (in your billing currency, e.g. `[50, 100, 150]` for dollars) that trigger a notification - the only alert that works when extra usage has no monthly limit |
| `alert_time_aware` | `true` | Only alert when usage outpaces elapsed time |
| `alert_time_aware_below` | `90` | Time-aware check applies only to thresholds below this value; thresholds at or above always fire |

Threshold lookup uses a fallback chain: exact match (e.g. `alert_thresholds_seven_day_opus`), then base period (e.g. `alert_thresholds_seven_day`), then no alerts. This lets you configure stricter thresholds per variant when needed:

```json
{
    "alert_thresholds_seven_day_opus": [50, 80, 95]
}
```

## Update notification

When a background token refresh installs a new Claude CLI version, the app shows a Windows notification reporting the version change. Set this to `false` to suppress that notification.

| Key | Default | Description |
|-----|---------|-------------|
| `notify_claude_update` | `true` | Show a notification when a background token refresh installs a new Claude CLI version |

## Claude CLI command

The popup lists the Claude Code version of the native Windows CLI and of each IDE extension it finds. Installs it cannot see - most commonly a Claude Code running inside WSL - are missing from that list. Use `cli_command` to have their versions reported as well.

The value is an object mapping a display name to the base command as an array of arguments (the app appends `--version` itself). Each entry is listed in the popup under the name you give it, **in addition to** the native CLI and the IDE extensions, which keep working exactly as before.

| Key | Default | Description |
|-----|---------|-------------|
| `cli_command` | *(none)* | Object mapping a display name to a base command (array of strings) whose Claude Code version is reported alongside the auto-detected ones, e.g. a WSL install |

```json
{
    "cli_command": {
        "WSL": ["wsl", "/home/<user>/.local/bin/claude"]
    }
}
```

An entry only appears once its command reports a version, so if it stays missing, run the command yourself in a terminal - `wsl /home/<user>/.local/bin/claude --version` has to print a version number.

Two things worth knowing:

- **This setting is display only.** It reports a version and nothing else. Automatic token refresh keeps using the native Windows CLI, because that is the install whose credentials this app reads - a Claude Code inside WSL keeps its own credentials there.
- **The version is read once per app start.** A custom command has no local file whose timestamp could reveal an update, and re-running it on every refresh would start WSL every few minutes. After updating Claude Code inside WSL, restart the app to see the new version.

## Tooltip fields

The tray tooltip shows a quick usage summary when you hover over the icon. By default, it displays the session (5h) and weekly (7d) quotas. Use `tooltip_fields` to choose which usage fields appear in the tooltip.

| Key | Default | Description |
|-----|---------|-------------|
| `tooltip_fields` | `["five_hour", "seven_day"]` | Which usage fields to show in the tray tooltip, in order |

Must be an array of non-empty strings. Duplicates are silently removed. An empty array `[]` is valid (tooltip shows only the title, no usage fields). Unknown field names are accepted - if a field is `null` or missing from the API response, it is simply skipped.

**Known field names:** `five_hour`, `seven_day`, `seven_day_sonnet`, `seven_day_opus`, `seven_day_cowork`, `seven_day_oauth_apps`

**Example** - show session and Sonnet quota in the tooltip:

```json
{
    "tooltip_fields": ["five_hour", "seven_day_sonnet"]
}
```

## Popup fields

The popup shows usage bars for all active quota types by default. Use `popup_fields` to control which bars appear and in what order.

| Key | Default | Description |
|-----|---------|-------------|
| `popup_fields` | `["*"]` | Which usage fields to show in the popup, in order. `"*"` is a wildcard meaning "all remaining non-null fields in default order" |

Must be an array of non-empty strings. `"*"` may appear at most once. Duplicates are silently removed. Unknown field names are accepted - if a field is `null` or missing from the API response, it is simply skipped.

**Known field names:** `five_hour`, `seven_day`, `seven_day_sonnet`, `seven_day_opus`, `seven_day_cowork`, `seven_day_oauth_apps`

**Default order** (used for `"*"` and when no setting is present): shorter periods first (`hour` before `day`), base field before variants, variants alphabetically.

**Examples:**

| Setting | Result |
|---------|--------|
| *(not set)* | All non-null fields in default order |
| `["five_hour", "seven_day_sonnet", "*"]` | Session first, then Sonnet, then all remaining |
| `["five_hour", "seven_day"]` | Only these two, everything else hidden |
| `["*"]` | Same as not set |

```json
{
    "popup_fields": ["five_hour", "seven_day_sonnet", "*"]
}
```

## Hidden popup fields

The usage API can expose quota types you have no interest in - for example a limit scoped to a model you never use, which the `"*"` wildcard picks up automatically and shows as a permanently empty bar. `popup_hide_fields` removes those bars without giving up the wildcard.

| Key | Default | Description |
|-----|---------|-------------|
| `popup_hide_fields` | `["nimbus_quill"]` | Usage fields never shown in the popup, matched by field name or by the label the popup displays |
| `popup_hide_inactive` | `true` | Drop quotas that have never been used - no reset window and 0% consumed - from the `"*"` wildcard |

Must be an array of non-empty strings. Each entry is matched case-insensitively against the field name (`nimbus_quill`), against its variant suffix so a bare model name also matches the period-prefixed form (`nimbus_quill` matches `seven_day_nimbus_quill`), and against the label shown in the popup (`Nimbus Quill`). Spaces, hyphens and underscores are interchangeable, so you can copy the text straight out of the popup. Matching is whole-token: `nimbus` does **not** match `nimbus_quill`.

This takes precedence over [`popup_fields`](#popup-fields) - a hidden field stays hidden even when listed there explicitly. It affects the popup only; the tray icon bars ([`icon_fields`](#tray-icon-bars)) and the tooltip ([`tooltip_fields`](#tooltip-fields)) are unaffected.

`popup_hide_inactive` works the other way round: it is an automatic tidy-up of the wildcard, so naming such a field in `popup_fields` still shows it. A quota that has just reset is at 0% but still has a reset window, so it is never treated as inactive.

**Both defaults differ from upstream.** Upstream shows every quota the API reports, including ones with no reset window, so a limit is visible before it is first used. This fork hides them, because the API currently reports `nimbus_quill` as a permanently empty bar. To get the upstream behavior back:

```json
{
    "popup_hide_fields": [],
    "popup_hide_inactive": false
}
```

Note that setting `popup_hide_fields` yourself **replaces** the default rather than adding to it - list `"nimbus_quill"` alongside your own entries if you want it to stay hidden.

```json
{
    "popup_hide_fields": ["nimbus_quill", "Some Other Quota"]
}
```

## Session detail

Clicking the session (5hr) or weekly (7 day) bar expands a panel with the exact token and message counts for that period, and a per-model breakdown. The usage API itself only reports a percentage - it does not disclose token counts or which models were used - so this reads the numbers straight out of Claude Code's own session transcripts (`<config dir>/projects/**/*.jsonl`), the same files Claude Code itself writes as you work. Nothing beyond the existing `/api/oauth/usage` call leaves the machine; the transcripts never do.

**These transcripts cover Claude Code only.** The quota percentage on the bar is account-wide - claude.ai in the browser, the desktop app, and Claude Code all draw from it - but only Claude Code writes a local record. A period you spent on claude.ai therefore shows a high percentage with no local tokens to report, and the panel says so rather than claiming zero usage. The panel repeats this caveat as a footnote every time it opens.

The window scanned matches the bar's own period: for a bar with a reset time, `[reset time − period, reset time)`; for one that has not reset yet in this account (see [Hidden popup fields](#hidden-popup-fields) above), the last *period* ending now. Retried or resumed turns that appear twice in a transcript are only counted once.

An **estimated total** is shown alongside the token count once the bar's utilization is at least 1% - calculated as `tokens ÷ (utilization ÷ 100)`. This is an extrapolation from the API's own reported percentage, not a guess at Anthropic's actual limit; the two can disagree slightly, since the transcripts and the API's internal accounting may not measure tokens identically. Below 1% the division amplifies noise into a meaningless number, so no estimate is shown.

There is no setting to turn this off - it reads local files only when the panel is clicked, so it costs nothing until asked for. Only `five_hour` and `seven_day` support it; a model-scoped or unlabeled quota (`seven_day_opus`, `nimbus_quill`, ...) has no local-log equivalent, and its bar is not clickable.

## Popup font and view

| Key | Default | Description |
|-----|---------|-------------|
| `popup_font` | `"system"` | Detail popup typeface: `"system"` (sans-serif) or `"pixel"` (bundled Galmuri11). The tray menu's "Popup font" selection applies to an open popup and is saved. Bar mode always uses the system font for legibility; an older `"mono"` value falls back to `"system"` |
| `popup_view` | `"detail"` | Popup view: `"detail"` or `"bar"`. The popup's view buttons save this choice. The bar stays open without pinning, can be dragged by its clock, and has detail-view and close buttons |

## Popup position

The popup is anchored to the corner nearest the tray, staying clear of both the monitor work area edge and the taskbar window's own rectangle - whichever is stricter. The second bound covers an auto-hiding taskbar, which Windows does not subtract from the work area at all. A third-party bar drawn as its own window is still not accounted for; `popup_margin` widens the gap for that case.

| Key | Default | Description |
|-----|---------|-------------|
| `popup_margin` | `12` | Gap in physical pixels between the popup and the work-area edge it is anchored to |

Must be an integer of 0 or more. The value is in physical pixels and is not DPI-scaled, so on a 150% display a margin of `75` is roughly 50 logical pixels.

```json
{
    "popup_margin": 75
}
```

## Compact pinned view

The detail popup can be pinned open (pin button in the header) so it stays visible and can be dragged anywhere. Use `compact_hide` to strip the pinned popup down to just the usage bars you care about - the entries listed here are hidden **only while the popup is pinned**, and reappear when you unpin it.

| Key | Default | Description |
|-----|---------|-------------|
| `compact_hide` | `[]` | Sections and usage bars to hide while the popup is pinned |

Must be an array of non-empty strings. Duplicates are silently removed. Unknown names are accepted and simply have no effect. With the default empty list, pinning changes nothing about what is shown.

Entries can be either a **section key** or a **usage field name**:

**Section keys:** `account` (email and plan), `extra_usage` (paid overage bar), `claude_code` (installed versions), `status` (the footer with the update time). The usage bar section itself cannot be hidden as a whole - hide individual bars by their field name instead. When hiding leaves only the usage bars (no other section visible), the "Usage" heading is dropped automatically, since it has nothing left to distinguish the bars from.

**Usage field names:** any quota field, e.g. `five_hour`, `seven_day`, `seven_day_sonnet`, `seven_day_opus`, `seven_day_cowork`, `seven_day_oauth_apps`. This hides that single bar in the pinned view, independent of [`popup_fields`](#popup-fields) (which controls the normal, unpinned popup).

**Example** - pin to a minimal view with only the session and weekly bars:

```json
{
    "compact_hide": ["account", "extra_usage", "claude_code", "status", "seven_day_sonnet", "seven_day_opus"]
}
```

## Tray icon bars

The tray icon displays two small progress bars. By default, these show the session (5h) and weekly (7d) quotas. Use `icon_fields` to choose which two API fields are displayed, and `icon_style` to switch the icon layout.

| Key | Default | Description |
|-----|---------|-------------|
| `tray_provider` | `"claude"` | Which agent the tray icon, its tooltip and the threshold alerts follow: `"claude"` or `"codex"`. `"codex"` also makes the app read Codex quotas on the poll beat instead of only while the popup's Codex detail or bar view is open, so the Codex app-server runs in the background as well. `icon_fields` and `tooltip_fields` name Claude API fields and are ignored under `"codex"`, which always draws its shortest window on top and its longest below. The tray menu's "Tray icon tracks" submenu switches agents immediately and saves this key for the next start |
| `icon_fields` | `["five_hour", "seven_day"]` | Which two usage fields to show as icon bars. The first entry is the top bar (also determines the icon text), the second is the bottom bar |
| `icon_style` | `"number+bars"` | Icon layout: `"number+bars"` shows the first field's percentage above two progress bars; `"numbers"` shows both fields as two stacked percentages without bars |

Must be an array of exactly 2 non-empty strings. Unknown field names are accepted - if a field is `null` or missing from the API response, the bar shows 0%.

**Known field names:** `five_hour`, `seven_day`, `seven_day_sonnet`, `seven_day_opus`, `seven_day_cowork`, `seven_day_oauth_apps`

Each entry can optionally include a display mode suffix using colon syntax: `"field_name:mode"`.

**Available bar display modes:**

| Mode | Description |
|------|-------------|
| `utilization` | *(default)* Fills left-to-right proportional to current usage |
| `overage` | Shows how far usage has entered the over-budget zone: empty when usage is at or below the time marker (on pace or ahead), half-filled when usage is halfway between the time marker and 100%, full when usage reaches 100% |

In `utilization` mode, each bar also shows a thin vertical marker at the elapsed-time position of the quota period - the same information as the time marker in the detail popup. When usage is ahead of the elapsed time (or fully exhausted), the bar fill switches to the warning color (`fg_warn` in [Tray icon colors](#tray-icon-colors)), matching the popup's red warning fill.

**The `"numbers"` style** replaces the bars with a second percentage: the first `icon_fields` entry becomes the top row, the second the bottom row. Each row follows the same rules as the classic icon text - an exhausted quota shows `✕` (or `$` when paid extra usage is still available); when both quotas are exhausted at once, the icon collapses to a single full-size `✕`/`$` like the classic style. The time marker, the warning color, and the `:overage` mode suffix have no effect in this style, and while both quotas are at 0% the icon shows the usual idle "C". Each stacked number is rendered at the same size as the classic single percentage.

**Example** - show session and weekly usage as two stacked percentages:

```json
{
    "icon_style": "numbers"
}
```

**Example** - show session in overage mode and weekly in default mode:

```json
{
    "icon_fields": ["five_hour:overage", "seven_day"]
}
```

**Example** - show session and Sonnet quota (default utilization mode):

```json
{
    "icon_fields": ["five_hour", "seven_day_sonnet"]
}
```

## Event commands

Run a shell command when a usage event occurs. See [Event Commands](event-commands.md) for examples and available environment variables.

| Key | Default | Description |
|-----|---------|-------------|
| `on_reset_command` | *(none)* | Shell command (or array of commands) to run when a quota resets (usage drops) |
| `on_startup_command` | *(none)* | Shell command (or array of commands) to run once after the first successful API update following app start |
| `on_threshold_command` | *(none)* | Shell command (or array of commands) to run when usage crosses a configured alert threshold |
| `quick_action_command` | *(none)* | Shell command (or array of commands) to run when you double-click the tray icon; a single click still opens the popup. Previously named `on_double_click_command`, which still works |

## Polling intervals

**This app refreshes once a minute by default.** Polling stops after the popup has been closed for `idle_pause` seconds. The tray menu's "Refresh interval" submenu offers one, three and five minutes and saves the selection as `poll_interval`, so it survives a restart. This changes the ordinary cadence only; `poll_fast` stays unchanged so reset-confirming polls keep their timing.

The countdowns themselves never depend on these values. The popup's reset countdowns, elapsed-time markers and bar dividers are redrawn every minute from your own clock, so they keep moving whatever you set here - lowering these will not make a countdown tick faster, only spend more API calls.

| Key | Default | Description |
|-----|---------|-------------|
| `poll_interval` | `60` | Seconds between API updates. The tray menu's "Refresh interval" submenu selects and saves 60, 180 or 300 seconds. A menu choice moves the cadence alone: `poll_fast` still floors how often a fetch can be sent, so the confirming poll after a quota reset is as exact at five minutes as at one |
| `poll_fast` | `60` | Seconds when usage is actively increasing. Doubles as the cache cooldown, so a scheduled poll is never sent more often than this, whatever `poll_interval` says. Only the popup's refresh button and the refetch after an account switch skip it |
| `poll_fast_extra` | `2` | Extra fast polls after usage stops increasing |
| `poll_error` | `30` | Seconds after a transient error (5xx, network). Rate-limit errors (429) use exponential backoff instead |
| `max_backoff` | `900` | Maximum backoff in seconds for rate-limit errors (15 min). The backoff starts at twice `poll_interval` and doubles with each further 429, or follows the server's `Retry-After` when it sends one. It caps the Codex side as well, where a failed read backs off from the current refresh interval and doubles per consecutive failure |
| `idle_pause` | `300` | Seconds the popup has to stay closed before polling pauses, and seconds of user inactivity after which notifications are held back until the user returns (0 = disable both). Notifications are also held while the workstation is locked. A paused poll loop resumes when the popup is opened, and is interrupted at a quota reset when `on_reset_command` is configured |

## Language

| Key | Default | Description |
|-----|---------|-------------|
| `language` | *(auto-detected)* | Override the UI language with a language code. Available: `en`, `ja`, `ko` (any other system language falls back to `en`) |

## Time Format

By default, reset times follow your Windows clock format (the 24-hour or 12-hour / AM-PM setting from your regional preferences), so no configuration is needed. Set this key to override the auto-detected format.

| Key | Default | Description |
|-----|---------|-------------|
| `time_format` | *(auto-detected from Windows)* | Clock format for reset times: `"24h"` (e.g. `14:30`) or `"12h"` (e.g. `2:30 PM`) |

## Currency

The app shows extra usage amounts in the billing currency the Anthropic API reports for your account (its symbol and decimal precision), falling back to your Windows locale's currency symbol when the API does not report one. If you want a different symbol, override it here - your override always wins. Number formatting (decimal separator, symbol position) always follows your system locale.

| Key | Default | Description |
|-----|---------|-------------|
| `currency_symbol` | *(from API, else locale)* | Override the displayed currency symbol (e.g., `"$"`, `"€"`, `"¥"`) |

## Tray icon colors

Override individual channels as RGBA arrays `[R, G, B, A]` (0-255). Unspecified keys keep their defaults.

| Key | Default | Description |
|-----|---------|-------------|
| `icon_light` | `{"fg": [255,255,255,255], "fg_half": [255,255,255,80], "fg_dim": [255,255,255,140], "fg_warn": [224,80,80,255]}` | Light icons for dark taskbar |
| `icon_dark` | `{"fg": [0,0,0,255], "fg_half": [0,0,0,80], "fg_dim": [0,0,0,140], "fg_warn": [224,80,80,255]}` | Dark icons for light taskbar |

## Popup colors

| Key | Default | Description |
|-----|---------|-------------|
| `bg` | `"#1e1e1e"` | Background |
| `fg` | `"#cccccc"` | Text |
| `fg_dim` | `"#888888"` | Dimmed text (labels, reset times) |
| `fg_heading` | `"#ffffff"` | Section headings |
| `fg_link` | `"#4a9eff"` | Link text (e.g. changelog) |
| `bar_bg` | `"#333333"` | Progress bar background |
| `bar_fg` | `"#4a9eff"` | Progress bar fill |
| `bar_fg_alt` | `"#e0a34a"` | Weekly row fill in bar mode; warnings still use `bar_fg_warn` |
| `bar_fg_warn` | `"#e05050"` | Progress bar fill when usage outpaces elapsed time, error text |
| `bar_divider` | `"#000c"` | Time dividers on progress bars (hour marks on the session bar, midnights on weekly bars) |
| `bar_marker` | `"#fffc"` | Time-position marker on progress bars |
