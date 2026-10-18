"""Re-entrancy guard for UI operations.

Batch runs call ``QApplication.processEvents()`` to repaint progress, which
means a second click (or a submission from another tab) can re-enter the same
command while the first one is still on the stack.  ``OperationGuard`` makes the
"already running" state explicit and pairs the busy notification with the
actual work, so the UI is always unlocked again in ``finally``.

Deliberately free of Qt and Maya imports so it can be unit-tested with the pure
Python suite.
"""

from core.logger import get_logger


class OperationGuard:

    def __init__(self, on_change=None, logger=None, source=""):
        self.on_change = on_change
        self.log = logger or get_logger()
        self.source = source
        self._running = False

    @property
    def running(self):
        return self._running

    def try_begin(self):
        """Enter the guarded section; False when another run is still active."""
        if self._running:
            self.log.warn("Operation already running; repeated request ignored.",
                          source=self.source)
            return False
        self._running = True
        self._notify(True)
        return True

    def end(self):
        """Leave the guarded section and unlock the UI (idempotent)."""
        if not self._running:
            return
        self._running = False
        self._notify(False)

    def _notify(self, active):
        callback = self.on_change
        if callback is None:
            return
        try:
            callback(bool(active))
        except Exception as exc:
            # Feedback must never break the business flow (see ui/feedback.py).
            self.log.warn(f"Busy state callback failed: {exc}", source=self.source)
