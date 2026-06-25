## Trim Audio Editor

Opens a built-in waveform editor for the first audio file in the configured field.
Drag the left and right handles to set trim points, preview the result with Play,
then commit to trim the file in-place.

### Configuration

- **shortcut** -- Keyboard shortcut in the editor (e.g. `Ctrl+E`).
- **audio_field_name** -- Name of the field containing audio `[sound:...]` tags.

### Usage

1. Open the card editor (Add or Browse mode).
2. Click the **Audio** button in the toolbar, or press the configured shortcut.
3. In the waveform editor:
   - Drag the red handles to set start/end trim points.
   - Use the spinboxes for precise time entry.
   - **Play Selection** -- preview the trimmed portion.
   - **Play Full** -- preview the original audio.
   - **Trim & Save** -- commit the trim (destructive, in-place).

### Dependencies

Requires `ffmpeg` / `ffprobe` / `ffplay` to be installed.

### Diagnostics

Run **Tools → Edit Audio: Run Diagnostics** to verify ffmpeg tools, media paths,
and field configuration.
