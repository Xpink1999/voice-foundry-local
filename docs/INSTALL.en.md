[简体中文](INSTALL.md) | **English** | [日本語](INSTALL.ja.md) | [한국어](INSTALL.ko.md)

# Installation and startup

[Back to README](../README.en.md)

Choose a permanent installation directory. Projects share the service and models installed there.

## Requirements

- Windows 11, Git, [uv](https://docs.astral.sh/uv/getting-started/installation/) and a working NVIDIA driver.
- The current inference environment uses Python 3.11.16 and PyTorch / torchaudio 2.8.0 cu128, primarily tested on an RTX 4090. The PyTorch wheel includes the CUDA runtime; a separate matching CUDA Toolkit is not required. Other GPUs and CPU inference have not received equivalent validation.
- Install FFmpeg from a [distribution listed on its official site](https://ffmpeg.org/download.html) and add it to PATH. Format conversion, post-processing and advanced audio processing depend on it. Licenses vary by build; see the [third-party notices](../THIRD_PARTY_NOTICES.md) (Chinese).
- Installation downloads require internet access. Allow several GB for models and the environment, plus download caches.

## First installation

Open PowerShell in the source directory and run:

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
~~~

The script installs Python in `runtime/python`, creates `.venv` and installs locked dependencies. Inference sources go in `vendor/`, models in `models/`, and download caches in `runtime/`. It then checks dependencies, runs core tests and starts the service.

Open the [WebUI](http://127.0.0.1:8961/). The first model load takes time. Speech generation and recording processing run locally.

Model sources and revisions are pinned in `config/model-sources.json`. Downloaders support resuming and hash checks; each model directory has a `provenance.json` download record. Update source, license and verification records together when changing model versions.

To install dependencies without downloading models or starting the service:

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -SkipModels -NoStart
~~~

This is useful for inspecting source and running core tests. Actual speech generation needs models. The installer does not change user PATH or Codex configuration automatically.

## Daily use

Use the root launchers `start-voice.cmd` (start), `stop-voice.cmd` (stop) and `check-health.cmd` (health), or run these commands from the installation directory:

~~~powershell
bin\voice.cmd start
bin\voice.cmd stop
bin\voice.cmd health
bin\voice.cmd unload
~~~

These are separate commands for starting, stopping, checking health and unloading models; run only the one you need. Models unload after 5 idle minutes by default. Manual unloading releases this platform's models without terminating other applications' GPU tasks. Closing the browser does not stop background tasks. Installation does not register a Windows service or a startup task.

## Global commands and MCP

This is optional. The following script requires an installed, working Codex CLI (`codex` command):

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-global.ps1
~~~

It adds this installation's `bin` directory to the current user's PATH and registers a user-level Codex MCP server. Before changing settings, it backs up PATH and any existing Codex configuration to `data/backups/`. Keep those backups local.

Open a new terminal to use `voice`. Restart Codex or reconnect MCP to discover the tools. If you only need the global CLI, manually add this installation's full `bin` path to user PATH instead of running the script. The WebUI and API work independently.

## Configuration and remote access

Paths, models, queue and service settings are in `config/platform.json`. Relative model and data paths use the installation directory as their base. Relative CLI input and export paths use the caller's working directory.

The default listener is `127.0.0.1`. Remote access requires explicit `host` and `allowed_hosts` settings and a token in the service environment variable named by `token_env`. Remote startup is rejected without a token. HTTP uses Bearer authentication; the WebUI creates a session after token entry. Internet-facing access also needs a trusted TLS reverse proxy. Do not put credentials in source files or commit them.

See the [maintenance guide](MAINTENANCE.en.md) for backups and recovery.
