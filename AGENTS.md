# AGENTS.md

## Project

An Anki 2.1 addon: inline waveform trimmer for audio fields. Opens a Qt dialog
with a waveform, drag handles for left/right trim, preview playback via ffplay,
and lossless commit via `ffmpeg -c copy`. Only the first `[sound:...]` in the
configured field is edited.

## Commands

```bash
# run unit tests (standalone, no Anki required)
python -m pytest tests/ -v

# or just this file directly
python -m pytest tests/test_audio.py -v

# create publishable .ankiaddon (run from addons21/)
rm -rf edit_audio_external/__pycache__ edit_audio_external/tests/__pycache__
cd edit_audio_external && zip -r ../edit_audio_external.ankiaddon * -x ".git/*" ".gitignore" "AGENTS.md"
```

## Architecture

```
__init__.py          <-- single-file addon, all logic here
├── config           _get_config() — merges config.json over DEFAULT_CONFIG
├── audio helpers    _get_duration(), _extract_waveform(), _commit_trim()
├── WaveformWidget   QWidget paint + mouse drag handles
├── TrimDialog       QDialog: waveform + spinboxes + play + commit
├── edit_audio()     main callback (called from button/shortcut)
├── _on_editor_buttons()   hook -> editor.addButton()
└── _run_diagnostics()     Tools menu -> trace log + system checks

tests/
└── test_audio.py    mocks all aqt/anki modules, no runtime needed
```

## Conventions

### Code style
- No comments in code unless necessary
- Private helper functions prefixed with `_`
- Imports: stdlib, then `aqt`/`anki`, then Qt
- String quotes: double `"` for Python, single `'` for regex patterns

### Anki addon patterns
- Hooks registered in `_init()` called at module load
- `editor_did_init_buttons` to add toolbar buttons
- `editor.addButton(icon=None, cmd, func, tip, label, keys)` for button + shortcut
- Config via `mw.addonManager.getConfig(__name__)` merged with `DEFAULT_CONFIG`
- `_trace()` for diagnostics; view via Tools -> Edit Audio: Run Diagnostics
- Catch all exceptions in `edit_audio()` and show via `showWarning()`

### Testing patterns
- Module-level mocks for `aqt`, `anki`, `aqt.qt`, etc. before any import
- `mock.patch.object(module, 'mw', mock_mw)` to inject mock main window
- `mock.patch.object()` for `subprocess.run`, `os.path.exists`, etc.
- Count call increments (`calls_before`) rather than `assert_called_once`
- `_fresh_mw()` and `_mock_editor()` factory functions per test class

### Qt notes
- PyQt6 API (enums under class, e.g. `Qt.AlignmentFlag.AlignCenter`)
- Use `event.position().x()` (PyQt6) not `event.pos().x()` (PyQt5)
- Use `QPainter`, `QColor`, `Qt` in widgets; avoid webview/JS

## Config keys (config.json)

| Key | Default | Purpose |
|---|---|---|
| `shortcut` | `"Ctrl+E"` | editor keyboard shortcut |
| `audio_field_name` | `"Audio"` | field containing `[sound:...]` tags |

## Publishing

1. Clean __pycache__
2. Zip as `.ankiaddon` (no parent folder, no `.git/`)
3. Upload at https://ankiweb.net/shared/addons/
