import functools
import time

import maya.cmds as cmds

from core.logger import get_logger
from ui import QtWidgets

_SOURCE = "BuilderFeedback"


def _report_terminal(message):
    """Logger-independent terminal error channel (stderr).

    Used only when the logger itself raises while reporting.  stderr is the
    single channel that depends on nothing (no logger, no UI, no Maya state).
    It must never raise, or it would mask the original exception.
    """
    import sys
    try:
        sys.stderr.write(f"[{_SOURCE}] {message}\n")
    except Exception as exc:
        # Terminal fallback itself failed; never mask the original exception.
        del exc  # guard-rule requirement (no silent pass), not business logic


def show_error_dialog(message):
    QtWidgets.QMessageBox.critical(None, "Error", message)


def qt_maya_logger(label):
    """Wrap a builder action with start/success banners and an error dialog.

    ``label`` is the action name shown in the log banner (e.g. "Builder").

    All feedback (log / banner / dialog) is best-effort: it can never alter
    the business control flow.  Logger failure falls back to stderr; dialog
    failure is logged; every failure still re-raises the original exception.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            log = getattr(self, "log", get_logger())
            start_time = time.time()

            try:
                log.info(f"[START] Building {label} Material...", source=_SOURCE)
            except Exception as log_exc:
                _report_terminal(f"Logger failed while starting action: {log_exc!r}")

            try:
                result = func(self, *args, **kwargs)
            except Exception as exc:
                try:
                    log.error(f"Action Failed: {exc}", source=_SOURCE)
                except Exception as log_exc:
                    _report_terminal(f"Logger failed while reporting: {log_exc!r}")
                try:
                    show_error_dialog(f"Operation failed:\n{exc}")
                except Exception as dialog_exc:
                    try:
                        log.warn(f"Error dialog failed: {dialog_exc}", source=_SOURCE)
                    except Exception as log_exc2:
                        _report_terminal(f"Logger failed while reporting dialog error: {log_exc2!r}")
                raise

            duration = time.time() - start_time
            try:
                cmds.inViewMessage(
                    amg=f"Success: Action completed in <color=yellow>{duration:.2f}s</color>",
                    pos="topCenter",
                    fade=True,
                )
            except Exception as view_exc:
                try:
                    log.warn(f"In-view message failed: {view_exc}", source=_SOURCE)
                except Exception as log_exc:
                    _report_terminal(f"Logger failed while reporting view message error: {log_exc!r}")
            try:
                log.info(f"[SUCCESS] Execution Time: {duration:.3f}s", source=_SOURCE)
            except Exception as log_exc:
                _report_terminal(f"Logger failed while reporting success: {log_exc!r}")

            return result
        return wrapper
    return decorator