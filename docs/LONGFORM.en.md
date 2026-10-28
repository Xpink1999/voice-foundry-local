[简体中文](LONGFORM.md) | **English** | [日本語](LONGFORM.ja.md) | [한국어](LONGFORM.ko.md)

# Long-form narration

Open Create → Long-form narration. Existing works appear first; expand Import a new work to add text. Voice instructions and cloning mode are optional expanded controls. Review and export chapters inside the work. See the [WebUI guide](WEBUI.en.md) for navigation.

## Import and split

Open long-form narration, import a TXT or Markdown file, and choose a voice and project. Check the chapter list and segments before generating the whole book or a selected chapter. Closing the browser does not stop work; use pause to stop generation. After restarting the platform, reopen the work and resume. Completed segments are kept.

Headings and line breaks are optional:

- Recognizes standalone Chinese chapter markers, Chapter numbers or Roman numerals, prologue/epilogue headings and Markdown headings.
- Without headings, groups paragraphs into automatic chapters at roughly 30,000 characters. These are management units, not the book's original table of contents.
- Without paragraphs, splits by punctuation and length. The default segment limit is 160 characters. Each segment records its byte offsets and content hash in normalized UTF-8 text.
- Detection uses rules. Check unusual headings, contents pages and running headers. Incorrect chapters or segments can be excluded, restored and reviewed again.

Choose automatic decoding or UTF-8, UTF-16 (including explicit byte order with or without BOM), GB2312, GBK or GB18030. Automatic decoding checks the BOM, validates all content as UTF-8, then tries GB18030, which covers common GBK/GB2312 content. A GB2312 file may therefore show GB18030 as the decoder. Decoding is strict; errors preserve the original file so you can select another encoding.

## Storage and limits

Long-form import is separate from the regular 60,000-character text field and 200-item batch API. It does not create hundreds of thousands of ordinary jobs at once. SQLite indexes works, chapters, segments and attempts; the browser loads pages while full text stays on disk. Even lines without breaks are parsed in bounded blocks, with index commits every 1,000 segments.

Original bytes are kept at `data/longform/<work UUID>/source.original`. A separate UTF-8 copy normalizes line endings. Both files have SHA-256 records. Segment offsets refer to the normalized file, not the original GB2312 or UTF-16 bytes.

At import, each work freezes its voice version, default reference and transcript version, model identity, parameters, base seed, segmentation and pause settings. A regenerated segment can store its own reference and delivery settings without changing the work defaults. The default source limit is **2 GiB of original file bytes**, configurable as an upload limit. The model still receives small segments. Disk space, runtime and model capability limit practical production volume.

## Resume, retry and alternate takes

Long-form generation shares the model and compute lock with regular TTS and audio processing. Each segment has its own checkpoint, state, attempts, text/audio hashes, model, reference configuration hash and actual seed. Work/chapter/state indexes locate the next segment; successful segments are not requeued as regular jobs.

On pause or restart, unfinished segments return to pending while successful files and records stay intact. A failed segment pauses the work. Retry failed segments, or resume to skip failures and process the rest. A changed model or reference hash blocks resuming under different conditions.

### Change the reference and regenerate one segment

Pause the work first, and finish or cancel any export in progress. Open the reference/regeneration action beside a successful or failed segment. Check the text and current audio, then choose a scene reference for the voice or a clip from the reference library. Preview the reference and its transcript before setting delivery instructions for controllable cloning and an optional seed. Hi-Fi follows the reference delivery, requires an accurate transcript, and does not add a style description.

The default is the segment's frozen reference and settings, rather than the voice's latest default. Choose the option to restore the reference and settings captured at import to return to the work defaults, then set any explicit changes. Regenerating one segment processes only that segment; it does not continue the rest of the chapter or book. Other segments and the work defaults stay unchanged. Changing the voice or model for the entire work still requires a separate import.

Previous audio and attempt records are retained. Open version history to compare successful takes and adopt an older version. Regenerating or adopting a take returns the chapter to pending review; listen and approve it again before formal export. Failed segments can still be retried with their existing settings. A model or frozen reference-file mismatch blocks generation rather than silently substituting new conditions.

Regular candidates on the listening/review page also support reference-based regeneration. This creates a new candidate awaiting review and leaves the original candidate and approval unchanged. Long-form chapter reviews, progress and exports remain inside the work.

A fixed reference reduces drift but does not guarantee identical voice or prosody across a book. Cancellation takes effect at the model's streaming or return boundary.

## Chapter review

Listen continuously within a chapter or play individual segments. The player reads one segment at a time. Finishing playback does not confirm listening or approve audio.

Approval requires every active segment in the chapter to succeed and an explicit confirmation that you listened. Regeneration, exclusion or restoration returns affected chapters to review; other chapters keep their status. Review history is stored in `lf_reviews`, and older audio remains in separate attempt directories.

## Export

The work's export area offers the current chapter, one file per chapter, or one combined book. WAV, FLAC, MP3 and OGG retain the model's original sample rate; additional encoding uses local FFmpeg.

Formal export requires all selected active chapters to be complete and approved for their current audio versions. For unreviewed content, explicitly select draft export. Audio and ZIP names include DRAFT and the manifest records `draft=true`. Long-form export does not change regular result approvals.

Audio and ZIP64 are written in blocks. WAV files predicted to exceed RIFF capacity use RF64, which some older players do not support; split chapters or use FLAC if needed. Combined books retain intermediate chapter WAVs and need extra disk space. The full book's PCM is not assembled in memory.

Packages include the configuration snapshot, source hashes, `segments.jsonl` with text and the adopted takes’ parameters and audio hashes, `chapters.jsonl`, segment-boundary subtitles, and `generation-profiles.jsonl`. The latter stores each distinct segment override used in the export by configuration hash. A take’s `generation_profile_id` links to that record; segments without overrides use the work snapshot. Chapter SRT files start at zero; `book.srt` uses the book timeline. These are segment timings, not word-level alignment.

Generation changes for this work are locked during export; other works and regular TTS remain available. Cancellation, failure and interruption retain written files. Submit a new export to retry; original segments are not overwritten. Downloads are streamed, and the CLI checks the ZIP SHA-256.

## Cloning modes

VoxCPM2 supports two modes:

- `clone_mode=reference`: controllable cloning uses `reference_wav_path` with optional bracketed style instructions. Speed, emotion and delivery are approximate guidance.
- `clone_mode=hifi`: Hi-Fi cloning supplies the same clip as `reference_wav_path` and `prompt_wav_path`, with its exact `prompt_text`. It follows the reference delivery without an extra style description.

Edit and save the full reference transcript in the workbench. It must describe the reference recording, not the new dialogue. The workbench, batch generation and long-form import have mode selectors. Unchecked automatic transcripts stay marked as drafts. Hi-Fi does not guarantee similarity or listening approval.

## Delete and restore

Management and recycle-bin tools cover projects, voices and versions, references and recordings, jobs, results, exports, processing, comparisons, and long-form works, chapters, segments and exports. Single and batch operations include relationship previews and restoration by selection or deletion batch.

Deletion removes items from daily lists without deleting model, text, audio or frozen trace records. It does not free disk space. Stop running tasks first. Unbind references from voices, or delete the voices in the same batch. The current voice version cannot be deleted alone. If any selected item is protected, the entire batch is rejected.

Deleting a work does not expand millions of segments into individual trash entries. Chapter deletion excludes its active segments in the same batch. Restoring that chapter restores only segments excluded by that batch, leaving earlier individual deletions unchanged. Changed chapters need review again.

On the regular listening/review page, select results for batch review and export, or choose approve and prepare export in the confirmation dialog. Advanced options remain in the export center. Approval requires listening confirmation; a selection containing unreviewed results cannot be formally exported.

## CLI, MCP and API

Examples assume the optional global CLI is registered. Replace the ID strings with IDs returned by the service and run commands as needed.

~~~powershell
$voiceId = "VOICE_ID"
$bookId = "BOOK_ID"
$exportId = "EXPORT_ID"
voice import-book .\book.txt --encoding auto --voice-id $voiceId
voice book $bookId --chapters
voice book-resume $bookId
voice book-pause $bookId
voice book-retry-failed $bookId
voice book-segments $bookId 1 --limit 25
voice book-generation $bookId 1
voice book-attempts $bookId 1
voice book-regenerate $bookId 1 --reference-id REFERENCE_ID --start
voice book-use-attempt $bookId 1 1
voice book-export $bookId --mode chapters --draft
voice book-export-status $exportId
voice book-download $exportId --dest .\output
~~~

`book-generation` shows the frozen settings and `book-attempts` lists previous takes. `book-regenerate --start` generates only that segment; without `--start`, it updates the settings and queues the segment for a later resume. `book-use-attempt` adopts a successful earlier take. Both changes require a new chapter review. For a regular candidate, `voice regenerate-result RESULT_ID --reference-id REFERENCE_ID` creates a new version awaiting review. MCP provides the same reference regeneration, history and take adoption tools. Manage clips with `voice references`, `voice update-reference REFERENCE_ID metadata.json` and `voice attach-references VOICE_ID --ids REFERENCE_ID`.

`voice delete-assets` previews changes unless `--apply` is supplied. Use `voice restore-asset-batch` with the deletion batch ID to restore a batch.

REST prefixes are `/api/v1/longform` and `/api/v1/assets`. The running service's `/docs` provides the full contract. Fields for segment regeneration, historical audio and take adoption are listed in the [API guide](API.md#按参考重做) (Chinese). MCP offers import, pagination, resume, export and asset tools, with no tool that approves audio on your behalf. Reconnect MCP after an update; models do not need reinstalling.

## Configuration and validation

`config/platform.json` → `longform` contains `max_source_bytes`, `segment_chars`, `fallback_chapter_chars`, `import_batch_segments`, `pause_ms` and `block_frames`. Changes affect snapshots for newly imported works.

Online database backups include the long-form indexes and recycle-bin metadata. Full recovery also needs `data/longform` and the other audio directories. Originals, normalized text, attempts and exports are retained; irreversible disk cleanup is not implemented. Large-text import tests do not constitute full-book synthesis or human listening acceptance. See [testing scope](TESTING.md) (Chinese).

## Related guides

[README](../README.en.md) · [Installation](INSTALL.en.md) · [Reference audio](REFERENCE_PREPROCESSING.en.md) · [Audio processing](AUDIO_RESTORATION.en.md) · [Maintenance](MAINTENANCE.en.md)


## Reference and narration workflow

[Reference and narration workflow](WORKFLOW_GUIDE.en.md)

## Switching books and retrying

Retry, resume, issue handling and review stay attached to the book and chapter selected when clicked. Old responses cannot replace a newly opened book. Failed version-page requests leave the last successful page available for another attempt. Switching books clears old issue rows, preventing actions on another book’s segment with the same number.
