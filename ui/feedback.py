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


def show_warning_banner(message):
    """Best-effort warning banner (in-view message). Returns True on success."""
    try:
        cmds.inViewMessage(
            amg=f"<span style='color:orange'>Warning:</span> {message}",
            pos="topCenter",
            fade=True,
        )
        return True
    except Exception as exc:
        # Best-effort UI feedback: the caller logs the failure; this must never
        # change business control flow. `del exc` marks the guard rule.
        del exc
        return False


def qt_maya_logger(label):
    """Wrap a builder action with start/success banners and an error dialog.

    ``label`` is the action name shown in the log banner (e.g. "Builder").

    If the wrapped method leaves ``self._last_operation_warnings`` > 0, a warning
    banner + WARN log replace the success banner so a partially-built result is
    never presented as a plain success.

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
                setattr(self, "_last_operation_warnings", 0)
            except Exception as reset_exc:
                _report_terminal(f"Logger-agnostic warning counter reset failed: {reset_exc!r}")

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
            warnings = getattr(self, "_last_operation_warnings", 0)
            if warnings:
                if not show_warning_banner(f"Completed with {warnings} issue(s); see the log"):
                    try:
                        log.warn("Warning banner failed", source=_SOURCE)
                    except Exception as banner_exc:
                        _report_terminal(f"Logger failed while reporting banner error: {banner_exc!r}")
                try:
                    log.warn(
                        f"[WARN] {label}: completed with {warnings} channel issue(s) "
                        f"in {duration:.2f}s",
                        source=_SOURCE,
                    )
                except Exception as log_exc:
                    _report_terminal(f"Logger failed while reporting warnings: {log_exc!r}")
                return result

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