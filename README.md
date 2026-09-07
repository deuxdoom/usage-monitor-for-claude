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

설치가 필요 없는 26MB짜리 윈도우 네이티브 트레이 앱입니다. 팝업 상단의 `Claude` / `Codex` 버튼으로 전환하면 두 에이전트의 세션·주간 한도가 얼마나 남았는지 같은 화면에서 볼 수 있고, 사용량 그래프를 클릭하면 모델별 토큰 사용량까지 펼쳐집니다.

![AI 에이전트 사용량 모니터 스크린샷](screenshot.png)

---

## ✨ 주요 기능

* **포터블 (무설치):** 단일 EXE 파일을 원하는 폴더에 두고 실행하면 끝입니다. 삭제도 파일을 지우는 것으로 끝납니다.
* **제로 구성:** Claude Code와 Codex에 이미 로그인되어 있다면 그대로 인증됩니다. API 키를 따로 입력할 필요가 없습니다.
* **실시간 트레이 아이콘:** 남은 사용량을 진행률 막대나 퍼센트로 트레이에 표시합니다. 마우스를 올리면 각 한도의 수치와 초기화 시점이 툴팁으로 나옵니다.
* **Claude / Codex 전환 팝업:** 계정과 플랜, 활성화된 모든 한도, 추가 사용량, 초기화 시점을 한 화면에서 봅니다. 세션 한도는 `3시간 20분 후 재설정`처럼 남은 시간으로, 주간 한도는 `8월 20일(목) 14:00에 재설정`처럼 날짜로 표시되어 지금 작업을 이어갈 수 있는지 바로 판단할 수 있습니다.
* **모델별 토큰 상세:** 사용량 그래프를 클릭하면 실제 토큰 사용량과 모델별 비율(예: Sonnet 96.6% / Opus 3.4%)이 펼쳐집니다. API가 주지 않는 수치를 로컬 세션 기록에서 직접 읽어 계산하므로, 웹이나 데스크톱 앱 사용분은 이 상세에 잡히지 않습니다(퍼센트 그래프에는 모두 반영됩니다).
* **설치된 버전 확인:** CLI와 IDE 확장에 설치된 Claude Code, Codex 버전을 팝업 하단에서 바로 확인하고 각 공식 변경 내역으로 이동할 수 있습니다.
* **스마트 알림:** 사용량이 설정한 임계값이나 추가 결제 금액을 넘으면 알림을 받습니다. 자리를 비운 동안 온 알림은 돌아왔을 때 표시됩니다.
* **이벤트 명령 실행:** 한도가 초기화되거나 임계값을 넘었을 때, 앱 시작 시, 트레이 아이콘을 더블 클릭했을 때 원하는 명령을 창 없이 실행합니다.
* **시간 대비 사용률 표시:** 사용률이 경과 시간 비율보다 앞서면 빨강, 여유가 있으면 파랑으로 표시합니다. 5시간 중 2시간 30분이 지났다면 50%가 기준이 되므로 지금 속도가 빠른지 한눈에 알 수 있습니다.
* **알아서 도는 자동 갱신:** 1분마다 갱신하되, 팝업을 닫아 둔 채 시간이 지나면 조회를 멈춰 불필요한 API 호출을 만들지 않습니다. 남은 시간과 시간 마커는 조회와 무관하게 계속 흐르고, 세션이 만료되면 토큰도 자동으로 갱신합니다.
* **다중 계정과 다국어:** `--config-dir`로 여러 Claude 계정을 동시에 모니터링할 수 있고, 한국어·영어·일본어를 윈도우 시스템 언어에 맞춰 자동 적용합니다.

---

## 🔒 보안 및 투명성

이 앱은 Claude Code의 OAuth 토큰을 읽고 Codex에 한도 조회를 위임하므로, 무엇을 읽고 어디로 보내는지가 가장 중요합니다.

* **사용량 조회 통신:** Claude는 `api.anthropic.com`으로만 조회합니다. Codex 계정과 한도는 설치된 Codex의 공식 App Server에 위임하며, Codex가 자체 설정에 따라 OpenAI 서비스와 통신합니다. 이 자식 프로세스의 분석 전송과 OpenTelemetry 내보내기는 비활성화하고, 모델 실행이나 프롬프트 전송은 하지 않습니다.
* **로컬 기록 읽기:** 모델별 토큰 상세는 로컬 세션 기록(Claude Code, 그리고 `CODEX_HOME` 또는 기본 `~/.codex`)을 읽어 계산하며 외부로 전송하지 않습니다. 다른 기기나 WSL 내부의 기록은 집계되지 않습니다.
* **인증 파일:** Claude 토큰은 조회 헤더에만 쓰이고 기록되거나 전송되지 않습니다. Codex 인증은 Codex가 담당하며, 모니터는 Codex 인증 파일을 직접 읽지 않습니다.
* **디스크 쓰기 없음:** 모니터 자체는 파일을 만들지 않고, 윈도우 레지스트리에 알림 등록과 자동 시작 정보만 최소한으로 남깁니다. 한도 조회를 위임받은 Codex는 자체 로그와 인증정보를 평소처럼 기록할 수 있습니다.

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
| **우클릭** | 자동 실행 켜기/끄기, 다시 시작, 종료 메뉴 열기 |
| **팝업 상단 `Claude` / `Codex`** | 보고 있는 에이전트 전환 |
| **사용량 그래프 클릭** | 토큰 사용량과 모델별 비율 펼치기 / 접기 |
| **계정 이름 클릭** | 가려 둔 이메일 주소 보이기 / 숨기기 |
| **새로고침 버튼** | 다음 자동 갱신을 기다리지 않고 즉시 조회 |

> **💡 트레이 아이콘이 보이지 않나요?**
> 윈도우가 새 아이콘을 자동으로 숨길 수 있습니다. 작업 표시줄을 우클릭해 설정에 들어간 뒤, '시스템 트레이 아이콘'에서 **AIAgentsUsageMonitor**를 켬(On)으로 바꿔 주세요.

---

## ⚙️ 설정 (선택 사항)

기본 설정 그대로 써도 됩니다. 바꾸고 싶은 값이 있다면 실행 파일과 같은 위치에 `usage-monitor-settings.json`을 만들어 해당 항목만 적으면 됩니다.

```json
{
  "tray_provider": "codex",
  "bar_fg": "#00cc66",
  "bar_fg_warn": "#ff6600"
}
```

`tray_provider`는 트레이 아이콘과 툴팁, 임계값 알림이 어느 쪽을 따라갈지 정합니다. 기본값 `claude`는 팝업의 Codex 화면을 열었을 때만 Codex를 조회하고, `codex`로 두면 팝업을 닫아 둔 동안에도 Codex 한도를 계속 조회합니다. 전체 설정 목록은 [docs/configuration.md](docs/configuration.md)에, 이벤트 명령은 [docs/event-commands.md](docs/event-commands.md)에 있습니다.

---

## 📄 라이선스

MIT

*이 프로젝트는 커뮤니티에서 독립적으로 만든 오픈소스 앱이며, Anthropic 또는 OpenAI의 공식 지원을 받지 않습니다.*
