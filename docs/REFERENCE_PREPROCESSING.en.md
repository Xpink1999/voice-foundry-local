[简体中文](REFERENCE_PREPROCESSING.md) | **English** | [日本語](REFERENCE_PREPROCESSING.ja.md) | [한국어](REFERENCE_PREPROCESSING.ko.md)

# Reference audio preparation

Open Create → Voice design & library → Create voice. Voice and reference libraries have their own entries; text design and saved-recording processing stay inside creation. Save references, set up a voice and continue directly to narration. See the [WebUI guide](WEBUI.en.md).

Recording analysis and generation run locally. Uploaded audio is not sent to a third-party service.

## Reference clips

Quick reference setup accepts up to 10 recordings per upload and processes them separately. Listen to the candidates, select Save to reference clips, name each clip and optionally add a scene, then choose Save selected clips. You can save clips before creating a voice. Originals are retained and recordings are never joined.

In Reference clips, search by name, scene, tags or notes; listen and edit annotations. Add several selected clips to one voice or move them to the recoverable trash. The voice editor reuses its saved default reference without another upload. Scene references let you keep alternatives and choose a new default. This affects future narration only; it does not train a model, combine recordings or guarantee better quality.

Use a clear, stable everyday recording as the default, with separate clips for soft speech, excitement or narration. Each generation uses one clip. A changed default needs listening confirmation again. Existing audio and submitted tasks retain their original reference.

## Workflow

1. Upload an authorized recording and enter its source and permission details. The browser previews duration. The server retains the original bytes and SHA-256 and creates a 16 kHz mono analysis copy. Limits are 200 MB and 0.5–1,800 seconds per recording.
2. A separate CPU queue runs voice activity detection, approximate speaker grouping, music/noise classification and transcription. Recommended references are 5–30 seconds. Default candidates are at most about 20 seconds, with up to 24 candidates, favoring longer usable clips. The original remains available to listen to and download.
3. Filter by temporary speaker labels such as S1/S2, listen and select clips to save. Each clip is one continuous interval of the recording. Short pauses are kept; long silence and speaker changes split clips. Nonadjacent intervals are not joined. Unselected candidates do not enter the usable reference library.
4. Edit the automatic transcript; version history is retained. Confirm it only after checking it yourself. Hi-Fi previews can use an unconfirmed transcript, but metadata remains marked as draft.
5. Create a voice with a primary reference and optional alternatives with scene labels. Generation uses the primary reference by default or one selected alternative, without automatically combining references. Explicitly selected, checked clips can form a new composite reference draft.
6. Compare at least two saved references for the same character. The system clones the same text with default seeds 42 and 84 and ranks reference similarity, consistency across seeds, ASR character error and source quality. Apply the recommendation explicitly to create a new draft voice version. Other references and scene labels stay intact. If the voice changed during comparison, applying the old recommendation is rejected.

Comparison samples and Hi-Fi results remain pending review. Scores and recommendations do not approve audio.

Hi-Fi follows the reference delivery and disables extra style descriptions. The voice's stored description remains available for reference mode. Appending a style to `prompt_text` can cause it to be spoken, so explicit Hi-Fi `style` is rejected. Metadata records why a default description was ignored. Use reference mode for extra emotion or speed guidance; control remains approximate.

## Analysis tools

| Function | Local implementation / source | License and limits |
|---|---|---|
| Speech boundaries | [Silero VAD](https://github.com/snakers4/silero-vad) 6.2.3, ONNX | MIT. Music can trigger false detections. |
| Transcription | [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) 1.2.1 + [small](https://huggingface.co/Systran/faster-whisper-small) | MIT. CPU int8, multilingual; short/noisy clips can produce hallucinations. |
| Music/noise hints | [AST AudioSet](https://huggingface.co/MIT/ast-finetuned-audioset-10-10-0.4593) | BSD-3-Clause. 10-second windows plus clip checks; sigmoid scores are not calibrated probabilities. |
| Speaker grouping | [Resemblyzer](https://github.com/resemble-ai/Resemblyzer) | Apache-2.0. Cosine clustering; 1–2.5-second voice windows. S1 labels apply only within this recording. |
| Silence, clips and ranking | Voice Foundry | 20 ms RMS, −50 dBFS silence threshold; not semantic analysis. Formula: reference_analysis.py. |

Speaker grouping follows sequential changes in voice and is not identity verification. Emotion, phrase or language changes can split one speaker into several groups; similar voices can also be confused. Two-speaker overlap separation, music removal and denoising are available through the quick workflow, which retains original candidates for comparison. See [audio processing](AUDIO_RESTORATION.en.md). Output tracks have anonymous labels and may contain leakage, residual sound or distortion. No warning does not guarantee clean audio.

Reference comparison uses this score:

`0.45 × reference cosine similarity + 0.25 × (1 − clipped character error rate) + 0.20 × cross-seed cosine similarity + 0.10 × source quality`

ASR varies on short lines; languages other than Chinese, accents and specialist vocabulary may affect ranking. The score narrows the listening choices; it is not a general voiceprint or quality certification.

Character comparison normalizes punctuation, case, full/half-width characters and simplified/traditional Chinese using [OpenCC Python](https://github.com/yichen0831/opencc-python) 0.1.7 (Apache-2.0). Original text and raw transcripts are unchanged.

## Files and configuration

Originals are stored at `data/recordings/<UUID>/original.<extension>`. Each analysis attempt has its own `analysis-*` directory, request, progress, log and result. Failure or cancellation preserves the original; retry creates a new attempt.

Candidate WAVs currently use the 16 kHz mono analysis copy. Original samples and bytes are unchanged. To preserve the bandwidth of an already trimmed reference, use `upload-reference --direct` for 0.5–90 seconds of audio. Hi-Fi is a cloning mode, not automatic bandwidth restoration.

Saved `references` records point to individual WAVs and retain source recording/time range, SHA-256, authorization, transcript history, quality and pinned model provenance. Voice versions snapshot the reference collection; each generated result freezes the single reference actually used.

Shared weights are in `models/faster-whisper-small`, `models/AST-AudioSet` and `models/Resemblyzer`. Each `provenance.json` records revision, license and file hashes. Resemblyzer source is pinned in `vendor/Resemblyzer`; the Silero ONNX model comes with the isolated environment's package. The installer runs `scripts/download_reference_models.py` to fetch pinned models. Dependencies remain in the platform's `.venv`.

`config/platform.json` → `reference_preprocessing` configures model paths, CPU threads, queue limits, timeouts, clip lengths and speaker/detection thresholds. Back up configuration and database before changing settings; restart the service afterward.

Each analysis uses a CPU subprocess that exits when finished, without using CUDA VRAM. TTS has a separate GPU queue; the separation and cleanup stage described in the audio processing guide uses the GPU. Stopping the service stops analysis subprocesses. Interrupted analysis is marked failed after restart and can be retried.

## CLI and MCP

After optional global CLI registration, run commands as needed and replace ID strings with returned IDs. Only confirm rights when you have the required permission.

~~~powershell
$voiceId = "VOICE_ID"
$referenceId = "REFERENCE_ID"
$recordingId = "RECORDING_ID"
voice upload-reference .\recording.wav --source "My recording" --authorization "Permission for this use" --rights-confirmed
voice recordings
voice recording $recordingId
voice generate --text "This is a voice sample." --voice-id $voiceId --reference-id $referenceId --clone-mode hifi --wait
~~~

`upload-reference` runs automatic processing by default and returns a recording task ID. `--analyze-only` limits it to analysis; `--direct` uploads a short prepared reference directly. Clip saving and comparison use the WebUI, REST or MCP.

MCP provides `voice_upload_recording`, `voice_recording`, `voice_save_reference_clips`, `voice_compare_references` and `voice_reference_comparison`. Generation accepts `reference_id` and `clone_mode`; voices store `reference_ids` and `reference_scenarios`. Reconnect MCP after updating. Apply recommendations and approve audio explicitly in the WebUI.

## Validation

Core tests use temporary databases and a test engine. Real-model checks run separately. The public repository includes no historical recordings or screenshots. See [testing scope](TESTING.md) (Chinese).

## Related guides

[README](../README.en.md) · [Installation](INSTALL.en.md) · [Long-form narration](LONGFORM.en.md) · [Audio processing](AUDIO_RESTORATION.en.md) · [Maintenance](MAINTENANCE.en.md)

## Speaker tracking and manual assembly

In Create voice, choose Process a saved recording, select a recording and organize it by speaker. Starting from an existing processing record reuses its music-removed speech when available. Originals and earlier results are kept.

Enter the known speaker count, or leave it blank for detection. The system labels speaker activity, builds voice anchors from solo speech, and separates only overlapping regions. Speaker IDs apply to this run only. Similarity scores are not identity probabilities. Ambiguous separated clips remain available for review.

Listen to each speaker, enter a name, and select individual clips to save to the reference library. Each clip retains source offsets, processing history and an unconfirmed transcript. Saving does not approve the audio or confirm the transcript. Clips under five seconds can be kept as alternatives.

Long gaps are removed from individual clips; short pauses default to 120 ms. Speech is not assembled automatically. Select clips and choose Combine selected in source order, with a gap of 0–1000 ms. Listen to or download the new file. Original clips remain separate, and the combined file is not automatically used for cloning. Compare original and speaker timeline to check assignments and omissions.

### Optional tracking model setup

Accept the access conditions on the [Community-1 model page](https://huggingface.co/pyannote/speaker-diarization-community-1), then authorize local downloads through the official Hugging Face login flow. Keep access tokens out of project configuration and Git. From the platform folder, run:

```powershell
.\.venv\Scripts\python.exe scripts/setup_speaker_tracking.py
```

The script creates `runtime/diarization-env`, reuses the platform's compatible PyTorch, and downloads and verifies a pinned model revision. Inference uses local files; stopping a task ends its worker. Recordings are not uploaded. This optional environment depends on the platform's `.venv`; do not move it alone. Paths and filtering parameters belong to the `speaker_tracking` configuration section.


## Reference and narration workflow

[Reference and narration workflow](WORKFLOW_GUIDE.en.md)
