[简体中文](AUDIO_RESTORATION.md) | **English** | [日本語](AUDIO_RESTORATION.ja.md) | [한국어](AUDIO_RESTORATION.ko.md)

# Audio processing and quick references

The voice workspace has three entries: Create voice, Voice library and Reference clips. Voice design and advanced processing sit within creation. See the [WebUI guide](WEBUI.en.md) for screenshots.

## Quick workflow

Upload an authorized recording → analyze speakers and speech clips → listen and select → name and save clips → create a voice or add a scene reference → start dubbing. When speaker tracking is available, clips are organized by speaker. Music removal and denoising depend on detected problems and installed models; they are not forced on every recording. Missing models are listed before submission.

Recommended references are 5–30 seconds. Shorter clips receive a warning; silence is not added to meet the target. Originals and previous results remain available for comparison. Processing does not always improve a recording.

References are stored separately. To combine short utterances, explicitly confirm that selected clips belong to the same person, then check speech duration, duplicate coverage and the final transcript before saving a composite reference. Different speakers are never combined automatically. Adding a scene reference preserves the existing primary reference. After saving clips, continue to voice setup or keep them in the reference library.

Recommendations are not approval. Confirm the transcript and listen to generated results before approving them. See the [workflow guide](WORKFLOW_GUIDE.en.md).

## Local models

| Operation | Pinned weights / revision | Inference code / revision | Output |
|---|---|---|---|
| Music removal | [KimberleyJSN/melbandroformer](https://huggingface.co/KimberleyJSN/melbandroformer), ac9b0614ab3cd7f77219e18ba494dfd93956c348, MIT | [ZFTurbo/Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training), 6fdad13686bb7e84d029ec66f9dbe76e65c93ebf, MIT | 44.1 kHz stereo vocals and background |
| Overlapping voices | [MossFormer2_SS_16K](https://huggingface.co/alibabasglab/MossFormer2_SS_16K), 407cb030cd66340918ebb6c8cc63b18f8592cdbe, Apache-2.0 | [ClearerVoice-Studio](https://github.com/modelscope/ClearerVoice-Studio), 6b3774dc79c46ae8bed2a4fa5f706f0ac8c75c61, Apache-2.0 | 16 kHz, two anonymous voices |
| Denoising | [MossFormer2_SE_48K](https://huggingface.co/alibabasglab/MossFormer2_SE_48K), eff8c97925c8bec812af707814b3e5d777fd4503, Apache-2.0 | [ClearerVoice-Studio](https://github.com/modelscope/ClearerVoice-Studio), 6b3774dc79c46ae8bed2a4fa5f706f0ac8c75c61, Apache-2.0 | 48 kHz mono voice |

The weights total about 1.8 GB and are shared across projects. Model `provenance.json` files record source, revision, license statements and hashes. `runtime/source-provenance.json` records inference source files and hashes. Model licenses do not grant permission to use a person's voice. Upstream license material remains in [third-party notices](../THIRD_PARTY_NOTICES.md) and [license records](../LICENSES/README.md) (Chinese).

Windows cannot check out an upstream training path named AUX. The installer exports required inference files from pinned Git objects, without changing inference implementations or installing the training environment. Alternative source without a clear code license and Demucs weights with disputed commercial restrictions are not integrated.

## Limits and comparison

Two-speaker separation produces two anonymous tracks, not verified identities. More than two speakers, long silence, strong reverberation and alternating speakers can cause leakage or swapped identities. Overlap matching keeps track order across windows but cannot remove all drift. Compare against the original. Music removal and denoising may alter voice quality or introduce residual sound and distortion.

Long recordings use bounded windows and crossfades to reconstruct continuous tracks, retaining the end and duration. This reconstructs time within a track; it does not join different references. Least-squares estimates from the mixture restore each track's scale, avoiding arbitrary amplification. Attenuation occurs only above the peak threshold, and gain policy is recorded in metadata. Playback levels can differ before and after processing.

Recommendations combine quality, speech ratio, length, ASR and approximate speaker metrics. Listening determines which clip to use. Hi-Fi uses the selected individual clip and its corrected transcript, not words from another clip.

## Tasks and recovery

Processing and TTS share an exclusive GPU lock. The platform unloads its TTS model before processing; the processing subprocess exits to release VRAM. Other applications are not terminated. CPU VAD, transcription and quality analysis use a separate queue.

Settings are under `config/platform.json` → `audio_processing`: device, CPU threads, queue limits, timeout and window lengths.

`data/recordings` holds original recordings and analyses. `data/audio-processing/<task UUID>` keeps the pre-processing WAV, intermediate steps and final outputs. Each output has a UUID, SHA-256, sample rate, channels, role and original/parent task provenance. Reimporting the same output reuses its recording record.

Cancellation, failure and timeout preserve originals. Interrupted processing is marked failed. Analysis can be retried separately using existing separation outputs. Progress-file writes have short retries on Windows; a progress notification failure does not invalidate a successful analysis. Final result files are saved independently.

## CLI and API

After optional global CLI registration, replace the ID strings with returned IDs and run commands as needed. Confirm rights only when you have permission.

~~~powershell
$recordingId = "RECORDING_ID"
$processingId = "PROCESSING_ID"
voice upload-reference .\recording.wav --source "My recording" --authorization "Permission for this use" --rights-confirmed
voice process-audio $recordingId --operations remove_music separate denoise
voice processing $processingId
~~~

Use `voice <command> --help` for available flags. MCP provides `voice_upload_recording`, `voice_process_recording`, `voice_audio_processing` and `voice_create_from_reference`. Reconnect MCP after updating; all working directories share the same local HTTP service and models.

Routes use the `/api/v1` prefix. See the running service's `/docs` and `/openapi.json` for schemas.

| Route | Purpose |
|---|---|
| POST /recordings | Multipart `file`, `source`, `authorization`, `rights_confirmed`, `smart_reference`. HTTP defaults to false for compatibility; WebUI/CLI/MCP default to true. |
| GET /recordings/{id} | Workflow state, original/derived clips, recommendations and analysis states. |
| POST /recordings/from-result | Register a design sample's original audio using `result_id`. |
| GET /audio-processing/capabilities | Available processing operations. |
| POST /audio-processing | Submit `recording_id`, `operations`, `analyze_outputs`. |
| GET /audio-processing or /audio-processing/{id} | List tasks or inspect one. |
| POST /audio-processing/{id}/cancel | Cancel a task. |
| GET /audio-processing/{id}/before | Listen to the pre-processing audio. |
| GET /audio-processing/{id}/outputs/{output_id} | Listen to an output. |
| POST /audio-processing/{id}/analyze-output | Submit `output_id` for reference analysis. |
| POST /reference-voices | Create a draft voice from `reference_id` and `name`, or add it to `voice_id` with a `scenario`. |

## Related guides

[README](../README.en.md) · [Installation](INSTALL.en.md) · [Long-form narration](LONGFORM.en.md) · [Reference audio](REFERENCE_PREPROCESSING.en.md) · [Maintenance](MAINTENANCE.en.md)


[Reference and narration workflow](WORKFLOW_GUIDE.en.md)
