# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This changelog covers 1.30.0 onwards, the point from which this project builds independently.


## [3.2.0] - 2026-09-25

### Added

- 바 모드 카드 오른쪽 위에 지금 보이는 숫자가 사용한 비율인지 남은 비율인지를 `사용`/`남음`으로 표시합니다. 3.1.0에서는 카드를 눌러 남은 비율로 바꿔도 화면에 이를 알려 주는 표시가 없었습니다
- 바 모드의 각 행 앞에 `5h`·`7d` 같은 기간 라벨을 붙였습니다. 라벨은 필드 이름이 아니라 서버가 알려 준 기간(`period_seconds`)에서 계산하므로, 한도 기간이 바뀌어도 맞게 표시됩니다. 3.1.0은 두 행을 색으로만 구분했습니다
- 바 모드의 카드와 행에 툴팁을 넣었습니다. 초기화 시점, 클릭하면 사용한 비율과 남은 비율이 바뀐다는 안내, 막대와 시간 마커는 항상 사용한 비율 기준이라는 설명을 보여 주며, 시계에는 "드래그하여 이동"이 표시됩니다
- 로컬 토큰 상세를 펼칠 수 있는 한도 카드의 이름 옆에 펼침 화살표를 표시합니다. 3.1.0에서는 어느 카드를 눌러야 상세가 열리는지 화면에서 알 수 없었습니다

### Changed

- 상세 팝업과 바 모드의 배경 위쪽에 두 에이전트의 시그니처 색이 옅게 번지게 하고, 카드에 반투명 표면과 얇은 윗면 하이라이트를 넣어 두 보기를 같은 질감으로 맞췄습니다. 창과 글자는 불투명하게 유지하므로 바탕 화면이 비치지 않습니다. 계정 같은 보조 패널은 표면을 한 단계 낮춰 선택된 탭과 사용량 카드가 먼저 눈에 들어옵니다. 상단 색 띠는 2px에서 1px로, 사용량 카드의 왼쪽 색 선은 3px에서 2px로 줄였습니다
- 사용 속도 문구를 줄였습니다. "시간 경과 76% · 시간 대비 여유"는 "경과 76% · 여유"가 되고, 영어는 "Elapsed 76% · On pace"/"Ahead of pace", 일본어는 "経過 76% · 余裕あり"/"速い消費"로 바뀝니다
- 재설정 시각 글자를 10px에서 11px로 키우고, 출처 주석(불투명도 0.65)과 추정치(0.8)에 걸려 있던 반투명을 없애 흐린 글자를 읽기 쉽게 했습니다
- 조회가 늦어지거나 실패했을 때 사용량 섹션 전체를 불투명도 40%로 흐리게 하던 것을, 막대만 흐리게 하고 카드 왼쪽 선을 점선으로 바꾸도록 해 마지막 수치를 그대로 읽을 수 있게 했습니다. 바 모드도 행 전체를 흐리고 제공자 이름을 경고 빨강(`bar_fg_warn`)으로 칠하던 것을, 막대만 흐리고 이름 옆에 `!`를 붙이도록 바꿔 조회 실패가 한도 경고와 같은 색으로 보이지 않게 했습니다. 오류 내용은 각 행의 툴팁에도 나옵니다
- 버튼과 펼칠 수 있는 카드에 키보드 포커스 테두리를 표시하고, 설치 목록의 "변경 내역" 링크를 버튼으로 바꿔 Tab과 Enter로도 열 수 있게 했습니다
- 기록이 비어 있는 세션 패널에도 출처 주석("로컬 Claude Code 기록 기준…")을 주간 패널과 똑같이 반복하던 것을, 기록이 있는 패널과 같은 규칙으로 가장 긴 기간의 패널에만 한 번 표시합니다. 3.1.0은 빈 패널을 예외로 두어 Claude 세션 카드 아래에 주석이 남았고, Codex 쪽은 이미 한 번만 표시했습니다. 빈 패널의 "이 기간에 Claude Code 사용 기록이 없습니다" 문구가 기록 범위를 이미 알려 줍니다

[Show all code changes](https://github.com/deuxdoom/usage-monitor-for-claude/compare/v3.1.0...v3.2.0)


## [3.1.0] - 2026-09-25

### Added

- 업데이트가 끝나면 앱을 원래 실행 인자(`--config-dir` 등) 그대로 자동으로 다시 실행합니다. 3.0.0은 완료 후 "닫기"만 남기고 앱을 다시 켜지 않았습니다. 새로 실행하는 앱은 PyInstaller의 `_PYI_*` 환경 변수와 DLL 경로를 이어받지 않고 자체 임시 폴더를 풉니다
- 새 버전이 시작 후 3초 안에 종료되면, 교체 직전에 같은 폴더에 만들어 둔 백업으로 되돌리고 이전 버전을 실행합니다. 교체 자체가 실패하면 손대지 않은 기존 EXE를 다시 실행합니다

### Changed

- 새 버전 안내 메시지 상자와 별도 진행 창을 프레임 없는 업데이트 창 하나로 합쳤습니다. 창은 주 모니터 가운데에 뜨고, 릴리스 본문을 요약한 변경 내역, 다운로드·파일 확인·앱 종료·설치·다시 실행 다섯 단계와 진행률을 함께 보여 주며, 완료 4초 뒤 스스로 닫힙니다
- 앱은 새 EXE의 다운로드와 검증(크기, SHA-256, GUI 실행 파일 형식)이 끝난 뒤에야 종료 요청을 받습니다. 3.0.0은 설치에 동의하는 즉시 앱을 종료했습니다. "나중에"를 누르면 업데이트 창용 임시 복사본을 재부팅까지 기다리지 않고 바로 지웁니다
- 팝업 전체를 번들 Pretendard JP 한 서체로 통일했습니다. 3.0.0에서는 본문 Pretendard, 섹션 제목·한도 이름 나눔스퀘어 네오, 추가 사용량 퍼센트 Segoe UI Variable, 바 모드 Arial(`Helvetica` 대체)·맑은 고딕이 한 화면에 섞여 있었습니다. 위계는 크기와 굵기로만 나눕니다. 나눔스퀘어 네오(1.5 MB)를 빼고 한자까지 담은 Pretendard JP(5.1 MB)로 바꿔 EXE는 약 1.6 MB 커졌습니다
- 바 모드에서 카드 하나를 누르면 Claude와 Codex 두 카드가 함께 사용한 비율/남은 비율로 바뀌던 동작을, 누른 카드만 바뀌도록 나눴습니다. 새로고침이 와도 카드마다 고른 표시가 유지됩니다
- 바 모드의 `CLAUDE`·`CODEX` 이름을 각 에이전트의 시그니처 색(갈색·파랑)으로 표시합니다. 제공자 전환 버튼의 점과 상단 띠도 같은 색을 씁니다. Claude는 브랜드 주황 대신 채도를 낮춘 갈색(`#b9835a`)을 써서 옆의 경고 빨강(`bar_fg_warn`)과 헷갈리지 않게 했고, 3.0.0의 Codex 파랑은 대비가 3.55:1로 작은 글자에 어두웠으므로 두 색 모두 검은 배경 대비 4.5:1 이상으로 맞췄습니다
- 바 모드 배경을 한 단계 밝은 카드 색에서 상세 팝업과 같은 검정(`bg`)으로 바꿨습니다
- 세션·주간 카드를 함께 펼치면 두 패널 아래에 같은 출처 주석("로컬 Claude Code 기록 기준…", "최근 5시간. 여러 계정의…")이 반복되던 것을, 가장 긴 기간인 주간 패널에만 한 번 표시합니다. 기록이 비어 있는 패널은 0으로 보이는 이유를 알려야 하므로 주석을 그대로 둡니다
- 한국어·일본어 화면의 섹션 제목에 대문자용 자간(0.08em)이 그대로 적용되어 "사 용 량"처럼 음절이 벌어지던 표시를 자연스러운 간격으로 바꿨습니다
- 소개 페이지(`index.html`)의 한글을 모두 앱과 같은 Pretendard JP로 맞추고, 히어로의 팝업·바 미리보기와 안내 문구를 가운데 축에 정렬했습니다. 중복된 "최신 릴리스 확인"·하단 다운로드 버튼을 없애고 상단 고정 메뉴의 "다운로드"로 모았습니다

### Fixed

- 팝업을 고정한 채 바 모드를 화면 아래쪽으로 옮긴 뒤 상세 보기로 돌아가면, 창이 왼쪽 위 모서리를 기준으로 늘어나 아래 부분이 모니터 밖으로 잘리던 문제를 고쳤습니다. 이제 작업 영역의 아래쪽 절반에 있는 창은 아래 가장자리를 유지한 채 위로 늘어나고, 그래도 넘치면 작업 영역 안으로 옮겨집니다. 고정한 상세 창에서 카드나 한도 목록을 펼칠 때도 같습니다
- 일본어 화면에서 Pretendard에 없는 한자가 맑은 고딕으로 대체되어 한국식 자형으로 보이던 문제를 고쳤습니다. 이제 가나와 한자도 Pretendard JP로 표시됩니다
- "한도 더 보기"와 설치 목록의 펼침 화살표(`⌄`)가 대체 글꼴로 그려져 글자 기준선 아래로 처지던 표시를 CSS로 그린 화살표로 바꿨습니다

### Removed

- 트레이 메뉴의 "팝업 글꼴"과 `popup_font` 설정을 없앴습니다. 기존 설정 파일에 남은 `popup_font` 값은 읽지 않으며 지우지 않고 그대로 둡니다
- 트레이 메뉴의 "사용량 보기" 항목을 없앴습니다. 트레이 아이콘을 왼쪽 클릭하면 이전처럼 팝업이 열립니다


## [3.0.0] - 2026-09-25

### Added

- EXE 시작 시 GitHub 최신 안정 릴리스를 확인하고, 새 버전이 있으면 설치 여부를 묻습니다. 동의하면 별도 프로세스가 진행 상태를 표시하며 파일 크기와 SHA-256을 검증한 뒤 실행 중인 앱이 닫히면 EXE를 교체합니다
- 추가 한도와 CLI·IDE 설치 목록을 필요할 때만 펼치는 버튼을 추가했습니다
- 팝업 버전 옆에 GitHub 공식 `mark-github` Octicon을 넣어 프로젝트 페이지를 바로 열 수 있습니다
- 프로젝트 루트에 실제 화면, 핵심 기능, 데이터 처리 범위와 다운로드 경로를 소개하는 반응형 `index.html`을 추가했습니다
- 소개 페이지는 GitHub 최신 릴리스 버전을 표시하고 EXE 직접 다운로드와 릴리스 확인을 분리했습니다. 고정 메뉴, 카드 호버와 지원 브라우저의 스크롤 등장 효과를 적용하며 움직임 감소 설정을 존중합니다

### Changed

- 기본 팝업을 검정 계열의 간결한 계정 패널과 신호색이 있는 한도 카드로 다시 구성했습니다. 기본 화면은 주요 한도 두 개를 먼저 보여 주고, 모델별 토큰 상세는 기존처럼 카드를 눌러 확인합니다
- 기본 상세 글꼴을 갈무리11에서 포함된 Pretendard로 바꾸고, 제목에 나눔스퀘어 네오를 적용했습니다. 저장된 `popup_font=pixel` 및 `mono` 값은 Pretendard로 이어집니다
- 한 줄 바 모드의 제공자 구분과 수치 대비를 다듬고, 기존 사용률·남은 비율 전환과 시간 마커 동작은 유지했습니다


## [2.1.0] - 2026-09-13

### Added

- 트레이 메뉴의 "팝업 글꼴"에서 시스템(기본)·픽셀(Galmuri11) 서체를 고르면 열린 팝업에 즉시 적용되며, `popup_font` 설정으로도 선택할 수 있습니다
- 팝업을 날짜·시간과 Claude·Codex의 세션·주간 사용률을 나란히 보여주는 바 모드로 전환할 수 있으며(`popup_view`), 시계의 `:`는 1초마다 깜빡이고 카드를 클릭하면 숫자만 남은 사용량으로 바뀌며 막대 채움과 시간 마커는 사용률 기준을 유지합니다
- 바 모드는 하단 여백 없이 작게 표시되고 고정 여부와 관계없이 계속 열려 있으며, 날짜·시간 영역으로 드래그하고 오른쪽 버튼으로 상세 보기 복귀 또는 닫기를 할 수 있습니다
- 바 모드의 주간 막대 색상을 `bar_fg_alt`로 지정할 수 있으며, 기본값은 세션 막대와 구별되는 `#e0a34a`입니다

### Changed

- 팝업의 기본 글꼴을 시스템 서체로 바꾸고, 픽셀 서체는 트레이 메뉴에서 선택할 수 있도록 했습니다
- 종료하면 사라지던 트레이 표시 대상(`tray_provider`)과 새로고침 주기(`poll_interval`) 선택을 이제 설정 파일에 저장하며, 팝업 글꼴(`popup_font`)과 보기 모드(`popup_view`)도 다음 실행에서 유지합니다
- 설정 파일의 기본 이름을 `usage-monitor-settings.json`에서 `config.json`으로 바꾸되 기존 이름도 계속 읽고 같은 파일에 저장하며, 디렉터리 우선순위를 유지하면서 각 디렉터리 안에서 새 이름을 먼저 찾습니다
- 설정 저장은 `settings_store.py`가 위 네 키만 갱신하고 나머지 키의 값을 보존하며, 읽거나 해석할 수 없는 기존 파일은 덮어쓰지 않고 저장에 실패해도 선택은 현재 실행에 적용합니다
- 팝업의 새로고침·고정·고정 해제·닫기·보기 전환 아이콘을 Fluent UI System Icons의 16px regular 아이콘으로 통일했습니다

### Fixed

- Codex가 사용률 0인 구간에 `resetsAt`을 보내더라도 팝업에 리셋 카운트다운과 경과 시간·시간 마커를 표시하지 않으며, 사용하지 않은 세션을 열었을 뿐인데 약 5시간 뒤 초기화되는 것처럼 보이던 문제를 수정했습니다

[Show all code changes](https://github.com/deuxdoom/usage-monitor-for-claude/compare/v2.0.0...v2.1.0)


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
