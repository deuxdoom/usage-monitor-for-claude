# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This fork builds independently from 1.30.0 onwards. For 1.20.0 and earlier, see the
[upstream changelog](https://github.com/jens-duttke/usage-monitor-for-claude/blob/main/CHANGELOG.md).


## [1.60.0] - 2026-08-17

### Changed

- Usage is now refreshed every minute without interruption. Polling no longer pauses while the computer is idle or the workstation is locked, so coming back to the machine no longer means looking at a stale reading, or waiting for the refresh cycle to restart before the numbers move again. Notifications are still held back until you return, so nothing pops up on a lock screen
- The session bar always states how much time is left ("Resets in 3h 20m"), even when the window ends after midnight - it previously switched to a bare clock time ("Resets tomorrow, 01:00"), which hid how much of the session was actually left. Weekly and other multi-day limits keep the calendar form, where a weekday and date say more than a large hour count
- The popup footer now shows only the countdown to the next update, instead of pairing it with how long ago the last one landed. The countdown already implies the data's age, and one moving number is easier to read at a glance than two counting in opposite directions

### Fixed

- The `idle_pause` setting now only governs how long you must be away before notifications are deferred; it no longer stops the app from polling
- The optional update-check script in the docs now watches this repository's releases. It still pointed at the upstream project it was forked from, so it compared your version against a different release series and offered that project's download

[Show all code changes](https://github.com/deuxdoom/usage-monitor-for-claude/compare/v1.50.0...v1.60.0)

## [1.50.0] - 2026-08-15

### Changed

- The session and weekly bar labels now use each language's own words for the period - Korean shows "세션 (5시간)" and "주간 (7일)" instead of the untranslated "5hr" and "7 day", and every other language gets its equivalent

### Fixed

- Reset times more than a day away now name the calendar date next to the weekday ("Resets on Sat 1/18, 14:00") - the weekday on its own was ambiguous about which week it meant, and in Korean, Japanese and Chinese it rendered as a lone character with no date at all

[Show all code changes](https://github.com/deuxdoom/usage-monitor-for-claude/compare/v1.40.0...v1.50.0)

## [1.40.0] - 2026-08-13

### Added

- Click the session (5hr) or weekly (7 day) usage bar for exact token/message counts and a per-model usage breakdown (e.g. Sonnet 96.6% / Opus 3.4%) - read from local Claude Code session logs, since the usage API itself only reports a percentage. The panel names its source, because those logs cover Claude Code alone: a period spent on claude.ai or the desktop app still moves the percentage but leaves no local record
- Korean UI now uses 클로드 for the app's own labels (popup title, tray menu, tooltip, dialogs) instead of the English "Claude"; "Claude Code" stays as-is, being the literal name of the program to install

### Fixed

- The session (5hr) and weekly (7 day) bars no longer disappear from the popup when the account has not touched that period yet - `popup_hide_inactive` was treating them the same as an unused model-scoped quota

[Show all code changes](https://github.com/deuxdoom/usage-monitor-for-claude/compare/v1.30.0...v1.40.0)

## [1.30.0] - 2026-08-13

### Added

- Extra usage without a monthly limit (uncapped pay-as-you-go overage, the usual state for Team and Enterprise plans) now appears in the popup as the amount spent - previously the Extra Usage section stayed hidden unless a monthly limit was configured, silently hiding real spending (thanks to [@joeklittle](https://github.com/joeklittle) for the contribution)
- New `alert_extra_usage_spent` setting - absolute spending amounts in your billing currency (e.g. `[50, 100, 150]`) that trigger a notification when extra-usage spending crosses them; complements the percentage thresholds and is the only alert that can fire for uncapped extra usage, where no percentage exists (thanks to [@joeklittle](https://github.com/joeklittle) for the contribution)
- Manual refresh button in the popup header - click the circular arrow to fetch usage data immediately instead of waiting for the next scheduled poll; the icon spins while the request runs and repeated presses are throttled to one fetch every 5 seconds
- New `popup_hide_inactive` setting, on by default - quota types the API reports but that have never been used (no reset window, 0% consumed) no longer appear as permanently empty bars in the popup; set it to `false` for the previous behavior
- The popup now avoids the taskbar's own window rectangle in addition to the reported work area, so it no longer opens underneath an auto-hiding taskbar
- Verbose diagnostics (`--verbose`) now report which settings file was loaded, or that none was found, plus the effective `popup_margin`
- New `popup_margin` setting - widens the gap between the popup and the screen edge it is anchored to (default `12` pixels), so the popup stays clear of an auto-hiding or third-party taskbar that Windows' reported work area does not account for
- New `popup_hide_fields` setting - a list of usage bars the popup never shows, matched by field name or by the label displayed in the popup (e.g. `["Nimbus Quill"]`), so the `"*"` wildcard in `popup_fields` can stay in place while individual auto-detected quota types are suppressed. Defaults to `["nimbus_quill"]`
- [New `icon_style` setting](https://github.com/jens-duttke/usage-monitor-for-claude/issues/78) - set it to `"numbers"` to show both `icon_fields` values as two stacked percentages on the tray icon instead of one percentage with two bars; each row shows `✕` or `$` when its quota is exhausted (thanks to [@Searcus](https://github.com/Searcus) for the suggestion)

### Changed

- The account row now shows your name and keeps the email address hidden until you click it - the popup is often open during a screen share, and the address is the one value there worth not leaving visible. Accounts the API reports without a name show the address blurred instead, revealed by the same click
- Usage is polled once a minute by default (`poll_interval` and `poll_fast` both `60`, upstream `180` / `120`), so the tray and the popup countdown move on a one-minute cycle; raise either setting to go back to fewer API calls
- The tray context menu links to this fork's repository instead of the upstream one
- The "Test event commands" submenu is hidden entirely when no event command is configured, instead of appearing greyed out - it reappears as soon as one is set
- The popup footer now shows the countdown to the next update from the moment the data arrives - previously it appeared only once the "updated" half had rolled over from seconds to minutes, leaving the first minute without any indication of when the next poll was due
- Korean popup title is now localized (`Claude 사용량 모니터`); other languages keep the English product name

### Fixed

- With uncapped extra usage enabled, an exhausted quota now shows the "extra usage active" tray indicator instead of the exhausted glyph - work continues on paid overage, so the icon no longer suggests Claude has stopped (thanks to [@joeklittle](https://github.com/joeklittle) for the contribution)
- The startup and double-click event commands no longer report `USAGE_MONITOR_EXTRA_LIMIT` as a zero amount for uncapped extra usage - the variable is now omitted when there is no monthly limit (thanks to [@joeklittle](https://github.com/joeklittle) for the contribution)
- After an account switch, the tray icon and popup now show the new account's usage right away - previously, when the switch happened while a usage request was already running, the "account switched" notification appeared next to the previous account's numbers, which stayed on screen until the next scheduled poll

[Show all code changes](https://github.com/deuxdoom/usage-monitor-for-claude/releases/tag/v1.30.0)
