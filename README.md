# AI 에이전트 사용량 모니터
[![RELEASE](https://img.shields.io/github/release/deuxdoom/usage-monitor-for-claude?style=flat&logo=github&logoColor=white&label=RELEASE&labelColor=2f353a&color=0ea5e9)](https://github.com/deuxdoom/usage-monitor-for-claude/releases/latest)
[![Downloads Latest](https://img.shields.io/github/downloads/deuxdoom/usage-monitor-for-claude/latest/total?logo=github&style=flat&label=DOWNLOADS@LATEST)](https://github.com/deuxdoom/usage-monitor-for-claude/releases/latest)
[![Downloads Total](https://img.shields.io/github/downloads/deuxdoom/usage-monitor-for-claude/total?logo=github&style=flat&label=DOWNLOADS)](https://github.com/deuxdoom/usage-monitor-for-claude/releases)
[![LICENSE](https://img.shields.io/badge/LICENSE-MIT-f43f5e?style=flat&labelColor=2f353a)](https://opensource.org/licenses/MIT)  
[![Platform](https://img.shields.io/badge/PLATFORM-WINDOWS%20X64-blue?style=flat&logo=windows)](https://github.com/deuxdoom/usage-monitor-for-claude)
[![PYTHON](https://img.shields.io/badge/PYTHON-3.10%2B-3776ab?style=flat&logo=python&logoColor=white&labelColor=2f353a)](https://www.python.org/)
[![Works with Claude](https://img.shields.io/badge/Works%20with-Claude-d97757?style=plastic&logo=anthropic&logoColor=white)](https://claude.ai/)
[![Works with Codex](https://img.shields.io/badge/Works%20with-Codex-10a37f?style=plastic&logo=openai&logoColor=white)](https://openai.com/codex/)
[![Lightweight](https://img.shields.io/badge/Lightweight-No%20Electron-black?style=plastic)](https://github.com/deuxdoom/usage-monitor-for-claude)
---

**Claude와 Codex의 사용량 한도를 윈도우 트레이에서 실시간으로 확인하세요.**

설치가 필요 없는 윈도우 네이티브 트레이 앱입니다. 검정 계열의 작은 팝업에서 `Claude` / `Codex`를 전환하며 세션·주간 한도와 초기화 시점을 빠르게 읽고, 추가 한도·설치 버전·모델별 토큰 사용량은 클릭해 펼칠 수 있습니다.

**[앱 소개 페이지](https://deuxdoom.github.io/usage-monitor-for-claude/)**에서 화면과 주요 기능을 한눈에 살펴볼 수 있습니다. 페이지의 다운로드 버튼은 최신 EXE를 바로 받고, 별도 버튼에서 릴리스 내용을 확인할 수 있습니다. 표시되는 최신 버전은 GitHub 공개 릴리스와 연동됩니다.

아래 화면은 미리보기용 예시 데이터입니다.

![AI 에이전트 사용량 모니터 스크린샷](screenshot.png)
![AI 에이전트 바 형태 스크린샷](screenshot2.png)

<p align="center"><a href="https://deuxdoom.github.io/usage-monitor-for-claude/"><img src="https://img.shields.io/badge/WEB-%EC%95%B1%20%EC%86%8C%EA%B0%9C%20%EB%B3%B4%EA%B8%B0-82d6b7?style=for-the-badge&amp;labelColor=101316" alt="웹에서 앱 소개 페이지 보기"></a></p>

---

## ✨ 주요 기능

* **포터블 (무설치):** 단일 EXE 파일을 원하는 폴더에 두고 실행하면 끝입니다. 메뉴에서 바꾼 설정은 파일에 저장되며, 앱과 설정을 모두 지우려면 EXE와 사용 중인 설정 파일을 삭제하면 됩니다.
* **제로 구성:** Claude Code와 Codex에 이미 로그인되어 있다면 그대로 인증됩니다. API 키를 따로 입력할 필요가 없습니다.
* **실시간 트레이 아이콘:** 남은 사용량을 진행률 막대나 퍼센트로 트레이에 표시합니다. 마우스를 올리면 각 한도의 수치와 초기화 시점이 툴팁으로 나오고, 우클릭 메뉴에서 Claude와 Codex 중 어느 쪽을 따라갈지 바로 고르면 다음 실행에도 유지됩니다.
* **Claude / Codex 전환 팝업:** 검정 계열의 짧은 화면에서 계정·플랜과 주요 한도 두 구간, 추가 사용량, 초기화 시점을 빠르게 봅니다. 더 많은 한도와 설치 버전은 눌러 펼칩니다. 세션 한도는 `3시간 20분 후 재설정`처럼 남은 시간으로, 주간 한도는 `8월 20일(목) 14:00에 재설정`처럼 날짜로 표시됩니다. 계정 이메일은 이름을 우선 표시하거나 가린 상태로 보여 줍니다.
* **한 줄 바 모드:** 날짜·시간 옆에 Claude와 Codex의 세션·주간 사용률을 나란히 놓아 두 에이전트의 여유를 동시에 확인합니다. 제공자와 주간 수치를 색과 구분선으로 읽기 쉽게 나누었습니다. 시계의 `:`는 1초마다 깜빡입니다. 카드를 클릭하면 숫자가 남은 사용량으로 바뀌며, 막대 채움과 시간 마커는 계속 사용률을 나타냅니다. 바는 고정 버튼을 누르지 않아도 계속 열려 있으며 날짜·시간 영역을 잡아 옮길 수 있습니다. 오른쪽 아이콘으로 상세 보기에 돌아가거나 X로 닫습니다.
* **모델별 토큰 상세:** 사용량 그래프를 클릭하면 실제 토큰 사용량과 모델별 비율(예: Sonnet 96.6% / Opus 3.4%)이 펼쳐집니다. API가 주지 않는 수치를 로컬 세션 기록에서 직접 읽어 계산하므로, 웹이나 데스크톱 앱 사용분은 이 상세에 잡히지 않습니다(퍼센트 그래프에는 모두 반영됩니다).
* **설치된 버전 확인:** CLI와 IDE 확장에 설치된 Claude Code, Codex 버전을 팝업 하단에서 펼쳐 보고 각 공식 변경 내역으로 이동할 수 있습니다. 앱 버전 옆의 GitHub Octicon은 프로젝트를 엽니다.
* **스마트 알림:** 사용량이 설정한 임계값이나 추가 결제 금액을 넘으면 알림을 받습니다. 자리를 비운 동안 온 알림은 돌아왔을 때 표시됩니다.
* **이벤트 명령 실행:** 한도가 초기화되거나 임계값을 넘었을 때, 앱 시작 시, 트레이 아이콘을 더블 클릭했을 때 원하는 명령을 창 없이 실행합니다.
* **시간 대비 사용률 표시:** 사용률이 경과 시간 비율보다 앞서면 붉은색, 여유가 있으면 녹색으로 표시합니다. 5시간 중 2시간 30분이 지났다면 50%가 기준이 되므로 지금 속도가 빠른지 한눈에 알 수 있습니다.
* **알아서 도는 자동 갱신:** 기본 1분마다 갱신하되, 팝업을 닫아 둔 채 시간이 지나면 조회를 멈춰 불필요한 API 호출을 만들지 않습니다. 갱신 주기는 우클릭 메뉴에서 1분, 3분, 5분 중에 고를 수 있으며, 앱을 다시 켜도 선택이 유지됩니다. 남은 시간과 시간 마커는 조회와 무관하게 계속 흐르고, 세션이 만료되면 토큰도 자동으로 갱신합니다.
* **선택해서 설치하는 앱 업데이트:** EXE 실행 때 GitHub의 최신 안정 릴리스를 확인하고 새 버전이 있으면 설치 여부를 묻습니다. 동의하면 별도 진행 창에서 다운로드 크기와 SHA-256을 검증하고 기존 앱이 닫힌 뒤 EXE를 교체합니다. 완료 후 닫기를 누르면 끝입니다. 소스 실행에는 적용되지 않습니다.
* **다중 계정과 다국어:** `--config-dir`로 여러 Claude 계정을 동시에 모니터링할 수 있고, 한국어·영어·일본어를 윈도우 시스템 언어에 맞춰 자동 적용합니다.
* **글꼴과 보기 선택 저장:** Pretendard(기본)와 시스템 글꼴 중 고르면 열린 팝업에 바로 적용됩니다. 글꼴과 상세/바 보기 선택도 저장됩니다. 제목에는 나눔스퀘어 네오를 절제해 사용하고, 작은 바 모드는 시스템 글꼴을 사용합니다. 필요한 폰트는 EXE에 포함되어 오프라인에서도 표시됩니다.

---

## 🔒 보안 및 투명성

이 앱은 Claude Code의 OAuth 토큰을 읽고 Codex에 한도 조회를 위임하므로, 무엇을 읽고 어디로 보내는지가 가장 중요합니다.

* **네트워크 통신:** Claude 사용량은 `api.anthropic.com`에서 조회합니다. 앱 버전 확인은 시작 시 `api.github.com`의 공개 릴리스 정보를 읽고, 동의한 업데이트만 GitHub 배포 파일을 받습니다. 여기에 계정 정보나 토큰을 보내지 않습니다. Codex 계정과 한도는 설치된 Codex의 공식 App Server에 위임하며, Codex가 자체 설정에 따라 OpenAI 서비스와 통신합니다. 이 자식 프로세스의 분석 전송과 OpenTelemetry 내보내기는 비활성화하고, 모델 실행이나 프롬프트 전송은 하지 않습니다.
* **로컬 기록 읽기:** 모델별 토큰 상세는 로컬 세션 기록(Claude Code, 그리고 `CODEX_HOME` 또는 기본 `~/.codex`)을 읽어 계산하며 외부로 전송하지 않습니다. 다른 기기나 WSL 내부의 기록은 집계되지 않습니다.
* **인증 파일:** Claude 토큰은 조회 헤더에만 쓰이고 기록되거나 전송되지 않습니다. Codex 인증은 Codex가 담당하며, 모니터는 Codex 인증 파일을 직접 읽지 않습니다.
* **설정과 업데이트 파일:** 모니터는 표시 대상·새로고침 주기·글꼴·보기 모드 네 선택만 `config.json`에 저장합니다. 이미 읽은 설정 파일이 있으면 옛 이름의 파일도 그대로 사용하고, 다른 키의 값은 보존하며 읽거나 해석할 수 없는 파일은 덮어쓰지 않습니다. 새 파일은 기본적으로 EXE 옆에 만들고, 별도 계정 폴더가 지정되면 그곳을 우선하며, 쓸 수 없으면 `~/.claude/config.json`을 시도합니다. 업데이트 동의 시에는 임시 헬퍼와 다운로드 파일을 만들고 기존 EXE를 교체하지만 사용량이나 인증정보를 파일에 기록하지 않습니다. 윈도우 레지스트리에는 알림 등록과 자동 시작 정보를 남기며, 한도 조회를 위임받은 Codex는 자체 로그와 인증정보를 평소처럼 기록할 수 있습니다.

자세한 내용은 [PRIVACY.md](PRIVACY.md)에 있습니다.

---

## 💻 요구 사항

* **Windows 10 또는 Windows 11 (64비트)**
* **Claude Code 설치 및 로그인:** 앱이 Claude Code가 로컬에 저장한 인증 토큰을 읽어 작동합니다.
* **Codex 설치 및 ChatGPT 로그인:** Codex 화면을 채우는 데 필요합니다. Codex CLI 또는 Codex IDE 확장 중 하나면 됩니다.

---

## 🚀 시작하기

최신 릴리즈의 `AIAgentsUsageMonitor.exe`를 받아 원하는 폴더에 두고 실행하세요.

| 동작 | 결과 |
|---|---|
| **아이콘에 마우스 오버** | 사용량 퍼센트와 초기화 시점 툴팁 표시 |
| **좌클릭** | 계정 정보와 상세 사용량 팝업 열기 |
| **우클릭** | 트레이 표시 대상, 새로고침 주기, 팝업 글꼴, 자동 실행 켜기/끄기, 종료 메뉴 열기 |
| **팝업 상단 `Claude` / `Codex`** | 보고 있는 에이전트 전환 |
| **팝업의 보기 전환 버튼** | 상세 보기와 한 줄 바 모드 전환 |
| **상세 보기의 사용량 그래프 클릭** | 토큰 사용량과 모델별 비율 펼치기 / 접기 |
| **바 모드의 에이전트 카드 클릭** | 사용한 비율 / 남은 비율 전환 |
| **계정 이름 클릭** | 가려 둔 이메일 주소 보이기 / 숨기기 |
| **새로고침 버튼** | 다음 자동 갱신을 기다리지 않고 즉시 조회 |

> **💡 트레이 아이콘이 보이지 않나요?**
> 윈도우가 새 아이콘을 자동으로 숨길 수 있습니다. 작업 표시줄을 우클릭해 설정에 들어간 뒤, '시스템 트레이 아이콘'에서 **AIAgentsUsageMonitor**를 켬(On)으로 바꿔 주세요.

---

## 📚 문서

설정 파일을 직접 만들 필요는 없습니다. 메뉴에서 고른 값은 자동 저장되며, 더 손대고 싶다면 [docs/](docs/)에 정리되어 있습니다.

* [설정 항목](docs/configuration.md) - 설정 파일 위치와 저장 방식, 직접 편집하거나 메뉴에서 고를 수 있는 값
* [이벤트 명령](docs/event-commands.md) - 한도가 초기화되거나 임계값을 넘었을 때 원하는 명령을 실행하기
* [앱 자동 업데이트](docs/automatic-update-check.md) - 새 버전 확인, 별도 진행 창, 검증과 EXE 교체 방식
* [Claude API](docs/claude-api-reference.md) / [Codex API](docs/codex-api-reference.md) - 두 에이전트의 사용량을 각각 어디에서 어떻게 읽어 오는지

---

## 📄 라이선스

MIT

*이 프로젝트는 커뮤니티에서 독립적으로 만든 오픈소스 앱이며, Anthropic 또는 OpenAI의 공식 지원을 받지 않습니다.*
