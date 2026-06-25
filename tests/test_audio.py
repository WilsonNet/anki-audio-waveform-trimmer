"""
Unit tests for Edit Audio External addon.

Run with: python -m pytest tests/ -v
"""

import os
import sys
from unittest import mock

import pytest

_mocks = {}
for _mod in (
    "aqt", "aqt.gui_hooks", "aqt.editor", "aqt.utils", "aqt.qt",
    "anki", "anki.hooks",
):
    _mocks[_mod] = mock.MagicMock()
    sys.modules[_mod] = _mocks[_mod]

_mocks["aqt"].gui_hooks = _mocks["aqt.gui_hooks"]
_mocks["aqt"].utils = _mocks["aqt.utils"]
_mocks["aqt"].editor = _mocks["aqt.editor"]
_mocks["aqt"].qt = _mocks["aqt.qt"]
_mocks["aqt"].mw = mock.MagicMock()

_here = os.path.dirname(__file__)
_addon_dir = os.path.dirname(_here)
sys.path.insert(0, _addon_dir)


def _fresh_mw():
    mw = mock.MagicMock()
    mw.col.media.dir.return_value = "/tmp/anki_media"
    mw.addonManager.getConfig.return_value = None
    return mw


def _mock_editor(mw):
    editor = mock.MagicMock()
    editor.mw = mw
    editor.note = mock.MagicMock()
    editor.note.items.return_value = [
        ("Audio", "some text [sound:recording.mp3] more text"),
        ("Front", "Question"),
    ]
    editor.note.note_type.return_value = {"name": "TestNote"}
    editor.note.__getitem__ = lambda self, k: {
        "Audio": "some text [sound:recording.mp3] more text",
        "Front": "Question",
    }.get(k, "")
    return editor


class TestExtractFirstAudio:
    def test_single_sound(self):
        from edit_audio_external import extract_first_audio
        assert extract_first_audio("foo [sound:a.mp3] bar") == "a.mp3"

    def test_multiple_sounds_returns_first_only(self):
        from edit_audio_external import extract_first_audio
        assert extract_first_audio("[sound:first.wav] [sound:second.mp3]") == "first.wav"

    def test_no_sound_returns_none(self):
        from edit_audio_external import extract_first_audio
        assert extract_first_audio("just text") is None

    def test_empty_string_returns_none(self):
        from edit_audio_external import extract_first_audio
        assert extract_first_audio("") is None

    def test_malformed_tag_no_closing_bracket(self):
        from edit_audio_external import extract_first_audio
        assert extract_first_audio("[sound:broken") is None

    def test_filename_with_spaces(self):
        from edit_audio_external import extract_first_audio
        assert extract_first_audio("[sound:my recording.mp3]") == "my recording.mp3"

    def test_filename_with_path_chars(self):
        from edit_audio_external import extract_first_audio
        assert extract_first_audio("[sound:rec_2024-01-01.mp3]") == "rec_2024-01-01.mp3"

    def test_html_surrounding_audio(self):
        from edit_audio_external import extract_first_audio
        html = "<div>Listen: [sound:audio.ogg]<br></div>"
        assert extract_first_audio(html) == "audio.ogg"


class TestConfig:
    def test_defaults_when_config_is_none(self):
        import edit_audio_external
        mw = _fresh_mw()
        mw.addonManager.getConfig.return_value = None
        with mock.patch.object(edit_audio_external, "mw", mw):
            cfg = edit_audio_external._get_config()
        assert cfg == edit_audio_external.DEFAULT_CONFIG

    def test_defaults_when_config_is_empty(self):
        import edit_audio_external
        mw = _fresh_mw()
        mw.addonManager.getConfig.return_value = {}
        with mock.patch.object(edit_audio_external, "mw", mw):
            cfg = edit_audio_external._get_config()
        assert cfg == edit_audio_external.DEFAULT_CONFIG

    def test_partial_override(self):
        import edit_audio_external
        mw = _fresh_mw()
        mw.addonManager.getConfig.return_value = {"shortcut": "Ctrl+Shift+T"}
        with mock.patch.object(edit_audio_external, "mw", mw):
            cfg = edit_audio_external._get_config()
        assert cfg["shortcut"] == "Ctrl+Shift+T"
        assert cfg["audio_field_name"] == "Audio"

    def test_extra_keys_preserved(self):
        import edit_audio_external
        mw = _fresh_mw()
        mw.addonManager.getConfig.return_value = {"custom_extra": 42}
        with mock.patch.object(edit_audio_external, "mw", mw):
            cfg = edit_audio_external._get_config()
        assert cfg["custom_extra"] == 42
        assert cfg["audio_field_name"] == "Audio"


class TestTimeFormat:
    def test_zero(self):
        from edit_audio_external import _format_time
        assert _format_time(0) == "0:00.00"

    def test_seconds(self):
        from edit_audio_external import _format_time
        assert _format_time(5.5) == "0:05.50"

    def test_minutes(self):
        from edit_audio_external import _format_time
        assert _format_time(125.75) == "2:05.75"


class TestGetDuration:
    def test_returns_float(self):
        import edit_audio_external
        with mock.patch.object(edit_audio_external.subprocess, "run") as mock_run:
            mock_run.return_value = mock.MagicMock(
                returncode=0, stdout="123.45\n", stderr=""
            )
            assert edit_audio_external._get_duration("/tmp/test.mp3") == 123.45

    def test_returns_zero_on_failure(self):
        import edit_audio_external
        with mock.patch.object(edit_audio_external.subprocess, "run") as mock_run:
            mock_run.return_value = mock.MagicMock(
                returncode=1, stdout="", stderr="error"
            )
            assert edit_audio_external._get_duration("/tmp/bad.mp3") == 0.0


class TestCommitTrim:
    def test_success_path(self):
        import edit_audio_external
        with mock.patch.object(edit_audio_external.subprocess, "run") as mock_run, \
             mock.patch.object(edit_audio_external.tempfile, "mkstemp") as mock_tmp, \
             mock.patch.object(edit_audio_external.os, "close"), \
             mock.patch.object(edit_audio_external.os.path, "getsize", return_value=1000), \
             mock.patch.object(edit_audio_external.os, "replace"):
            mock_tmp.return_value = (99, "/tmp/tmpXXXX.mp3")
            mock_run.return_value = mock.MagicMock(returncode=0, stderr=b"")
            assert edit_audio_external._commit_trim("/tmp/test.mp3", 2.0, 8.0) is True

    def test_ffmpeg_nonzero_return(self):
        import edit_audio_external
        with mock.patch.object(edit_audio_external.subprocess, "run") as mock_run, \
             mock.patch.object(edit_audio_external.tempfile, "mkstemp") as mock_tmp, \
             mock.patch.object(edit_audio_external.os, "close"), \
             mock.patch.object(edit_audio_external.os, "unlink"):
            mock_tmp.return_value = (99, "/tmp/tmpXXXX.mp3")
            mock_run.return_value = mock.MagicMock(returncode=1, stderr=b"fail")
            assert edit_audio_external._commit_trim("/tmp/test.mp3", 2.0, 8.0) is False

    def test_empty_output_file(self):
        import edit_audio_external
        with mock.patch.object(edit_audio_external.subprocess, "run") as mock_run, \
             mock.patch.object(edit_audio_external.tempfile, "mkstemp") as mock_tmp, \
             mock.patch.object(edit_audio_external.os, "close"), \
             mock.patch.object(edit_audio_external.os.path, "getsize", return_value=0), \
             mock.patch.object(edit_audio_external.os, "unlink"):
            mock_tmp.return_value = (99, "/tmp/tmpXXXX.mp3")
            mock_run.return_value = mock.MagicMock(returncode=0, stderr=b"")
            assert edit_audio_external._commit_trim("/tmp/test.mp3", 2.0, 8.0) is False


class TestEditAudio:
    def test_field_not_found(self):
        import edit_audio_external
        calls_before = _mocks["aqt.utils"].showWarning.call_count
        mw = _fresh_mw()
        editor = _mock_editor(mw)
        editor.note.items.return_value = [("Front", "hello")]
        with mock.patch.object(edit_audio_external, "mw", mw):
            edit_audio_external.edit_audio(editor)
        assert _mocks["aqt.utils"].showWarning.call_count == calls_before + 1
        assert "not found" in str(_mocks["aqt.utils"].showWarning.call_args)

    def test_no_sound_in_field(self):
        import edit_audio_external
        calls_before = _mocks["aqt.utils"].showInfo.call_count
        mw = _fresh_mw()
        editor = _mock_editor(mw)
        editor.note.items.return_value = [("Audio", "plain text"), ("Front", "Q")]
        editor.note.__getitem__ = lambda self, k: {"Audio": "plain text", "Front": "Q"}.get(k, "")
        with mock.patch.object(edit_audio_external, "mw", mw):
            edit_audio_external.edit_audio(editor)
        assert _mocks["aqt.utils"].showInfo.call_count == calls_before + 1
        assert "No audio" in str(_mocks["aqt.utils"].showInfo.call_args)

    def test_file_not_on_disk(self):
        import edit_audio_external
        calls_before = _mocks["aqt.utils"].showWarning.call_count
        mw = _fresh_mw()
        mw.col.media.dir.return_value = "/nonexistent"
        editor = _mock_editor(mw)
        editor.note.items.return_value = [("Audio", "[sound:missing.mp3]"), ("Front", "Q")]
        editor.note.__getitem__ = lambda self, k: {"Audio": "[sound:missing.mp3]", "Front": "Q"}.get(k, "")
        with mock.patch.object(edit_audio_external, "mw", mw):
            edit_audio_external.edit_audio(editor)
        assert _mocks["aqt.utils"].showWarning.call_count == calls_before + 1
        assert "not found on disk" in str(_mocks["aqt.utils"].showWarning.call_args)

    def test_opens_trim_dialog(self):
        import edit_audio_external
        mw = _fresh_mw()
        editor = _mock_editor(mw)
        editor.note.items.return_value = [("Audio", "[sound:test.mp3]"), ("Front", "Q")]
        editor.note.__getitem__ = lambda self, k: {"Audio": "[sound:test.mp3]", "Front": "Q"}.get(k, "")
        with mock.patch.object(edit_audio_external, "mw", mw):
            with mock.patch.object(edit_audio_external.os.path, "exists", return_value=True):
                with mock.patch.object(edit_audio_external.os.path, "join", return_value="/tmp/anki_media/test.mp3"):
                    with mock.patch.object(edit_audio_external, "TrimDialog") as MockDialog:
                        mock_dialog = mock.MagicMock()
                        MockDialog.return_value = mock_dialog
                        edit_audio_external.edit_audio(editor)
                        MockDialog.assert_called_once_with(
                            "/tmp/anki_media/test.mp3",
                            parent=editor.widget,
                        )
                        mock_dialog.exec.assert_called_once()


class TestHooks:
    def test_editor_buttons_hook_registered(self):
        import edit_audio_external
        hooks = _mocks["aqt.gui_hooks"].editor_did_init_buttons
        appended_fns = [
            str(call_args[0])
            for call_args in hooks.append.call_args_list
        ]
        assert any("_on_editor_buttons" in fn for fn in appended_fns)
