# 개인정보 처리방침

**AI 에이전트 사용량 모니터**는 사용자의 Claude와 Codex 사용량을 확인하는 로컬 데스크톱 애플리케이션입니다.

## 데이터 수집

이 애플리케이션은 어떠한 개인정보도 **수집하거나, 저장하거나, 외부로 전송하지 않습니다.**

## 네트워크 통신

이 애플리케이션이 직접 보내는 HTTP 요청은 Claude 사용량을 조회하기 위한 `api.anthropic.com` 한 곳뿐입니다.

Codex 화면을 보고 있는 동안에는 설치되어 있는 네이티브 Codex CLI 또는 IDE 확장의 실행 파일을 앱 서버로 실행한 뒤,
로컬 표준 입출력을 통해 계정과 한도 정보를 요청합니다. 이때 OpenAI 서비스와의 인증 및 통신은 Codex가 자체적으로
처리합니다. 이 자식 프로세스에 대해서는 애널리틱스와 OpenTelemetry 내보내기를 꺼 둡니다.

모니터가 프롬프트나 모델 대화 내용을 전송하는 일은 없습니다.

## 자격 증명

이 애플리케이션은 로컬 Claude CLI 설정 파일(`~/.claude/.credentials.json`)에 이미 저장되어 있는 Claude OAuth
토큰을 읽습니다. 이 토큰은 다음과 같이 취급됩니다.

- Anthropic API 인증을 위한 HTTP Authorization 헤더에만 사용됩니다
- 기록하거나, 다른 곳에 저장하거나, 복사하거나, 제3자에게 전송하지 않습니다

Codex 자격 증명은 읽지 않습니다. Codex 인증은 Codex가 직접 처리합니다.

## 로컬 저장소

Codex 화면은 `CODEX_HOME`(설정하지 않았다면 `~/.codex`) 아래에 이미 존재하는 `sessions/**/*.jsonl`과
`archived_sessions/**/*.jsonl` 파일을 읽습니다. 이 과정에서 메모리에 남기는 것은 모델 이름과 시각, 토큰 수치뿐입니다.
로컬 토큰 기록은 네트워크로 전송되지 않습니다.

계정 한도 그래프를 그릴 때는 Codex의 `account/read`와 `account/rateLimits/read` 프로토콜 메서드를 사용합니다.
여기에서 얻은 이메일과 플랜, 한도 정보는 모두 메모리에만 남습니다.

모니터 자신은 파일을 쓰지 않습니다. 다만 위임받아 실행된 Codex 프로세스는 Codex가 평소 동작하는 방식대로
자신에게 설정된 홈 디렉터리 아래에 로그나 데이터베이스, 갱신된 자격 증명을 기록할 수 있습니다.

모니터가 다루는 모든 사용량 데이터는 메모리에만 유지되며 애플리케이션을 종료하면 사라집니다. 선택 사항인 설정
파일(`usage-monitor-settings.json`)은 읽기 전용으로만 사용합니다.

윈도우 레지스트리에는 두 개의 값이 기록되며, 둘 다 `HKEY_CURRENT_USER` 아래에 있습니다.

- `Software\Classes\AppUserModelId\deuxdoom.UsageMonitorForClaude` - 알림 헤더에 표시되는 앱 이름과
  아이콘입니다. 시작할 때마다 다시 등록합니다.
- `Software\Microsoft\Windows\CurrentVersion\Run` - 자동 실행 항목입니다. 트레이 메뉴에서 자동 실행을 켤 때만
  기록하며, 다시 끄면 삭제합니다.

그리고 1.80.0 버전을 처음 실행할 때 한 번, 다음 키 하나를 삭제합니다.

- `Software\Classes\AppUserModelId\JensDuttke.UsageMonitorForClaude` - 애플리케이션 이름을 바꾸기 전에
  사용하던 알림 식별자입니다. 이제 아무것도 참조하지 않으므로 그대로 두지 않고 지웁니다. 삭제는 시작할 때마다
  시도하지만 키가 이미 없으면 아무 일도 하지 않으며, 삭제가 거부되는 환경에서는 그대로 넘어가고 애플리케이션은
  정상적으로 실행됩니다.

## Claude Code 설치

OAuth 토큰이 만료되면 이 애플리케이션은 `claude update` 명령을 실행합니다. 그러면 Claude Code CLI가 자신의
자격 증명 파일에서 토큰을 갱신합니다. 이 명령의 부수적인 결과로 더 새로운 Claude Code 버전이 설치될 수 있습니다.
시스템의 다른 소프트웨어는 변경하지 않습니다.

## 제3자 서비스

이 애플리케이션은 애널리틱스, 트래킹, 광고, 텔레메트리 등 어떠한 서비스와도 연동되지 않습니다.

## 문의

이 개인정보 처리방침에 관해 궁금한 점이 있다면 아래 주소에 이슈를 남겨 주세요.
https://github.com/deuxdoom/usage-monitor-for-claude/issues
