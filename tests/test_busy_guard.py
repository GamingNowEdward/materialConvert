"""Re-entrancy guard tests.

The guard is Qt-free on purpose: the failure mode is "a second submission while
the first is still on the stack", which is testable without a Maya session.
"""

from core.logger import LogLevel, Logger
from ui.operation_state import OperationGuard
from ui.widgets import set_enabled


def test_second_begin_is_rejected_and_logged():
    events = []
    log = Logger()
    guard = OperationGuard(on_change=events.append, logger=log, source="Test")

    assert guard.try_begin() is True
    assert guard.running
    assert guard.try_begin() is False
    assert events == [True]

    warns = [r for r in log.poll(0) if r.level == LogLevel.WARN]
    assert warns
    assert "already running" in warns[0].message


def test_end_unlocks_and_is_idempotent():
    events = []
    guard = OperationGuard(on_change=events.append, logger=Logger())

    guard.try_begin()
    guard.end()
    assert events == [True, False]

    guard.end()  # a second end must not notify again
    assert events == [True, False]
    assert guard.try_begin() is True


def test_callback_failure_never_breaks_the_guard():
    log = Logger()

    def broken(active):
        raise RuntimeError("ui gone")

    guard = OperationGuard(on_change=broken, logger=log)
    assert guard.try_begin() is True
    guard.end()

    assert not guard.running
    warns = [r for r in log.poll(0) if r.level == LogLevel.WARN]
    assert any("Busy state callback failed" in r.message for r in warns)


def test_missing_callback_is_allowed():
    guard = OperationGuard(logger=Logger())
    assert guard.try_begin()
    guard.end()
    assert not guard.running


class _Widget:
    def __init__(self, error=None):
        self.enabled = None
        self.error = error

    def setEnabled(self, value):
        if self.error is not None:
            raise self.error
        self.enabled = value


def test_set_enabled_tolerates_destroyed_widgets():
    alive = _Widget()
    dead = _Widget(RuntimeError("already deleted"))

    set_enabled([alive, dead], False)
    assert alive.enabled is False

    set_enabled([alive], True)
    assert alive.enabled is True
