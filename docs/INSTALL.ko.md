[简体中文](INSTALL.md) | [English](INSTALL.en.md) | [日本語](INSTALL.ja.md) | **한국어**

# 설치와 실행

처음에는 [WebUI 사용 가이드](WEBUI.ko.md)에서 새 탐색 메뉴와 생성·검토·내보내기 흐름을 확인하세요.

[README로 돌아가기](../README.ko.md)

계속 사용할 설치 폴더를 선택하세요. 각 프로젝트는 이곳의 서비스와 모델을 공유합니다.

## 준비 사항

- Windows 11 x64, [Git](https://git-scm.com/download/win), [uv](https://docs.astral.sh/uv/getting-started/installation/), 정상 작동하는 NVIDIA 드라이버.
- 현재 추론 환경은 Python 3.11.16과 PyTorch / torchaudio 2.8.0 cu128이며 주로 RTX 4090에서 검증했습니다. CUDA 런타임은 PyTorch wheel에 포함되므로 같은 버전의 CUDA Toolkit을 별도로 설치할 필요가 없습니다. 다른 GPU와 CPU 추론은 같은 수준으로 검증하지 않았습니다.
- [FFmpeg 공식 사이트에 안내된 배포처](https://ffmpeg.org/download.html)에서 설치하고 PATH에 추가하세요. 형식 변환, 후처리, 고급 오디오 처리에 필요합니다. 빌드별로 라이선스가 다를 수 있습니다. [제삼자 고지](../THIRD_PARTY_NOTICES.md)(중국어)를 확인하세요.
- PyTorch DLL 로드 오류가 나면 [Microsoft Visual C++ v14 x64 런타임](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)을 설치하세요. Windows 시스템 의존성이며 플랫폼 설치 스크립트가 자동으로 설치하거나 변경하지 않습니다.
- 다운로드에는 인터넷 연결이 필요합니다. 전체 설치에는 30 GiB 이상 여유 공간을 권장합니다.

## 처음 설치

GitHub에서 **Code → Download ZIP**을 선택하고 ZIP의 **압축 풀기**를 실행합니다. `pyproject.toml`과 `install-voice.cmd`가 있는 폴더를 여세요. 압축 파일 안에서 실행하지 마세요. Git으로 받을 수도 있습니다.

~~~powershell
git clone https://github.com/Xpink1999/voice-foundry-local.git
cd voice-foundry-local
~~~

Program Files와 동기화 폴더를 피하고, 현재 계정이 쓸 수 있는 위치를 선택하세요. 설치 후 폴더를 옮기면 가상 환경을 다시 만들어야 합니다. 관리자 권한, 기존 Python, CUDA Toolkit, Codex, 목소리나 데이터베이스는 필요하지 않습니다.

`install-voice.cmd`를 더블클릭하거나 해당 폴더에서 PowerShell을 엽니다.

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
~~~

전체 설치는 Python 3.11.16, CUDA PyTorch, 고정된 추론 소스와 모델 7세트를 내려받습니다. 가져오기와 CUDA 확인, 코어 테스트 후 서비스를 시작합니다. 가중치는 약 7.1 GiB, PyTorch 다운로드는 약 3.2 GiB입니다. 환경, 압축 해제와 캐시를 포함해 30 GiB 이상 여유 공간을 권장합니다. 새 설치의 목소리, 프로젝트, 작업 목록은 비어 있습니다.

[WebUI](http://127.0.0.1:8961/)에서 한 문장과 목소리 설명을 입력하고 생성하세요. 첫 합성은 모델을 불러오므로 화면을 여는 것보다 오래 걸립니다. 결과는 직접 듣고 승인해야 합니다.

CUDA와 모델을 받지 않고 화면, 데이터베이스와 기본 흐름만 확인하려면:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -CoreOnly -NoStart
~~~

`-CoreOnly`에는 Git, NVIDIA GPU, FFmpeg가 필요하지 않습니다. 빈 화면은 열 수 있지만 음성 생성이나 녹음 처리는 할 수 없습니다. 나중에 옵션 없이 다시 실행하면 전체 설치를 진행합니다. `-SkipModels -NoStart`는 가중치만 생략하며 CUDA 의존성과 추론 소스는 설치합니다.

Python, uv 상태와 캐시는 `runtime/`(모델 캐시는 `cache_dir`, 기본값 `runtime/model-cache`), 독립 환경은 `.venv`, 소스는 `vendor/`, 모델은 `models/`, 데이터베이스와 오디오는 `data/`에 저장합니다. 다른 설치의 환경이나 녹음을 읽지 않으며 사용자 PATH와 Codex 설정을 바꾸지 않습니다.

모델 출처와 리비전은 `config/model-sources.json`에 고정되어 있습니다. 크기와 해시를 확인하고 `provenance.json`에 기록합니다. 다운로드가 끊기면 다시 실행하세요. 정상 파일은 유지합니다.

## 확인과 문제 해결

- 로그: `runtime/install.log`. 확인 결과: `runtime/install-check.json`. 실패하면 0이 아닌 종료 코드를 반환합니다. 원인을 고친 뒤 다시 실행하고 `data/`는 보존하세요.
- uv나 Git을 찾지 못하면 설치 후 터미널을 다시 여세요. ZIP으로 받은 전체 설치도 추론 소스를 받으려면 Git이 필요합니다. CoreOnly는 필요 없습니다.
- 설치 전에 실행하면 시작 파일에 설치 명령을 안내합니다.
- 다른 설치가 같은 포트를 쓰면 해당 서비스를 종료하거나 이 폴더의 `config/platform.json`에서 `port`를 바꾸세요. 로컬 시작, 종료와 상태 확인은 설치 위치를 검사합니다.
- CUDA를 쓸 수 없으면 NVIDIA 드라이버를 갱신하세요. CUDA 런타임은 PyTorch에 포함됩니다. [버전별 설치 안내](https://pytorch.org/get-started/previous-versions/)도 확인하세요.
- FFmpeg가 없으면 WAV 텍스트 음성화는 가능하지만 녹음 업로드, 인코딩 내보내기, 무음 자르기, 음량 처리와 고급 분리에 필요합니다. 설치 후 터미널을 다시 열거나 설정의 `ffmpeg`에 실행 파일의 절대 경로를 넣으세요.
- uv 버전 링크의 권한 오류는 내려받은 로컬 Python을 검사하고 정상일 때만 계속합니다. 시스템 Python으로 대체하지 않습니다. 다운로드나 검사에 실패하면 설치를 중단합니다.

전체 설치를 다시 확인하려면:

~~~powershell
.venv\Scripts\python.exe scripts\check_install.py --profile inference --models
~~~

CoreOnly는 `--profile core`를 사용합니다. 화면 표시, 의존성 확인과 실제 음성 생성은 별도로 검증합니다.

## 일상적인 사용

루트의 `start-voice.cmd`(시작), `stop-voice.cmd`(종료), `check-health.cmd`(상태 확인)를 사용하거나 설치 폴더에서 다음 명령을 실행합니다.

~~~powershell
bin\voice.cmd start
bin\voice.cmd stop
bin\voice.cmd health
bin\voice.cmd unload
~~~

각 줄은 시작, 종료, 상태 확인, 모델 해제를 위한 별도 명령입니다. 필요한 한 줄만 실행하세요. 모델은 기본적으로 30초 동안 사용하지 않으면 해제됩니다. 수동 해제도 이 플랫폼의 모델만 대상으로 하며 다른 앱의 GPU 작업을 종료하지 않습니다. 브라우저를 닫아도 백그라운드 작업은 계속됩니다. Windows 서비스나 시작 프로그램은 등록하지 않습니다.

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
