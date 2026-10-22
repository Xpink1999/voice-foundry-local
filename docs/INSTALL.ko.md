[简体中文](INSTALL.md) | [English](INSTALL.en.md) | [日本語](INSTALL.ja.md) | **한국어**

# 설치와 실행

[README로 돌아가기](../README.ko.md)

계속 사용할 설치 폴더를 선택하세요. 각 프로젝트는 이곳의 서비스와 모델을 공유합니다.

## 준비 사항

- Windows 11, Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), 정상 작동하는 NVIDIA 드라이버.
- 현재 추론 환경은 Python 3.11.16과 PyTorch / torchaudio 2.8.0 cu128이며 주로 RTX 4090에서 검증했습니다. CUDA 런타임은 PyTorch wheel에 포함되므로 같은 버전의 CUDA Toolkit을 별도로 설치할 필요가 없습니다. 다른 GPU와 CPU 추론은 같은 수준으로 검증하지 않았습니다.
- [FFmpeg 공식 사이트에 안내된 배포처](https://ffmpeg.org/download.html)에서 설치하고 PATH에 추가하세요. 형식 변환, 후처리, 고급 오디오 처리에 필요합니다. 빌드별로 라이선스가 다를 수 있습니다. [제삼자 고지](../THIRD_PARTY_NOTICES.md)(중국어)를 확인하세요.
- 다운로드에는 인터넷 연결이 필요합니다. 모델과 환경에 수 GB, 캐시에 추가 디스크 공간이 필요합니다.

## 처음 설치

소스 폴더에서 PowerShell을 열고 실행합니다.

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
~~~

Python은 `runtime/python`에, 독립 환경은 `.venv`에 설치하며 고정된 의존성을 사용합니다. 추론 소스는 `vendor/`, 모델은 `models/`, 다운로드 캐시는 `runtime/`에 저장합니다. 이후 의존성을 확인하고 코어 테스트를 실행한 뒤 서비스를 시작합니다.

[WebUI](http://127.0.0.1:8961/)를 엽니다. 처음 모델을 불러올 때는 시간이 걸립니다. 음성 생성과 녹음 처리는 로컬에서 실행됩니다.

모델 출처와 리비전은 `config/model-sources.json`에 고정되어 있습니다. 다운로드 이어받기와 해시 검증을 지원하며 각 모델의 `provenance.json`에 다운로드 기록을 남깁니다. 모델을 변경할 때는 출처, 라이선스, 검증 기록도 함께 갱신하세요.

모델 다운로드와 서비스 시작을 생략하고 의존성만 설치하려면 다음을 실행합니다.

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -SkipModels -NoStart
~~~

소스 확인과 코어 테스트에 사용할 수 있습니다. 실제 음성 생성에는 모델이 필요합니다. 설치 스크립트는 사용자 PATH나 Codex 설정을 자동 변경하지 않습니다.

## 일상적인 사용

루트의 `start-voice.cmd`(시작), `stop-voice.cmd`(종료), `check-health.cmd`(상태 확인)를 사용하거나 설치 폴더에서 다음 명령을 실행합니다.

~~~powershell
bin\voice.cmd start
bin\voice.cmd stop
bin\voice.cmd health
bin\voice.cmd unload
~~~

각 줄은 시작, 종료, 상태 확인, 모델 해제를 위한 별도 명령입니다. 필요한 한 줄만 실행하세요. 모델은 기본적으로 5분 동안 사용하지 않으면 해제됩니다. 수동 해제도 이 플랫폼의 모델만 대상으로 하며 다른 앱의 GPU 작업을 종료하지 않습니다. 브라우저를 닫아도 백그라운드 작업은 계속됩니다. Windows 서비스나 시작 프로그램은 등록하지 않습니다.

## 전역 명령과 MCP

선택 사항입니다. 다음 스크립트를 사용하려면 Codex CLI(`codex` 명령)가 설치되어 정상 작동해야 합니다.

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-global.ps1
~~~

현재 설치의 `bin` 폴더를 사용자 PATH에 추가하고 사용자 수준 Codex MCP 서버를 등록합니다. 변경 전에 PATH와 기존 Codex 설정을 `data/backups/`에 백업합니다. 백업은 로컬에만 보관하세요.

새 터미널을 열면 `voice`를 사용할 수 있습니다. Codex를 다시 시작하거나 MCP에 재연결하면 도구를 찾을 수 있습니다. 전역 CLI만 필요하면 스크립트 대신 설치된 `bin`의 전체 경로를 사용자 PATH에 직접 추가하세요. WebUI와 API는 독립적으로 사용할 수 있습니다.

## 설정과 원격 접속

경로, 모델, 큐, 서비스 설정은 `config/platform.json`에 있습니다. 모델과 데이터의 상대 경로는 설치 폴더를 기준으로 합니다. CLI 입력과 내보내기의 상대 경로는 명령을 실행한 작업 폴더를 기준으로 합니다.

기본 수신 주소는 `127.0.0.1`입니다. 원격 접속에는 `host`, `allowed_hosts`를 명시하고 `token_env`가 지정한 서비스 환경 변수에 토큰을 설정해야 합니다. 토큰이 없으면 원격 시작을 거부합니다. HTTP는 Bearer 인증을 사용하며 WebUI는 토큰 입력 후 세션을 만듭니다. 인터넷에 노출하려면 신뢰할 수 있는 TLS 역방향 프록시도 필요합니다. 인증 정보를 소스에 적거나 커밋하지 마세요.

백업과 복구는 [유지 관리 안내](MAINTENANCE.ko.md)를 참고하세요.
