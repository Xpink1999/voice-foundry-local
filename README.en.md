[简体中文](README.md) | **English** | [日本語](README.ja.md) | [한국어](README.ko.md)

# Voice Foundry

Design voices, clone voices from recordings and produce narration for dialogue, video or books on Windows. The WebUI, CLI, REST API and MCP share one model installation and voice library across projects.

The current engine is VoxCPM2. The interface supports Chinese, English, Japanese and Korean, with light and dark themes that can follow browser preferences. Interface and speech languages are selected separately. Text, asset names and transcripts retain their original language. The service runs independently for games, video, audiobooks and interactive applications.

## Interface and workflow

![Updated generation workspace](docs/images/studio-en.jpg)

An empty installation, with no user files. See the [WebUI guide](docs/WEBUI.en.md), [dark theme](docs/images/studio-dark-en.jpg) and [narrow layout](docs/images/reference-mobile-en.jpg).

Navigation is grouped into Create, Production and Resources. Enter text, choose a voice and submit; expand candidate and reference controls when needed. Approved audio can be exported from the review page. Language and theme controls are at the top right. Ctrl / ⌘ + K switches workspaces.

## Installation

Full speech generation needs Windows 11, Git, [uv](https://docs.astral.sh/uv/getting-started/installation/) and a working NVIDIA driver, primarily tested on an RTX 4090. Recording uploads and processing also need [FFmpeg](https://ffmpeg.org/download.html). Python and Codex do not need to be preinstalled.

Choose **Code → Download ZIP** on GitHub and extract everything. Open the folder containing `install-voice.cmd` and double-click it, or run:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
~~~

The full installer downloads an isolated environment, pinned sources and models, runs checks and starts the service. Allow at least 30 GiB. For interface checks only, add `-CoreOnly -NoStart`; this skips CUDA and models and cannot generate speech.

Open the [WebUI](http://127.0.0.1:8961/). Describe a voice and generate a sentence; no saved voice or recording is needed. Later use `start-voice.cmd` and `stop-voice.cmd`. See the [installation guide](docs/INSTALL.en.md) for downloads, dependencies, port conflicts and troubleshooting.

Source downloads contain no model weights, recordings, database or installed environment.

## Generate and review

1. Open voice generation and enter text. If you have no saved voice, describe one in words.
2. Listen to the result. Generate multiple candidates for the same text when you need a comparison.
3. Approve a result after listening, then choose a format and export from the listening page.

Generated results await review. The platform does not approve audio automatically.

## Voices and reference recordings

Quick reference creation handles upload, processing, segmentation and clip recommendations. Listen to the clips before saving them to the voice library. Original recordings are retained for before-and-after comparison. Transcripts are generated automatically; correct them before using Hi-Fi cloning.

A character can have multiple reference clips, including a primary reference and alternatives for different scenes. Generation uses one clip at a time; clips are not simply joined into a long recording. Each voice has a global Voice ID and can be shared across projects or kept private to one project.

Controllable cloning combines a reference voice with a style description. Hi-Fi cloning uses a reference recording and an accurate transcript. Natural-language emotion, tone and speed controls are approximate and require listening checks. Music removal, denoising and two-speaker separation may leave artifacts, residual sound or voice leakage.

## Long-form narration

Import TXT or Markdown in UTF-8, UTF-16, GB2312, GBK or GB18030. Chapters are detected and text is split into segments, including text with no headings or line breaks.

Pause and resume work, retry failed segments, review chapter audio and export chapters or a whole book. Content is paginated. Import and indexing checks for very large texts do not mean a whole book has been generated as audio; generation time depends on text length, model and hardware. See the [long-form guide](docs/LONGFORM.en.md).

## CLI and API

~~~powershell
bin\voice.cmd start
bin\voice.cmd generate --text "This is a voice sample." --style "Calm adult male, warm and natural" --wait
bin\voice.cmd voices
bin\voice.cmd health
~~~

[Global commands and MCP](docs/INSTALL.en.md#global-commands-and-mcp) are optional. The WebUI works without Codex, and the API works without a browser. [OpenAPI documentation](http://127.0.0.1:8961/docs) is available while the service is running.

## Guides

[Long-form narration](docs/LONGFORM.en.md) · [Reference audio](docs/REFERENCE_PREPROCESSING.en.md) · [Audio processing](docs/AUDIO_RESTORATION.en.md) · [Maintenance](docs/MAINTENANCE.en.md)

## Files and maintenance

Models are stored in `models/`, assets and databases in `data/`, and caches and logs in `runtime/`. Paths are configured in `config/platform.json`. Exports are saved separately; post-processing does not overwrite original audio.

Finished tasks are archived after 7 days by default, or manually in batches. Deleted items from management pages go to a recoverable recycle bin and do not immediately free disk space. The following detailed guides are in Chinese:

- [API](docs/API.md) · [Architecture](docs/ARCHITECTURE.md) · [Modules](docs/MODULES.md)
- [Interface languages](docs/LOCALIZATION.md)
- [Testing and validation scope](docs/TESTING.md) · [Source publication](docs/PUBLISHING.md)

## License

The platform's own code and documentation use [Apache-2.0](LICENSE). Models and dependencies retain their own licenses; see the [third-party notices](THIRD_PARTY_NOTICES.md) and [license records](LICENSES/README.md), both in Chinese. This is not an official product of VoxCPM or other upstream projects.

Use recordings and texts you have permission to use. An open model license does not grant permission to use a person's voice or redistribute imported manuscripts, recordings or cloned results.

[Reference and narration workflow](docs/WORKFLOW_GUIDE.en.md)
