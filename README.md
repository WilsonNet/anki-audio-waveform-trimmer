# Audio Waveform Trimmer

An Anki 2.1 add-on that adds a built-in waveform trimmer for audio files in your cards.

## Features

- **Waveform viewer** — click the **Audio** button or press **Ctrl+E** in the card editor
- **Drag handles** — set left and right trim boundaries directly on the waveform
- **Precise input** — spinboxes for second-by-second time control
- **Preview playback** — hear the trimmed result before committing, using `ffplay`
- **Lossless trim** — commits with `ffmpeg -c copy` (fast, no re-encoding)

![screenshot](https://raw.githubusercontent.com/WilsonNet/anki-audio-waveform-trimmer/main/screenshot.png)

Only the **first** `[sound:...]` in the configured field is edited; additional audio files are left untouched.

## Requirements

- Anki 2.1 (tested on Anki 24.04+)
- `ffmpeg`, `ffprobe`, and `ffplay` installed and available in PATH

## Installation

1. Download the `.ankiaddon` file
2. In Anki, go to **Tools → Add-ons → Install from file**
3. Select the downloaded file

Alternatively, copy the `edit_audio_external` folder into your `addons21` directory.

## Configuration

Via **Tools → Add-ons → Audio Waveform Trimmer → Config**:

| Key | Default | Purpose |
|---|---|---|
| `shortcut` | `"Ctrl+E"` | Keyboard shortcut in the editor |
| `audio_field_name` | `"Audio"` | Field name with `[sound:...]` tags |

## Usage

1. Open the card editor (Add or Browse)
2. Click the **Audio** toolbar button or press **Ctrl+E**
3. Drag the red handles on the waveform to set trim boundaries
4. Click **Play Selection** to preview the trimmed audio
5. Click **Trim & Save** to commit (replaces the file in-place)

Editing is non-destructive until you hit **Trim & Save**.

## Diagnostics

Run **Tools → Edit Audio: Run Diagnostics** to verify `ffmpeg`, media paths, and field configuration.

## License

GNU Affero General Public License v3.0 or later.
