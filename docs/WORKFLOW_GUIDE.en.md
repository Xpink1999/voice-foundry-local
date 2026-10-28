[简体中文](WORKFLOW_GUIDE.md) | **English** | [日本語](WORKFLOW_GUIDE.ja.md) | [한국어](WORKFLOW_GUIDE.ko.md)

# Reference and narration workflow

## Create a voice from a recording

1. Upload recordings in Create voice and confirm usage rights. Each original is kept separately.
2. When speaker tracking is available, choose Continue with speaker clips. Otherwise listen to original candidates, or start tracking under Speakers and audio.
3. Listen to each speaker and select clips. Each row has one selection control; playback, hover and focus do not change it.
4. Save clips separately, or create a composite reference from one speaker.
5. Create a voice or add the references to an existing voice in the same flow. Choose the default for a new voice; existing defaults stay unchanged.
6. Choose Use this voice. The studio opens with the voice selected, ready for your script.

## Combine short clips into a reference

A composite uses clips explicitly selected by the user. The platform does not silently combine all speech from a person. It checks duplicate source ranges, rights, per-output speech detection and duration before creating a draft. Defaults are at least 5 seconds of estimated speech and at most 30 seconds including gaps, configured under `speaker_tracking`.

File duration and speech estimates are separate. Duplicate source coverage and silence do not count toward the speech minimum. Listen to the combined draft before saving it. Transcribe the final audio again, then check the transcript before Hi-Fi mode. Saving never approves a reference or generated take automatically.

Combine for listening only allows arbitrary clips. It does not qualify the output as a single-speaker reference. Changing order, clips or gaps creates a new file and preserves earlier versions.

## Correct speakers and compare tracks

Expand Speaker assignment and analysis to reassign, leave unassigned, exclude or undo. Names are separate from identity. Corrections retain history; earlier references and voice snapshots are not rewritten. Derived items show source changes, and earlier timelines are marked as earlier versions.

Solo and full speaker timelines are separate. Full tracks restore every source-map interval, including assigned separated overlap. Unresolved regions remain available in the original. Silence does not prove a speaker was absent. Speech coverage is estimated; voice similarity is not an identity probability.

New tasks accept Auto, 1, 2 or 3 speakers. Automatic results above three are flagged, never forced into three identities. Optional [SepFormer WSJ0-3Mix](https://huggingface.co/speechbrain/sepformer-wsj03mix) uses native 8 kHz three-source weights. Upsampling does not restore high frequencies or establish Chinese-language quality. Missing models leave overlap unresolved while reliable solo clips stay available.

```powershell
.\.venv\Scripts\python.exe scripts/setup_three_speakers.py
```

Install speaker tracking first. This optional step downloads weights and records revision and hashes; it sends no recordings. Model loading is not listening acceptance.

## Review, revise and export

The redo dialog accepts edited production text and a different reference for both ordinary takes and book segments. Originals and previous takes remain intact. A book edit affects that segment and invalidates its chapter review; adopting an older take restores its production text too.

Flag individual book segments and use the book issue list to navigate across chapters and pages. Successful generation does not clear a manual issue. Resolving an issue does not approve a chapter. Reopening an ordinary take restores its related revision task and comparison instead of generating again.

Review shows the next action: review first, then export. Format, deletion and other settings are under More actions. Ordinary exports run in the background. Return to Export after a reload to inspect, cancel, retry or download the existing task. Unreviewed work requires an explicit draft export.

## Existing data and maintenance

Stop the service and back up database and configuration before upgrading. Event sequence and issue tables are additive. Existing recordings, entities and tracks are not rewritten. Old assemblies remain listening outputs; old timelines remain solo tracks. Missing measurements and confirmations remain unknown. Roll back by restoring the matching database, configuration and source backup while stopped; do not delete tables individually.

Readiness distinguishes installed files from loaded models. Missing files preserve drafts and point to installation. Event cursors replay task events; they do not imply inference can resume at any audio sample.

## Moving between workspaces

The studio’s batch and book actions carry the current script, project, voice, reference, cloning mode and delivery settings. Check the reference, engine, language and seed under Reference and generation settings. Existing unsubmitted drafts require confirmation before replacement. A book uses one default voice; batch role assignments are not converted into a single voice.

Batch roles match only available, unarchived voices in the row’s project. Choose a replacement when no match is available. Other characters use their own default references; explicit JSON references remain authoritative. Submission opens the batch’s task list. Choose Review this batch to continue. Batch task and review scopes survive a page reload through their URLs.

Opening candidates from a project or task resets stale filters and preserves explicit selections, including a count of hidden selections. Search export history by project, title or filename, expand its contents and return to surviving source candidates. Deleted sources are marked unavailable. Refreshing preserves unchanged selection details.

Missing models block batch submission, book continuation and retakes with a specific reason. Playback and export of existing audio remain available.

## Editing, recovery and export

- Open Details and transcript in Reference clips to listen, name the clip, inspect its source and permission, and correct its transcript. Editing clears the confirmation. Saved changes affect future tasks only.
- Hidden selections are counted across filters and pages. Inspect the selected list or clear it before adding clips to a voice.
- Reloading restores the latest voice-design sample task in this tab. Standard candidates can also be saved as voice references. Listening and approval remain manual.
- Edit archived voices and return them to Draft before generating. Using a clip directly chooses a cloning model and clears the previous voice’s delivery description.
- Models & settings shows missing-model reasons and installation instructions. Choose Check models again after installation. Diagnostic logs start collapsed.
- Without FFmpeg, WAV export must keep the original sample rate and channels. Choose Use original WAV settings in advanced export. Conversion, resampling, loudness and silence processing require encoding tools.
- Old responses cannot replace a newly selected voice, book, chapter or asset category. Changes made during saving remain unsaved drafts.
