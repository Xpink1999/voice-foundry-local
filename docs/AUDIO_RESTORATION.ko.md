[简体中文](AUDIO_RESTORATION.md) | [English](AUDIO_RESTORATION.en.md) | [日本語](AUDIO_RESTORATION.ja.md) | **한국어**

# 오디오 처리와 빠른 참조

## 빠른 작업 흐름

목소리 디자인·라이브러리에서 빠른 참조 만들기를 선택합니다. 권한이 있는 녹음을 올리면 음성 분리, 음악·잡음 제거, 구간 추천을 수행합니다. 들어 본 뒤 인물 이름을 입력해 저장하세요. 모델 세부 설정은 필요하지 않습니다. 권장 길이는 5~30초입니다. 5초 미만에는 경고하며 무음을 붙여 길이를 맞추지 않습니다.

원본 녹음은 그대로 둡니다. 추천은 원본과 처리 결과를 함께 비교하며 처리본이 항상 낫다고 보지 않습니다. 다른 후보를 펼쳐 직접 고를 수 있습니다. 참조는 따로 저장하고 한 번 생성할 때 한 구간만 사용합니다. 기존 목소리에 장면별 참조를 추가해도 기본 참조와 확인 상태를 유지합니다.

화면에는 한 번에 한 작업 영역을 표시합니다.

- 빠른 참조 만들기: 녹음에서 시작하는 기본 작업.
- 목소리 라이브러리: 검색, 편집, 재생. 참조 비교는 선택 사항.
- 목소리 디자인: 설명으로 샘플을 만들고 바로 참조 준비로 전송.
- 고급 오디오 처리: 음악 제거, 두 화자 분리, 잡음 제거를 골라 원본과 비교하고 최종 트랙을 구간 선택으로 전송.

저장하면 목소리 초안을 만듭니다. 전사문을 교정하고 명시적으로 확인하며 생성 결과도 직접 듣고 승인해야 합니다.

## 로컬 모델

| 처리 | 고정 가중치·리비전 | 추론 코드·리비전 | 출력 |
|---|---|---|---|
| 음악 제거 | [KimberleyJSN/melbandroformer](https://huggingface.co/KimberleyJSN/melbandroformer), ac9b0614ab3cd7f77219e18ba494dfd93956c348, MIT | [ZFTurbo/Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training), 6fdad13686bb7e84d029ec66f9dbe76e65c93ebf, MIT | 44.1 kHz 스테레오 음성과 배경 |
| 겹친 음성 분리 | [MossFormer2_SS_16K](https://huggingface.co/alibabasglab/MossFormer2_SS_16K), 407cb030cd66340918ebb6c8cc63b18f8592cdbe, Apache-2.0 | [ClearerVoice-Studio](https://github.com/modelscope/ClearerVoice-Studio), 6b3774dc79c46ae8bed2a4fa5f706f0ac8c75c61, Apache-2.0 | 16 kHz 익명 음성 두 개 |
| 잡음 제거 | [MossFormer2_SE_48K](https://huggingface.co/alibabasglab/MossFormer2_SE_48K), eff8c97925c8bec812af707814b3e5d777fd4503, Apache-2.0 | [ClearerVoice-Studio](https://github.com/modelscope/ClearerVoice-Studio), 6b3774dc79c46ae8bed2a4fa5f706f0ac8c75c61, Apache-2.0 | 48 kHz 모노 음성 |

가중치는 합계 약 1.8 GB이며 프로젝트 간 공유합니다. 모델의 `provenance.json`에 출처, 리비전, 라이선스 표시, 해시를 남깁니다. `runtime/source-provenance.json`은 추론 소스와 해시를 기록합니다. 모델 라이선스가 개인 목소리 사용 권한을 주지는 않습니다. [제삼자 고지](../THIRD_PARTY_NOTICES.md)와 [자료](../LICENSES/README.md)는 중국어입니다.

상위 학습 경로에 Windows 예약 이름 AUX가 있어 설치 스크립트는 고정 Git 객체에서 필요한 추론 파일을 추출합니다. 추론 구현을 바꾸거나 학습 환경을 설치하지 않습니다. 코드 허가가 불명확한 대체 소스와 상업 제한 논쟁이 있는 Demucs 가중치는 통합하지 않았습니다.

## 한계와 비교

두 화자 분리는 익명의 트랙 두 개를 만들며 신원을 확인하지 않습니다. 세 명 이상, 긴 무음, 강한 잔향, 화자 교대에서는 혼입이나 트랙 뒤바뀜이 생길 수 있습니다. 창의 겹침 구간으로 순서를 맞추지만 모든 변화를 없애지는 못합니다. 원본과 비교하세요. 음악·잡음 제거도 목소리를 바꾸거나 잔여 소리와 왜곡을 만들 수 있습니다.

긴 녹음은 제한된 창과 크로스페이드로 끝부분과 길이를 유지한 연속 트랙을 재구성합니다. 같은 트랙의 시간 복원이며 서로 다른 참조를 합치는 기능이 아닙니다. 혼합음의 최소제곱 추정으로 각 트랙의 음량을 복원해 임의 증폭을 피합니다. 피크 임계값을 넘을 때만 감쇠하며 게인 정책을 기록합니다. 처리 전후 음량은 다를 수 있습니다.

추천은 품질, 음성 비율, 길이, ASR, 근사 화자 지표를 조합합니다. 사용할 구간은 들어서 판단합니다. Hi-Fi는 선택한 단일 구간과 해당 구간의 교정된 전사문을 쓰며 다른 구간의 대사를 빌려오지 않습니다.

## 작업과 복구

처리와 TTS는 GPU 배타 잠금을 공유합니다. 처리 전에 이 플랫폼의 TTS 모델을 해제하며 처리 하위 프로세스가 종료되면 VRAM을 반환합니다. 다른 앱은 종료하지 않습니다. CPU 음성 탐지, 전사, 품질 분석은 별도 큐입니다.

설정은 `config/platform.json`의 `audio_processing`에 있으며 장치, CPU 스레드, 큐, 시간 제한, 창 길이를 포함합니다.

`data/recordings`는 원본과 분석을, `data/audio-processing/<작업 UUID>`는 처리 전 WAV, 중간 단계, 최종 출력을 보관합니다. 출력마다 UUID, SHA-256, 샘플레이트, 채널, 역할, 원본·상위 작업 출처를 기록합니다. 같은 출력의 재가져오기는 녹음 기록을 재사용합니다.

취소·실패·시간 초과에도 원본은 남습니다. 중단한 처리는 실패로 표시하고 분석만 기존 분리 결과를 사용해 다시 시도할 수 있습니다. Windows 진행 파일 쓰기는 짧게 재시도하며 진행 알림 실패가 분석 성공을 취소하지 않습니다. 최종 결과 파일은 별도로 저장합니다.

## CLI와 API

선택 사항인 전역 CLI 등록 후 ID를 반환된 값으로 바꾸고 필요한 명령을 실행하세요. 권리 확인 옵션은 실제 권한이 있을 때만 사용합니다.

~~~powershell
$recordingId = "RECORDING_ID"
$processingId = "PROCESSING_ID"
voice upload-reference .\recording.wav --source "My recording" --authorization "Permission for this use" --rights-confirmed
voice process-audio $recordingId --operations remove_music separate denoise
voice processing $processingId
~~~

옵션은 `voice <command> --help`로 확인합니다. MCP는 `voice_upload_recording`, `voice_process_recording`, `voice_audio_processing`, `voice_create_from_reference`를 제공합니다. 업데이트 후 재연결하세요. 모든 작업 폴더는 같은 로컬 HTTP 서비스와 모델을 사용합니다.

경로는 `/api/v1` 아래에 있습니다. 스키마는 실행 중인 `/docs`와 `/openapi.json`을 참고하세요.

| 경로 | 용도 |
|---|---|
| POST /recordings | multipart: file, source, authorization, rights_confirmed, smart_reference. 기본값은 HTTP false, WebUI/CLI/MCP true. |
| GET /recordings/{id} | 상태, 구간, 추천, 분석. |
| POST /recordings/from-result | result_id로 디자인 샘플 등록. |
| GET /audio-processing/capabilities | 사용 가능한 처리. |
| POST /audio-processing | recording_id, operations, analyze_outputs. |
| GET /audio-processing or /audio-processing/{id} | 작업 목록·상세. |
| POST /audio-processing/{id}/cancel | 작업 취소. |
| GET /audio-processing/{id}/before | 처리 전 오디오. |
| GET /audio-processing/{id}/outputs/{output_id} | 출력 오디오. |
| POST /audio-processing/{id}/analyze-output | output_id를 참조용으로 분석. |
| POST /reference-voices | reference_id와 name으로 초안 생성. voice_id와 scenario로 추가. |

## 관련 안내

[README](../README.ko.md) · [설치](INSTALL.ko.md) · [장문 음성 제작](LONGFORM.ko.md) · [참조 오디오](REFERENCE_PREPROCESSING.ko.md) · [유지 관리](MAINTENANCE.ko.md)
