import sys
import types

import pytest
import maya.cmds as cmds

from ui import feedback


class _Log:
    def __init__(self):
        self.calls = []

    def info(self, msg, **kw):
        self.calls.append(("info", msg))

    def warn(self, msg, **kw):
        self.calls.append(("warn", msg))

    def error(self, msg, **kw):
        self.calls.append(("error", msg))


class _Action:
    def __init__(self, log, fn):
        self.log = log
        self.fn = fn

    @feedback.qt_maya_logger("Test")
    def run(self):
        return self.fn()


def _boom():
    raise ValueError("boom")


def _capture_dialog(monkeypatch):
    dialogs = []
    monkeypatch.setattr(feedback, "show_error_dialog", lambda m: dialogs.append(m))
    return dialogs


def test_success_returns_result_without_dialog(monkeypatch):
    log = _Log()
    dialogs = _capture_dialog(monkeypatch)
    action = _Action(log, lambda: "ok")
    assert action.run() == "ok"
    assert dialogs == []
    assert any(c[0] == "info" and "[START]" in c[1] for c in log.calls)
    assert any(c[0] == "info" and "[SUCCESS]" in c[1] for c in log.calls)


def test_business_error_logs_shows_dialog_and_reraises(monkeypatch):
    log = _Log()
    dialogs = _capture_dialog(monkeypatch)
    action = _Action(log, _boom)
    with pytest.raises(ValueError, match="boom"):
        action.run()
    assert any(c[0] == "error" and "boom" in c[1] for c in log.calls)
    assert dialogs == ["Operation failed:\nboom"]


def test_dialog_failure_is_logged_and_original_reraises(monkeypatch):
    log = _Log()

    def broken_dialog(m):
        raise RuntimeError("dialog broken")

    monkeypatch.setattr(feedback, "show_error_dialog", broken_dialog)
    action = _Action(log, _boom)
    with pytest.raises(ValueError, match="boom"):
        action.run()
    assert any(c[0] == "warn" and "Error dialog failed" in c[1] for c in log.calls)


def test_logger_error_failure_falls_back_to_stderr_without_warn(monkeypatch, capsys):
    class BrokenLog(_Log):
        def error(self, msg, **kw):
            raise RuntimeError("logger broken")

    log = BrokenLog()
    _capture_dialog(monkeypatch)
    action = _Action(log, _boom)
    with pytest.raises(ValueError, match="boom"):
        action.run()
    err = capsys.readouterr().err
    assert "Logger failed while reporting" in err
    assert not any(c[0] == "warn" for c in log.calls)


def test_dialog_and_warn_both_fail_fall_back_to_stderr(monkeypatch, capsys):
    class BrokenLog(_Log):
        def error(self, msg, **kw):
            raise RuntimeError("logger broken")

        def warn(self, msg, **kw):
            raise RuntimeError("logger broken")

    log = BrokenLog()

    def broken_dialog(m):
        raise RuntimeError("dialog broken")

    monkeypatch.setattr(feedback, "show_error_dialog", broken_dialog)
    action = _Action(log, _boom)
    with pytest.raises(ValueError, match="boom"):
        action.run()
    err = capsys.readouterr().err
    assert "Logger failed while reporting dialog error" in err


def test_start_log_failure_does_not_block_business(monkeypatch, capsys):
    class BrokenStartLog(_Log):
        def info(self, msg, **kw):
            if "[START]" in msg:
                raise RuntimeError("logger broken")
            super().info(msg, **kw)

    log = BrokenStartLog()
    _capture_dialog(monkeypatch)
    action = _Action(log, lambda: "ok")
    assert action.run() == "ok"
    err = capsys.readouterr().err
    assert "Logger failed while starting action" in err


def test_view_message_failure_still_returns_result(monkeypatch):
    log = _Log()

    def broken_view(*a, **k):
        raise RuntimeError("view broken")

    monkeypatch.setattr(cmds, "inViewMessage", broken_view)
    action = _Action(log, lambda: "ok")
    assert action.run() == "ok"
    assert any(c[0] == "warn" and "In-view message failed" in c[1] for c in log.calls)


def test_success_log_failure_falls_back_to_stderr(monkeypatch, capsys):
    class BrokenSuccessLog(_Log):
        def info(self, msg, **kw):
            if "[SUCCESS]" in msg:
                raise RuntimeError("logger broken")
            super().info(msg, **kw)

    log = BrokenSuccessLog()
    _capture_dialog(monkeypatch)
    action = _Action(log, lambda: "ok")
    assert action.run() == "ok"
    err = capsys.readouterr().err
    assert "Logger failed while reporting success" in err


def test_show_error_dialog_uses_none_parent(monkeypatch):
    fake_ui = types.ModuleType("ui")
    fake_qt = types.ModuleType("fake_qt")
    calls = []

    class _MsgBox:
        @staticmethod
        def critical(parent, title, text):
            calls.append((parent, title, text))

    fake_qt.QMessageBox = _MsgBox
    fake_ui.QtWidgets = fake_qt
    monkeypatch.setitem(sys.modules, "ui", fake_ui)

    feedback.show_error_dialog("test message")
    assert calls == [(None, "Error", "test message")]