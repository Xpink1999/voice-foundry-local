[简体中文](MAINTENANCE.md) | **English** | [日本語](MAINTENANCE.ja.md) | [한국어](MAINTENANCE.ko.md)

# Maintenance, recovery and updates

Open Resources → Models & settings. Expand language/model details or installation/runtime details when needed, and save changes to runtime settings. Interface language and theme are separate controls at the top right. See the [WebUI guide](WEBUI.en.md).

## Daily operation

From the installation directory, use `start-voice.cmd`, `stop-voice.cmd` and `check-health.cmd`. With the optional global CLI registered, the equivalent commands are `voice start`, `voice stop` and `voice health`. The start launcher also opens the WebUI. No Windows service or startup task is registered.

Models load in a separate inference process only when needed. After 30 idle seconds by default, that process exits, releasing weights, the PyTorch runtime and its CUDA context. Adjust the timeout in Settings. `voice unload` releases an idle inference process without starting a stopped service. Closing the browser stops its preview; background jobs continue. Run `stop-voice.cmd` or `voice stop` to end the tool and wait for service exit. Saved audio is kept; unfinished books can resume later. Startup and library browsing do not load models. The lightweight service still uses some memory until stopped.

Settings are in `config/platform.json`. Before changing storage paths, stop the service, back up and copy the assets/database, then update the paths. Moving a model directory without updating configuration leaves an invalid path.

Logs are in `runtime/logs/`: `platform.log` is the rotating exception log; `server.log` contains startup and upstream model output.

## Backups

From the installation directory:

~~~powershell
bin\voice.cmd backup
~~~

This uses SQLite online backup to save a consistent `platform.sqlite3` and `platform.json` in `data/backups/<UUID>`. It does **not** back up audio files.

For full recovery, also back up the complete data directory, including `references`, `recordings`, `reference-comparisons`, `audio-processing`, `originals`, `exports` and `longform`. Long-form data includes original and normalized text, segment attempts and background exports. Keep model `provenance.json` files, the source revision and dependency locks as well. Large weights can be downloaded again using their pinned revisions.

For a matching database and file snapshot, stop the service while copying the full data directory. Keep a recovery copy before replacing anything.

Global registration backs up the prior user PATH and Codex configuration in `data/backups/global-<timestamp>`. These may contain private settings. Keep them local and out of shared logs.

## Restore

1. Stop the platform and save a separate copy of the current data.
2. Put the backed-up SQLite database, matching configuration and audio/text directories at their configured locations.
3. Verify model, reference and source hashes, then start the service and check health and task states.

Interrupted ordinary generation becomes failed and can be retried without overwriting previous results. Long-form unfinished segments return to pending; the work pauses until you resume it. Reparse an interrupted import from its preserved original. Resubmit an interrupted export. A changed source hash blocks reuse.

Do not delete unknown partial files, rebuild the whole voice library or delete the database to fix individual failures.

## Updates and schema

Back up first. Verify new code or models in an isolated environment/configuration before switching. Do not upgrade the entire environment with `pip install -U`. Record Python, CUDA wheels, upstream source commits, model revisions, dependency locks and actual listening checks.

Replacing weights in place can make existing tasks reject the changed model identity. Create new tasks for the new model. Each long-form work keeps a frozen voice/model configuration; changing global settings does not change half-finished books.

Versions 0.1–0.3 use schema 1 with stable UUIDs and JSON entities. Version 0.2 adds recordings, comparisons and optional archive fields; 0.3 adds `audio_processing` and derived recording provenance. Existing jobs default to unarchived, and historical audio is retained. Version 0.4 adds long-form tables, columns and indexes incrementally, including `lf_*` indexes, review history and `asset_trash`. Future schema changes need backups and an explicit migration, not database deletion.

## Archive and recycle bin

Finished jobs archive after 7 days by default. Set `task_archive_after_days=0` to disable automatic archiving. The task queue switches between active and archived lists and supports single or batch restoration.

Archiving keeps audio and approvals and does not free disk space. Restoration restarts the archive timer. Retrying an archived job creates an unarchived task. Original job UUIDs still retrieve historical results and events.

The recycle bin also keeps files on disk. Deleting or restoring long-form chapters/segments recalculates counts and requires affected chapters to be reviewed again. Batch restoration preserves relationships. Restoring a chapter does not restore segments individually deleted earlier. There is no irreversible empty-bin action.

## Troubleshooting

| Problem | Check |
|---|---|
| Cannot connect | Run the start launcher or `voice start`; read `runtime/logs/server.log`. Resolve port conflicts in configuration instead of starting duplicate workers. |
| Out of VRAM | Stop or unload this platform's work and close other GPU applications yourself if needed. Keep the failed task and retry. |
| Unexpected speed or emotion | These are approximate controls. Adjust the description or compare more candidates by listening. |
| Voice drift in long text | Use a confirmed reference and the same model/settings. Check prosody across segment boundaries manually. |
| Non-WAV export fails | Check FFmpeg and its encoder. Original WAVs remain. Duplicating channels does not create genuine stereo space. |
| Subtitle and trimming conflict | Disable trimming or subtitles. Without an aligner, word timestamps are not generated. |
| Global command unavailable | Open a new terminal; restart/reconnect Codex MCP. Use `bin\voice.cmd` from the installation directory meanwhile. |
| Batch failures | Inspect each task's error/events. Successful audio and approvals are kept. |

## Validation scope

Core tests use synthetic test waveforms to check service contracts. Real-model output, browser interactions, human listening and production acceptance are separate checks. Automation never approves audio.

`scripts/verify_longform_scale.py` uses a separate service on port 8962 and `runtime/longform-scale`, then stops its own service. It does not add the generated test text to the user's library. These are validation files, not production voices or user content. Current source-size, segmentation, automatic chapter and block settings are under `longform` in the configuration.

## Related guides

[README](../README.en.md) · [Installation](INSTALL.en.md) · [Long-form narration](LONGFORM.en.md) · [Reference audio](REFERENCE_PREPROCESSING.en.md) · [Audio processing](AUDIO_RESTORATION.en.md)
