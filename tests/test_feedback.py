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
    fake_qt = types.ModuleType("fake_qt")
    calls = []

    class _MsgBox:
        @staticmethod
        def critical(parent, title, text):
            calls.append((parent, title, text))

    fake_qt.QMessageBox = _MsgBox
    # Patch the binding feedback holds directly: show_error_dialog imports
    # QtWidgets at module level, so replacing sys.modules["ui"] no longer
    # affects it (and would drive a real blocking QMessageBox in offscreen CI).
    monkeypatch.setattr(feedback, "QtWidgets", fake_qt)

    feedback.show_error_dialog("test message")
    assert calls == [(None, "Error", "test message")]


class _WarnAction:
    def __init__(self, log, warnings):
        self.log = log
        self._warnings = warnings

    @feedback.qt_maya_logger("Test")
    def run(self):
        self._last_operation_warnings = self._warnings
        return "ok"


def test_warning_branch_shows_banner_and_warn_not_success(monkeypatch):
    log = _Log()
    banners = []
    monkeypatch.setattr(feedback, "show_warning_banner",
                        lambda m: banners.append(m) or True)
    views = []
    monkeypatch.setattr(cmds, "inViewMessage", lambda **k: views.append(k.get("amg", "")))

    action = _WarnAction(log, 2)
    assert action.run() == "ok"
    assert banners and "issue" in banners[0]
    assert any(c[0] == "warn" and "[WARN]" in c[1] for c in log.calls)
    assert not any(c[0] == "info" and "[SUCCESS]" in c[1] for c in log.calls)
    assert not any("Success" in v for v in views)


def test_warning_counter_is_reset_between_runs(monkeypatch):
    log = _Log()
    monkeypatch.setattr(feedback, "show_warning_banner", lambda m: True)
    action = _Action(log, lambda: "ok")
    action._last_operation_warnings = 5  # stale value from a previous run
    assert action.run() == "ok"
    assert any(c[0] == "info" and "[SUCCESS]" in c[1] for c in log.calls)


def test_warning_banner_failure_is_logged(monkeypatch):
    log = _Log()
    monkeypatch.setattr(feedback, "show_warning_banner", lambda m: False)
    action = _WarnAction(log, 1)
    assert action.run() == "ok"
    assert any(c[0] == "warn" and "Warning banner failed" in c[1] for c in log.calls)


def test_show_warning_banner_is_best_effort(monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("view broken")

    monkeypatch.setattr(cmds, "inViewMessage", broken)
    assert feedback.show_warning_banner("hi") is False

    monkeypatch.setattr(cmds, "inViewMessage", lambda **kwargs: None)
    assert feedback.show_warning_banner("hi") is True


def test_show_result_banner_severity(monkeypatch):
    views = []
    monkeypatch.setattr(cmds, "inViewMessage", lambda **k: views.append(k.get("amg", "")))

    assert feedback.show_result_banner(2, 1) is True
    assert "color:red" in views[-1] and "failed" in views[-1]

    assert feedback.show_result_banner(0, 3) is True
    assert "color:orange" in views[-1] and "issues" in views[-1]

    assert feedback.show_result_banner(0, 0, ok_message="3 material(s) converted") is True
    assert "color:green" in views[-1] and "3 material(s) converted" in views[-1]


def test_show_result_banner_is_best_effort(monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("view broken")

    monkeypatch.setattr(cmds, "inViewMessage", broken)
    assert feedback.show_result_banner(1, 0) is False