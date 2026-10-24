[简体中文](WEBUI.md) | **English** | [日本語](WEBUI.ja.md) | [한국어](WEBUI.ko.md)

# WebUI guide

[Back to README](../README.en.md) · [Installation](INSTALL.en.md)

Screenshots use a separate, empty data directory. They contain no user files, recordings, voices or tasks.

![Generate audio in the light theme](images/studio-en.jpg)

## Find a workspace

| Navigation group | Workspaces |
| --- | --- |
| Create | Generate, Voice design & library, Batch narration, Long-form narration |
| Production | Task queue, Listen & review, Exports |
| Resources | Projects, Asset management, Models & settings |

On narrow screens, open the top-left menu for the full navigation. Voice workspace tabs scroll horizontally.

## Generate a line

1. In Generate, enter text. Title, project and speech language are optional.
2. Choose a saved voice or describe a voice and its delivery. You can design a voice without a recording.
3. Expand Generation options for candidate count or a fixed seed. When references exist, Reference & cloning lets you select a clip and mode. Hi-Fi needs an accurate, corrected transcript and does not use extra delivery instructions.
4. Select Generate. Follow progress in Task queue, then open Listen & review.

Pace, emotion and style are approximate controls. A successful generation still needs review.

## Listen, approve and export

Play a candidate and choose Approve after listening. Confirm that you have listened and add an optional note. You can approve and keep comparing, or choose Approve and prepare export.

Select audio to show its comparison, review and export actions. Once every selected item is approved, choose a format and Export selected approved audio. The download link appears on the same page. Advanced export settings provides sample rate, channels, naming and draft packages. Drafts carry a DRAFT label and do not change review status.

Continuous comparison plays every selected item, including selections on other pages or hidden by a filter. You can stop playback at any time. To revise a candidate, choose Adjust reference and regenerate, then select a reference, cloning mode and delivery instructions. The new candidate needs its own listening review; the original audio and review record are kept.

## Create and reuse voices

Open Voice design & library and choose a tab:

- Reference clips: name and annotate individual clips, then add them to a voice for different scenes.
- Quick reference setup: upload a recording you have permission to use, listen to the recommended clips and save a voice.
- Voice library: find, listen to and edit saved voices. Start narration sends a voice to the generation workspace.
- Voice design: describe a voice, generate a sample and send it to reference preparation.
- Audio processing: remove music, separate two overlapping voices or reduce noise; compare the output before choosing a reference.

Original recordings are kept. A voice can have several references, but generation uses one clip at a time. See [reference audio](REFERENCE_PREPROCESSING.en.md) and [audio processing](AUDIO_RESTORATION.en.md).

In Quick reference setup, the radio selection chooses the voice's default reference; checkboxes select independent clips to name and save in the library. For audio processing, choose a recording and explicitly select at least one operation. If no recording exists, use the upload shortcut in the prompt.

![Quick reference setup](images/reference-en.jpg)

## Batch and long-form work

Use Batch narration for separate lines, one per row. Check the voice and text preview before submitting. Use Long-form narration for a whole file. Existing works appear first; expand the import section to add one. Check chapters and segments, try one chapter, then continue the book. Pause generation when you need to stop computation; reopen the same work to resume.

Listen, review and export chapters inside the work. Chapter reviews are separate from the regular candidate list. See [long-form narration](LONGFORM.en.md).

Pause the work, then choose Adjust reference and regenerate beside a segment. Preview a scene reference or library clip and regenerate only that segment. Hi-Fi follows the reference delivery and needs an accurate transcript; controllable cloning accepts additional delivery instructions as approximate controls. Version history and comparison keeps successful earlier takes available for listening and adoption. Regenerating or adopting a take returns the chapter to pending review. Listen and approve it again before formal export.

## Appearance, shortcuts and management

The top-right controls select interface language and theme. System follows browser or OS preferences. Interface language does not change speech language. Changing language reloads the page and keeps text drafts; reselect files and listening confirmations.

| Action | Shortcut |
| --- | --- |
| Search and switch workspaces | Ctrl / ⌘ + K |
| Submit on Generate | Ctrl / ⌘ + Enter |
| Switch voice workspace tabs | Left/Right arrows, Home, End |
| Close workspace search or navigation | Esc |

Archive finished tasks manually or through the automatic archive setting. Deleted items can be restored from the recycle bin. Archiving and deletion do not immediately remove original files. Expand model details or installation/runtime details in Models & settings when needed. See [maintenance](MAINTENANCE.en.md) for backups and stopping the service.

<details>
<summary>Dark theme and narrow layout</summary>

![Dark generation workspace](images/studio-dark-en.jpg)

<img src="images/reference-mobile-en.jpg" alt="Reference workspace on a narrow screen" width="390">

</details>
