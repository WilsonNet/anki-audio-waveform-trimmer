import os
import re
import subprocess
import tempfile

from aqt import mw, gui_hooks
from aqt.editor import Editor
from aqt.utils import showInfo, showWarning, qconnect
from aqt.qt import (
    QAction,
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QDoubleSpinBox, QSizePolicy,
    QPainter, QColor, Qt,
)

ADDON_DIR = os.path.dirname(__file__)

DEFAULT_CONFIG = {
    "shortcut": "Ctrl+E",
    "audio_field_name": "Audio",
}

_trace_log = []


def _trace(msg):
    from datetime import datetime
    _trace_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    if len(_trace_log) > 200:
        _trace_log[:] = _trace_log[-100:]


def _get_config():
    config = mw.addonManager.getConfig(__name__)
    if not isinstance(config, dict):
        config = {}
    merged = {}
    for key, value in DEFAULT_CONFIG.items():
        merged[key] = config.get(key, value)
    for key, value in config.items():
        if key not in merged:
            merged[key] = value
    return merged


def extract_first_audio(field_html):
    match = re.search(r"\[sound:(.*?)\]", field_html)
    if match:
        return match.group(1)
    return None


# ---------------------------------------------------------------------------
# Audio backend helpers
# ---------------------------------------------------------------------------

def _get_duration(filepath):
    """Return audio duration in seconds via ffprobe."""
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", filepath],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode == 0 and r.stdout.strip():
        return float(r.stdout.strip())
    return 0.0


def _extract_waveform(filepath, num_columns=800):
    """Return list of (min, max) tuples for waveform display columns."""
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", filepath,
         "-f", "s16le", "-ac", "1", "-ar", "8000", "pipe:1"],
        capture_output=True, timeout=30,
    )
    raw = r.stdout
    if not raw:
        _trace("_extract_waveform: no PCM data returned")
        return [(0, 0)] * 10

    samples = []
    for i in range(0, len(raw) - 1, 2):
        val = int.from_bytes(raw[i:i + 2], "little", signed=True)
        samples.append(val)

    if not samples:
        return [(0, 0)] * 10

    cols = []
    samples_per_col = max(1, len(samples) // num_columns)
    for i in range(num_columns):
        start = i * samples_per_col
        end = start + samples_per_col
        chunk = samples[start:end]
        if chunk:
            cols.append((min(chunk), max(chunk)))
    return cols


def _format_time(seconds):
    """Format seconds as m:ss.ms"""
    m = int(seconds) // 60
    s = int(seconds) % 60
    ms = int((seconds - int(seconds)) * 100)
    return f"{m}:{s:02d}.{ms:02d}"


def _commit_trim(filepath, start_sec, end_sec):
    """Trim audio file in-place. Returns True on success."""
    _trace(f"_commit_trim: {filepath} [{start_sec:.2f} - {end_sec:.2f}]")
    fd, tmp = tempfile.mkstemp(
        suffix=os.path.splitext(filepath)[1],
        dir=os.path.dirname(filepath),
    )
    os.close(fd)

    try:
        r = subprocess.run(
            ["ffmpeg", "-y",
             "-ss", str(start_sec),
             "-i", filepath,
             "-to", str(end_sec - start_sec),
             "-c", "copy", tmp],
            capture_output=True, timeout=60,
        )
        if r.returncode != 0:
            _trace(f"ffmpeg trim failed: {r.stderr.decode()[:300]}")
            os.unlink(tmp)
            return False
        if os.path.getsize(tmp) == 0:
            _trace("ffmpeg produced empty file")
            os.unlink(tmp)
            return False
        os.replace(tmp, filepath)
        _trace("_commit_trim: success")
        return True
    except Exception as e:
        _trace(f"_commit_trim exception: {e}")
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


# ---------------------------------------------------------------------------
# Waveform widget
# ---------------------------------------------------------------------------

HANDLE_WIDTH = 8
COLOR_WAVEFORM = QColor("#4a9eff")
COLOR_SELECTED = QColor("#4a9eff")
COLOR_DIMMED = QColor("#4a9eff")
COLOR_DIMMED.setAlpha(80)
COLOR_HANDLE = QColor("#ff6b6b")
COLOR_BG = QColor("#2b2b2b")
COLOR_GRID = QColor("#3d3d3d")


class WaveformWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cols = []            # list of (min, max) tuples
        self._duration = 0.0       # total duration in seconds
        self._trim_start = 0.0     # in seconds
        self._trim_end = 0.0       # in seconds
        self._dragging = None      # 'left', 'right', or None
        self._last_mouse_x = 0
        self.setMinimumHeight(150)
        self.setMouseTracking(True)

    def load_audio(self, filepath):
        self._duration = _get_duration(filepath)
        if self._duration <= 0:
            self._duration = 1.0
        self._cols = _extract_waveform(filepath)
        if not self._cols:
            self._cols = [(0, 0)] * 10
        self._trim_start = 0.0
        self._trim_end = self._duration
        self.update()

    def set_trim(self, start, end):
        self._trim_start = max(0.0, min(start, self._duration))
        self._trim_end = max(0.0, min(end, self._duration))
        if self._trim_end < self._trim_start:
            self._trim_end = self._trim_start + 0.1
        self.update()

    @property
    def trim_start(self):
        return self._trim_start

    @property
    def trim_end(self):
        return self._trim_end

    def _x_to_time(self, x):
        margin = HANDLE_WIDTH + 4
        usable = self.width() - 2 * margin
        if usable <= 0:
            return 0.0
        frac = (x - margin) / usable
        return frac * self._duration

    def _time_to_x(self, t):
        if self._duration <= 0:
            return 0
        margin = HANDLE_WIDTH + 4
        usable = self.width() - 2 * margin
        frac = t / self._duration
        return margin + int(frac * usable)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), COLOR_BG)

        if not self._cols:
            p.setPen(QColor("#888"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No waveform data")
            p.end()
            return

        margin = HANDLE_WIDTH + 4
        w = self.width()
        h = self.height()
        usable_w = w - 2 * margin
        col_w = usable_w / len(self._cols) if self._cols else 1
        mid_y = h // 2
        amp = h * 0.40

        left_x = self._time_to_x(self._trim_start)
        right_x = self._time_to_x(self._trim_end)

        # Draw waveform columns
        for i, (mn, mx) in enumerate(self._cols):
            x = int(margin + i * col_w)
            bar_w = max(1, int(col_w) + 1)

            # Normalize to amp
            peak = max(abs(mn), abs(mx), 1)
            y1 = int(mid_y - (mx / peak) * amp)
            y2 = int(mid_y - (mn / peak) * amp)
            if y1 == y2:
                y2 = y1 + 1

            in_selection = left_x <= x <= right_x

            if in_selection:
                p.setBrush(COLOR_WAVEFORM)
                p.setPen(Qt.PenStyle.NoPen)
            else:
                p.setBrush(COLOR_DIMMED)
                p.setPen(Qt.PenStyle.NoPen)

            p.drawRect(x, y1, bar_w, y2 - y1)

        # Draw handles
        handle_h = h - 10
        p.setBrush(COLOR_HANDLE)
        p.setPen(QColor("#cc5555"))
        p.drawRect(left_x - HANDLE_WIDTH // 2, 5, HANDLE_WIDTH, handle_h)
        p.drawRect(right_x - HANDLE_WIDTH // 2, 5, HANDLE_WIDTH, handle_h)

        # Draw time labels
        p.setPen(QColor("#ccc"))
        font = p.font()
        font.setPointSize(9)
        p.setFont(font)
        p.drawText(5, h - 5, _format_time(self._trim_start))
        end_label = _format_time(self._trim_end)
        end_w = p.fontMetrics().horizontalAdvance(end_label)
        p.drawText(w - end_w - 10, h - 5, end_label)
        dur = _format_time(self._trim_end - self._trim_start)
        dur_w = p.fontMetrics().horizontalAdvance(dur)
        p.drawText(w // 2 - dur_w // 2, h - 5, dur)

        p.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x = event.position().x()
        left_x = self._time_to_x(self._trim_start)
        right_x = self._time_to_x(self._trim_end)

        if abs(x - left_x) < HANDLE_WIDTH + 4:
            self._dragging = "left"
        elif abs(x - right_x) < HANDLE_WIDTH + 4:
            self._dragging = "right"
        self._last_mouse_x = x

    def mouseMoveEvent(self, event):
        x = event.position().x()
        left_x = self._time_to_x(self._trim_start)
        right_x = self._time_to_x(self._trim_end)

        if self._dragging is None:
            # Cursor feedback
            if abs(x - left_x) < HANDLE_WIDTH + 4 or abs(x - right_x) < HANDLE_WIDTH + 4:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        dx = x - self._last_mouse_x
        self._last_mouse_x = x
        dt = (dx / (self.width() - 2 * (HANDLE_WIDTH + 4))) * self._duration if self.width() > 0 else 0

        if self._dragging == "left":
            new_start = self._trim_start + dt
            new_start = max(0.0, min(new_start, self._trim_end - 0.05))
            self._trim_start = new_start
        elif self._dragging == "right":
            new_end = self._trim_end + dt
            new_end = max(self._trim_start + 0.05, min(new_end, self._duration))
            self._trim_end = new_end

        self.update()
        if hasattr(self.parent(), "_on_trim_changed"):
            self.parent()._on_trim_changed()

    def mouseReleaseEvent(self, event):
        self._dragging = None


# ---------------------------------------------------------------------------
# Trim dialog
# ---------------------------------------------------------------------------

class TrimDialog(QDialog):
    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self._filepath = filepath
        self._player = None
        self._set_up_ui()
        self._waveform.load_audio(filepath)
        # Update spinboxes after waveform loads
        dur = self._waveform._duration
        self._start_spin.setMaximum(dur)
        self._end_spin.setMaximum(dur)
        self._end_spin.setValue(dur)
        self._update_spins_from_waveform()
        self._waveform.update()

    def _set_up_ui(self):
        self.setWindowTitle(f"Trim Audio: {os.path.basename(self._filepath)}")
        self.setMinimumSize(700, 350)
        self.resize(800, 420)

        root = QVBoxLayout(self)

        # Waveform
        self._waveform = WaveformWidget(self)
        root.addWidget(self._waveform, 1)

        # Time controls
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Start:"))
        self._start_spin = QDoubleSpinBox()
        self._start_spin.setDecimals(2)
        self._start_spin.setSingleStep(0.1)
        self._start_spin.setSuffix("s")
        self._start_spin.valueChanged.connect(self._on_start_spin)
        time_row.addWidget(self._start_spin)

        time_row.addStretch()
        self._dur_label = QLabel("Duration: 0:00.00")
        time_row.addWidget(self._dur_label)
        time_row.addStretch()

        time_row.addWidget(QLabel("End:"))
        self._end_spin = QDoubleSpinBox()
        self._end_spin.setDecimals(2)
        self._end_spin.setSingleStep(0.1)
        self._end_spin.setSuffix("s")
        self._end_spin.valueChanged.connect(self._on_end_spin)
        time_row.addWidget(self._end_spin)
        root.addLayout(time_row)

        # Buttons
        btn_row = QHBoxLayout()
        self._play_btn = QPushButton("\u25b6 Play Selection")
        self._play_btn.clicked.connect(self._play_trimmed)
        btn_row.addWidget(self._play_btn)

        self._play_full_btn = QPushButton("Play Full")
        self._play_full_btn.clicked.connect(self._play_full)
        btn_row.addWidget(self._play_full_btn)

        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._commit_btn = QPushButton("Trim & Save")
        self._commit_btn.clicked.connect(self._commit)
        self._commit_btn.setStyleSheet("QPushButton { background-color: #4a9eff; color: white; font-weight: bold; }")
        btn_row.addWidget(self._commit_btn)

        root.addLayout(btn_row)

    def _on_trim_changed(self):
        self._update_spins_from_waveform()

    def _update_spins_from_waveform(self):
        self._start_spin.blockSignals(True)
        self._end_spin.blockSignals(True)
        self._start_spin.setValue(self._waveform.trim_start)
        self._end_spin.setValue(self._waveform.trim_end)
        self._start_spin.blockSignals(False)
        self._end_spin.blockSignals(False)
        d = self._waveform.trim_end - self._waveform.trim_start
        self._dur_label.setText(f"Duration: {_format_time(d)}")

    def _on_start_spin(self, val):
        self._waveform.set_trim(val, self._waveform.trim_end)
        self._update_spins_from_waveform()

    def _on_end_spin(self, val):
        self._waveform.set_trim(self._waveform.trim_start, val)
        self._update_spins_from_waveform()

    def _stop_player(self):
        if self._player and self._player.poll() is None:
            self._player.kill()
            self._player = None

    def _play_trimmed(self):
        self._stop_player()
        start = self._waveform.trim_start
        dur = self._waveform.trim_end - self._waveform.trim_start
        if dur <= 0:
            return
        self._player = subprocess.Popen(
            ["ffplay", "-autoexit", "-nodisp",
             "-ss", str(start), "-t", str(dur),
             self._filepath],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _play_full(self):
        self._stop_player()
        self._player = subprocess.Popen(
            ["ffplay", "-autoexit", "-nodisp", self._filepath],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _commit(self):
        start = self._waveform.trim_start
        end = self._waveform.trim_end
        if end - start <= 0.01:
            showWarning("Selection too short.")
            return
        self._commit_btn.setEnabled(False)
        self._commit_btn.setText("Trimming...")
        from aqt.qt import QApplication
        QApplication.processEvents()

        ok = _commit_trim(self._filepath, start, end)
        if ok:
            showInfo(f"Audio trimmed: {_format_time(start)} \u2192 {_format_time(end)}")
            self.accept()
        else:
            showWarning("Trim failed. Check ffmpeg is installed.")
            self._commit_btn.setEnabled(True)
            self._commit_btn.setText("Trim & Save")

    def closeEvent(self, event):
        self._stop_player()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def edit_audio(editor):
    note = editor.note
    config = _get_config()
    field_name = config["audio_field_name"]

    try:
        note_type_name = note.note_type()["name"]
    except Exception:
        note_type_name = "?"
    _trace(f"edit_audio() called — note type={note_type_name}")

    try:
        note_fields = [name for name, _ in note.items()]
        _trace(f"note fields: {note_fields}")
    except Exception as e:
        _trace(f"FAIL: cannot read note fields — {e}")
        showWarning("Cannot read note fields. Is a note loaded?")
        return

    if field_name not in note_fields:
        _trace(f"FAIL: field '{field_name}' not in {note_fields}")
        showWarning(
            f"Field '{field_name}' not found on this note type.\n"
            f"Available fields: {note_fields}"
        )
        return

    _trace(f"field '{field_name}' found")

    try:
        field_content = note[field_name]
        filename = extract_first_audio(field_content)
        _trace(f"extracted filename: {filename!r}")

        if not filename:
            showInfo(f"No audio ([sound:...]) found in field '{field_name}'.")
            return

        media_dir = editor.mw.col.media.dir()
        filepath = os.path.join(media_dir, filename)
        _trace(f"full path: {filepath}")

        if not os.path.exists(filepath):
            _trace("FAIL: file not found on disk")
            showWarning(f"Audio file not found on disk:\n{filepath}")
            return

        _trace("opening trim dialog")
        dialog = TrimDialog(filepath, parent=editor.widget)
        dialog.exec()
        _trace("trim dialog closed")

    except Exception as e:
        _trace(f"FAIL: exception — {e}")
        showWarning(f"Error launching audio editor:\n{e}")


def _on_editor_buttons(buttons, editor):
    config = _get_config()
    _trace(f"_on_editor_buttons() — editor id={id(editor)}")
    btn = editor.addButton(
        icon=None,
        cmd="edit_audio_external",
        func=edit_audio,
        tip=f"Trim first audio in '{config['audio_field_name']}' field ({config['shortcut']})",
        label="Audio",
        keys=config["shortcut"],
    )
    _trace(f"addButton returned — shortcut registered")
    buttons.append(btn)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def _run_diagnostics():
    config = _get_config()
    lines = []
    lines.append("=== Edit Audio External - Diagnostics ===")
    lines.append("")

    def result(label, ok, info=""):
        mark = "PASS" if ok else "FAIL"
        line = f"[{mark}] {label}"
        if info:
            line += f"  -> {info}"
        lines.append(line)

    # Config
    try:
        raw = mw.addonManager.getConfig(__name__)
        lines.append("--- Raw config from getConfig ---")
        lines.append(str(raw))
    except Exception as e:
        lines.append(f"getConfig raised: {e}")
    lines.append("")
    lines.append("--- Merged config ---")
    for k, v in config.items():
        lines.append(f"  {k} = {v!r}")
    lines.append("")

    # ffmpeg / ffprobe / ffplay
    for binary in ["ffmpeg", "ffprobe", "ffplay"]:
        try:
            r = subprocess.run(
                [binary, "-version"],
                capture_output=True, text=True, timeout=5,
            )
            ver = r.stdout.split("\n")[0] if r.stdout else ""
            result(binary, r.returncode == 0, ver[:120])
        except FileNotFoundError:
            result(binary, False, "not found")
        except OSError as e:
            result(binary, False, str(e))
    lines.append("")

    # media dir
    lines.append("--- Media directory ---")
    try:
        md = mw.col.media.dir()
        result("Media dir exists", os.path.isdir(md), md)
    except Exception as e:
        result("Media dir", False, str(e))
    lines.append("")

    # test regex
    sample = "Solo_Leveling_S01E03_It'_185643_OIqMxoNZ.mp3"
    lines.append("--- Test: extract_first_audio() ---")
    test_tag = f"[sound:{sample}]"
    lines.append(f"  input:  {test_tag!r}")
    extracted = extract_first_audio(test_tag)
    lines.append(f"  output: {extracted!r}")
    result("Regex extraction", extracted == sample)
    lines.append("")

    # test path + duration
    lines.append("--- Test: full path + duration ---")
    try:
        md = mw.col.media.dir()
        full = os.path.join(md, sample)
        exists = os.path.exists(full)
        lines.append(f"  full path: {full}")
        lines.append(f"  exists:    {exists}")
        if exists:
            dur = _get_duration(full)
            lines.append(f"  duration:  {dur:.2f}s")
            result("File accessible", True, f"{dur:.2f}s")
        else:
            result("File accessible", False, "file not found")
    except Exception as e:
        result("File accessible", False, str(e))
    lines.append("")

    # note lookup
    field_name = config["audio_field_name"]
    lines.append(f"--- Note lookup (field='{field_name}') ---")
    try:
        nids = mw.col.find_notes("")
    except Exception as e:
        nids = []
        lines.append(f"  find_notes failed: {e}")
    lines.append(f"  total notes in collection: {len(nids)}")
    found = False
    for nid in nids[:1000]:
        try:
            note = mw.col.get_note(nid)
        except Exception:
            continue
        note_fields = [name for name, _ in note.items()]
        if field_name in note_fields:
            lines.append(f"  found note nid={nid} with field '{field_name}'")
            lines.append(f"  note fields: {note_fields}")
            raw_val = note[field_name]
            lines.append(f"  raw field value ({len(raw_val)} chars):")
            lines.append(f"    {raw_val[:300]!r}")
            af = extract_first_audio(raw_val)
            lines.append(f"  extracted audio filename: {af!r}")
            if af:
                full = os.path.join(mw.col.media.dir(), af)
                lines.append(f"  full path: {full}")
                lines.append(f"  file exists: {os.path.exists(full)}")
                if os.path.exists(full):
                    dur = _get_duration(full)
                    lines.append(f"  duration: {dur:.2f}s")
            found = True
            result("Note with field found", True, f"nid={nid}")
            break
    if not found:
        lines.append(f"  scanned {min(len(nids), 1000)} notes, none had field '{field_name}'")
        result("Note with field found", False, f"no note has field '{field_name}'")
    lines.append("")

    # collection
    lines.append("--- Collection ---")
    try:
        deck_name = mw.col.decks.current()["name"]
        result("Collection accessible", True, f"deck: {deck_name}")
    except Exception as e:
        result("Collection accessible", False, str(e))
    lines.append("")

    # addon info
    lines.append("--- Addon info ---")
    lines.append(f"  __name__ = {__name__!r}")
    lines.append(f"  ADDON_DIR = {ADDON_DIR}")
    lines.append(f"  mw type = {type(mw).__name__}")
    lines.append(f"  mw.col is None = {mw.col is None}")

    # trace log
    lines.append("")
    lines.append("--- Recent trace log ---")
    if _trace_log:
        lines.extend(_trace_log)
    else:
        lines.append("  (no activity recorded yet)")

    showInfo("\n".join(lines))


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def _init():
    gui_hooks.editor_did_init_buttons.append(_on_editor_buttons)
    action = QAction("Edit Audio: Run Diagnostics", mw)
    qconnect(action.triggered, _run_diagnostics)
    mw.form.menuTools.addAction(action)


_init()
