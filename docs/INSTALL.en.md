[简体中文](INSTALL.md) | **English** | [日本語](INSTALL.ja.md) | [한국어](INSTALL.ko.md)

# Installation and startup

Start with the [WebUI guide](WEBUI.en.md) for the current navigation, generation, review and export workflow.

[Back to README](../README.en.md)

Choose a permanent installation directory. Projects share the service and models installed there.

## Requirements

- Windows 11 x64, [Git](https://git-scm.com/download/win), [uv](https://docs.astral.sh/uv/getting-started/installation/) and a working NVIDIA driver.
- The current inference environment uses Python 3.11.16 and PyTorch / torchaudio 2.8.0 cu128, primarily tested on an RTX 4090. The PyTorch wheel includes the CUDA runtime; a separate matching CUDA Toolkit is not required. Other GPUs and CPU inference have not received equivalent validation.
- Install FFmpeg from a [distribution listed on its official site](https://ffmpeg.org/download.html) and add it to PATH. Format conversion, post-processing and advanced audio processing depend on it. Licenses vary by build; see the [third-party notices](../THIRD_PARTY_NOTICES.md) (Chinese).
- If PyTorch reports a DLL loading error, install the [Microsoft Visual C++ v14 x64 runtime](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist). This is a Windows system dependency; the platform installer does not install or change it automatically.
- Installation downloads require internet access. Allow at least 30 GiB for a full installation.

## First installation

On GitHub, choose **Code → Download ZIP**, then use **Extract All**. Open the extracted folder containing `pyproject.toml` and `install-voice.cmd`. Do not run files inside the ZIP. Alternatively:

~~~powershell
git clone https://github.com/Xpink1999/voice-foundry-local.git
cd voice-foundry-local
~~~

Use a permanent folder your account can write to, outside Program Files and synced folders. Moving it later requires rebuilding the virtual environment. Administrator rights, an existing Python installation, CUDA Toolkit, Codex, voices and databases are not required.

Double-click `install-voice.cmd`, or open PowerShell in that folder:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
~~~

The full installer downloads Python 3.11.16, CUDA PyTorch, pinned inference sources and seven model sets. It checks imports and CUDA, runs core tests and starts the service. Weights total about 7.1 GiB; the PyTorch download is about 3.2 GiB. Allow at least 30 GiB for models, the environment, extraction and caches. A fresh installation has empty voice, project and task lists.

Open the [WebUI](http://127.0.0.1:8961/), enter one sentence and describe a voice, then generate. The first synthesis loads the model and takes longer than opening the page. Results still require listening and approval.

To inspect the interface, database and core workflows without downloading CUDA or models:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -CoreOnly -NoStart
~~~

`-CoreOnly` needs no Git, NVIDIA GPU or FFmpeg. It can open an empty interface, but cannot generate speech or process recordings. Rerun without switches to complete installation later. `-SkipModels -NoStart` still installs CUDA dependencies and inference sources, skipping only weights; it is not a lightweight installation.

Installation runs the core tests. Recording decoding, conversion and separation checks require FFmpeg; when it is absent they are explicitly skipped, rather than failing a valid CoreOnly installation. Service, queue and native-rate WAV draft export checks still run. These checks do not establish model inference or audio-processing readiness.

Python, uv state and caches stay in `runtime/`; model and runtime caches use `cache_dir`, defaulting to `runtime/model-cache`; the environment is `.venv`. Sources go in `vendor/`, models in `models/`, and databases and assets in `data/`. The installer does not read another installation's environment, recordings or database, or change user PATH or Codex settings.

Model sources and revisions are pinned in `config/model-sources.json`. Downloads verify sizes and hashes and retain `provenance.json`. Rerun after an interrupted download; valid existing files are retained.

## Checks and troubleshooting

- Log: `runtime/install.log`. Check report: `runtime/install-check.json`. Failures return a nonzero exit code. Fix the reported step and rerun; keep `data/`.
- uv or Git not found: install the tool and reopen the terminal. A ZIP download still needs Git for full inference sources; CoreOnly does not.
- Starting before installation: launchers show the install command instead of only a missing-Python error.
- Port belongs to another installation: stop that service or change `port` in this folder's `config/platform.json`, then retry and use the new URL. Local start, stop and health commands verify installation identity.
- CUDA unavailable: update the NVIDIA driver and retry. PyTorch supplies its CUDA runtime; installing a Toolkit does not replace the driver check. See [PyTorch version instructions](https://pytorch.org/get-started/previous-versions/).
- FFmpeg missing: WAV text-to-speech works; recording uploads, encoded exports, trimming, loudness processing and advanced separation need FFmpeg. Reopen the terminal after installation, or set an absolute executable path in the `ffmpeg` configuration field.
- uv version-link permission error: the installer checks the downloaded local interpreter and continues only if it works. It never falls back to system Python. Failed downloads or interpreter checks still stop installation.

Recheck a full installation:

~~~powershell
.venv\Scripts\python.exe scripts\check_install.py --profile inference --models
~~~

For CoreOnly, use `--profile core`. Opening the page, passing dependency checks and generating real speech are separate checks.

## Daily use

Use the root launchers `start-voice.cmd` (start), `stop-voice.cmd` (stop) and `check-health.cmd` (health), or run these commands from the installation directory:

~~~powershell
bin\voice.cmd start
bin\voice.cmd stop
bin\voice.cmd health
bin\voice.cmd unload
~~~

These are separate commands for starting, stopping, checking health and unloading models; run only the one you need. Models unload after 30 idle seconds by default. Manual unloading releases this platform's models without terminating other applications' GPU tasks. Closing the browser does not stop background tasks. Installation does not register a Windows service or a startup task.

## Global commands and MCP

This is optional. The following script requires an installed, working Codex CLI (`codex` command):

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-global.ps1
~~~

It adds this installation's `bin` directory to the current user's PATH and registers a user-level Codex MCP server. Before changing settings, it backs up PATH and any existing Codex configuration to `data/backups/`. Keep those backups local.

Open a new terminal to use `voice`. Restart Codex or reconnect MCP to discover the tools. If you only need the global CLI, manually add this installation's full `bin` path to user PATH instead of running the script. The WebUI and API work independently.

## Configuration and remote access

Empty `VOICE_PLATFORM_CONFIG` and `VOICE_PLATFORM_URL` values use this installation’s configuration and local address. They are not treated as a file path or an explicit remote service. Set a complete URL only when intentionally selecting another service.

Paths, models, queue and service settings are in `config/platform.json`. Relative model and data paths use the installation directory as their base. Relative CLI input and export paths use the caller's working directory.

The default listener is `127.0.0.1`. Remote access requires explicit `host` and `allowed_hosts` settings and a token in the service environment variable named by `token_env`. Remote startup is rejected without a token. HTTP uses Bearer authentication; the WebUI creates a session after token entry. Internet-facing access also needs a trusted TLS reverse proxy. Do not put credentials in source files or commit them.

See the [maintenance guide](MAINTENANCE.en.md) for backups and recovery.
