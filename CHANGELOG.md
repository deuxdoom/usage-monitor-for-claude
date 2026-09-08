# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This changelog covers 1.30.0 onwards, the point from which this project builds independently.


## [2.0.0] - 2026-09-08

### Added

- 트레이 아이콘과 툴팁, 임계값 알림이 Claude와 Codex 중 어느 쪽을 따를지 트레이 우클릭 메뉴의 "트레이 표시 대상"에서 바로 고를 수 있습니다. 설정 파일을 만들 필요가 없습니다. 이 선택은 앱을 종료할 때까지만 유지되며, 다음 실행이 무엇으로 시작할지는 `tray_provider` 설정이 그대로 결정합니다
- 사용량을 얼마나 자주 갱신할지 1분, 3분, 5분 중에서 트레이 우클릭 메뉴의 "새로고침 주기"로 고를 수 있습니다. 파일에 저장하지 않으므로 앱을 다시 켜면 기본값인 1분으로 돌아옵니다. 느려지는 것은 평상시 갱신뿐입니다. 캐시 쿨다운(`poll_fast`)은 60초로 고정되어 있어, 어느 주기를 고르더라도 한도가 초기화되는 순간의 확인 조회와 알림 시점은 그대로 정확합니다

### Changed

- 팝업 글꼴이 픽셀 서체(Galmuri11)로 바뀌었습니다. 영문과 한글을 한 서체가 함께 담고 있어 두 문자가 같은 인상으로 읽힙니다. 서체 파일은 앱에 포함되어 있으므로 따로 설치할 것이 없고, 서체에 없는 문자는 기존 시스템 글꼴로 자연스럽게 대체됩니다. SIL Open Font License 1.1로 배포되는 글꼴이며 고지는 `LICENSE`에 있습니다
- 실행 파일 크기가 약 25.7MB에서 15.8MB로 줄었습니다. Pillow가 타입 힌트에서만 참조하는 NumPy를 PyInstaller가 따라가면서 NumPy와 그에 딸린 OpenBLAS(약 20MB)까지 통째로 넣고 있었습니다. 이 앱은 `Image`, `ImageDraw`, `ImageFont`만 사용하고 NumPy가 필요한 API는 쓰지 않으므로 빌드에서 제외했습니다. 위의 글꼴을 포함하고도 이전보다 약 10MB 작습니다

### Fixed

- 트레이가 Codex를 따르도록 설정한 경우, Codex 한도가 초기화되는 순간을 제때 확인합니다. 이전에는 조회 시점을 Claude의 초기화 시각에만 맞추고 있어서, Codex 창이 초기화된 뒤에도 갱신 주기 하나만큼 이전 수치를 그대로 보여줄 수 있었습니다
- 팝업의 Claude 탭과 Codex 탭이 같은 갱신 시각을 카운트다운합니다. 이전에는 Codex 쪽이 사용자가 그 탭을 처음 연 시점부터 시작하는 별도의 시계를 따르고 있어서, 탭을 언제 눌렀느냐에 따라 두 화면의 남은 시간이 서로 달랐고 새로고침 주기를 바꿔도 양쪽에 같은 시점으로 반영되지 않았습니다
- `max_backoff` 설정이 Codex 읽기 실패 후의 대기 시간에도 적용됩니다. 이전에는 Claude 쪽에만 적용되어, 설정값과 무관하게 Codex는 15분 상한으로 고정되어 있었습니다

### Removed

- 트레이 메뉴의 "다시 시작" 항목을 없앴습니다. 이 항목은 `usage-monitor-settings.json`을 편집한 뒤 다시 읽어들이기 위한 통로였는데, 일상적으로 바꿀 만한 설정은 이제 트레이 메뉴에서 직접 고를 수 있습니다. 설정 파일을 수정한 뒤 적용하려면 트레이 메뉴에서 종료한 다음 다시 실행하면 됩니다

[Show all code changes](https://github.com/deuxdoom/usage-monitor-for-claude/compare/v1.90.0...v2.0.0)


## [1.90.0] - 2026-09-07

The quick-action rename, the autostart wording, the late-failure dialog, the event-command reset fix and the two TLS changes below were found in, and adapted from, upstream [usage-monitor-for-claude v1.22.0](https://github.com/jens-duttke/usage-monitor-for-claude/releases/tag/v1.22.0) - thanks to [@jens-duttke](https://github.com/jens-duttke). The Codex view and the rename to AI Agents Usage Monitor are this fork's own work.

### Added

- Switch between Claude and Codex in the popup header to see the Codex account, plan and server quota bars with reset times, refreshed every minute, with local 5-hour/7-day token details collapsed under each clickable bar and installed CLI/IDE extension versions plus a Changelog link to the Codex release notes in the footer
- `tray_provider` picks which agent the tray icon, its tooltip and the threshold alerts follow. It stays on Claude unless you set `"tray_provider": "codex"`, which also keeps Codex quotas up to date while the popup is closed - see [docs/configuration.md](docs/configuration.md)

### Changed

- The app is now called **AI Agents Usage Monitor**, and the download is `AIAgentsUsageMonitor.exe`. It no longer watches Claude alone, so the tray menu, the notifications and the dialogs drop the Claude-only name. The tray menu opens with the app name as a heading and its first action reads "Show usage" rather than "Show Claude usage"; the popup header became a Claude/Codex switch, so the app name moved to the footer, where hovering the version shows it. Your settings file is unchanged. Because the file name changed, the old `UsageMonitorForClaude.exe` stays where it is when you copy the new one in - delete it, and if you had "start at login" on, launch the new file once so the entry points at it again
- The Codex plan row names the product, not just the tier: "ChatGPT Plus" instead of "Plus", and the same for Free, Go, Pro, Business and Enterprise
- Claude and Codex quota bars show larger percentages in the bar's blue/red color, with elapsed-time and consumption-pace text to explain when usage is ahead of the time budget
- **Breaking:** the quick action (a double-click on the tray icon) now reports itself as `USAGE_MONITOR_EVENT=quick_action` instead of `double_click`. A script that branches on that variable needs the new value
- The `on_double_click_command` setting is now called `quick_action_command`. Existing settings files keep working unchanged - the old name is still accepted, and the new one wins if you set both
- The autostart menu entry now reads "Start at login", which is when it actually runs
- The installed-version rows in the popup now name the extension, not just the editor: "VS Code (Claude)" next to the "VS Code (Codex)" the Codex view shows, so one editor carrying both extensions reads unambiguously
- A quick action no longer raises a failure dialog when the program it started exits with an error later on. Starting something you keep open and closing it hours afterwards is not a broken command, and a dialog appearing then has no visible connection to the click. A command that fails immediately - a wrong path, a bad argument - is still reported at once

### Fixed

- Event commands now run when a quota resets. If the API reported the fresh quota without a new reset time yet, the app passed an empty value the launched process rejected, and `on_reset_command` was silently skipped - at the one moment it exists for. Threshold commands could be lost the same way
- The app now reaches the API from behind a corporate proxy that inspects TLS. Certificates are verified against the Windows certificate store, which holds the root your company installs, instead of only the list bundled with the app
- A failed certificate check now says so, instead of being reported as an ordinary connection failure that gave no hint where to look

[Show all code changes](https://github.com/deuxdoom/usage-monitor-for-claude/compare/v1.80.0...v1.90.0)

## [1.80.0] - 2026-09-04

### Changed

- Reset countdowns, elapsed-time markers and bar dividers no longer wait on a fetch to move. They are read off your own clock, so the popup redraws them every minute on its own; previously only a fresh API response could move them, which left them frozen whenever a poll was delayed by a rate limit, an error, or a raised `poll_interval`
- The countdown to the next update now names the seconds as well as the minutes, so it visibly moves on every tick. It previously showed whole minutes only, leaving the footer unchanged for a minute at a time, which read as a stalled app rather than a waiting one
- Notifications are registered under this project's own identity (`현재repo작성자.UsageMonitorForClaude`) instead of the one inherited from the project this was forked from. Toasts look and behave exactly as before; if you had adjusted this app's notification settings in Windows, set them once more, since Windows tracks them per identity. The registry entry the old identity left behind is deleted on first start, so nothing of it stays on your machine
- The executable's file properties now name this project. The company field reads `현재repo작성자` and the version resource is tagged Korean, instead of the values carried over from the project this was forked from

### Fixed

- The refresh button no longer sends a request while the API is rate-limiting the app. It used to force past the wait the server had asked for, so pressing it on the "API request failed (HTTP 429)" message - the one moment it is most tempting to press - kept the limit alive instead of clearing it. The immediate refresh after an account switch is unaffected and still bypasses the wait
- A first rate-limit error now actually slows the app down. The backoff was exactly one polling interval long, so the retry repeated the same request rate the server had just rejected; it now starts at twice the interval and doubles from there, so a rate limit clears instead of renewing itself

[Show all code changes](https://github.com/deuxdoom/usage-monitor-for-claude/compare/v1.70.0...v1.80.0)

## [1.70.0] - 2026-08-21

### Changed

- Polling now follows the popup instead of running around the clock. It refreshes while the popup is open - including a pinned one, for as long as you leave it up - and for five minutes after you close it, then pauses until you open it again. An app sitting in the tray with nothing on screen no longer spends an API call a minute on numbers nobody is looking at
- Reset lines no longer repeat themselves. A countdown now ends where it makes its point ("Resets in 3h 20m") instead of restating the same moment as a clock time, and a reset further out reads as one phrase with the date and the time together ("Resets on 8/23 (3:00 AM)")
- Reset dates no longer name the weekday. In Korean and Japanese the weekday character repeated the one already ending the date, so "8월 23일(일)에 재설정, 3:00 AM" read as if it said the same thing twice; the calendar date pins the day on its own
- The tray tooltip now labels each quota in your own language - Korean shows "5시간" and "7일" instead of the untranslated "5h" and "7d"
- `idle_pause` now also sets how long the popup has to stay closed before polling pauses, on top of the notification hold it already governed

### Removed

- Ten of the thirteen bundled languages (German, Spanish, French, Hindi, Indonesian, Italian, Portuguese, Ukrainian, Simplified and Traditional Chinese). English, Japanese and Korean remain; any other system language now shows the English UI

[Show all code changes](https://github.com/deuxdoom/usage-monitor-for-claude/compare/v1.60.0...v1.70.0)

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
- New `icon_style` setting - set it to `"numbers"` to show both `icon_fields` values as two stacked percentages on the tray icon instead of one percentage with two bars; each row shows `✕` or `$` when its quota is exhausted (thanks to [@Searcus](https://github.com/Searcus) for the suggestion)

### Changed

- The account row now shows your name and keeps the email address hidden until you click it - the popup is often open during a screen share, and the address is the one value there worth not leaving visible. Accounts the API reports without a name show the address blurred instead, revealed by the same click
- Usage is polled once a minute by default (`poll_interval` and `poll_fast` both `60`), so the tray and the popup countdown move on a one-minute cycle; raise either setting to go back to fewer API calls
- The tray context menu links to this fork's repository instead of the upstream one
- The "Test event commands" submenu is hidden entirely when no event command is configured, instead of appearing greyed out - it reappears as soon as one is set
- The popup footer now shows the countdown to the next update from the moment the data arrives - previously it appeared only once the "updated" half had rolled over from seconds to minutes, leaving the first minute without any indication of when the next poll was due
- Korean popup title is now localized (`Claude 사용량 모니터`); other languages keep the English product name

### Fixed

- With uncapped extra usage enabled, an exhausted quota now shows the "extra usage active" tray indicator instead of the exhausted glyph - work continues on paid overage, so the icon no longer suggests Claude has stopped (thanks to [@joeklittle](https://github.com/joeklittle) for the contribution)
- The startup and double-click event commands no longer report `USAGE_MONITOR_EXTRA_LIMIT` as a zero amount for uncapped extra usage - the variable is now omitted when there is no monthly limit (thanks to [@joeklittle](https://github.com/joeklittle) for the contribution)
- After an account switch, the tray icon and popup now show the new account's usage right away - previously, when the switch happened while a usage request was already running, the "account switched" notification appeared next to the previous account's numbers, which stayed on screen until the next scheduled poll

[Show all code changes](https://github.com/deuxdoom/usage-monitor-for-claude/releases/tag/v1.30.0)
