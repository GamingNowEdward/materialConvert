"""Guard against silent failures in core/ and ui/.

Structural (AST) check, not a line regex, so it cannot be bypassed by
formatting, comments between ``except`` and ``pass``, ``del exc``, or string
concatenation.

Rules
-----
1. Every ``except`` handler must *do* something observable:
   - ``raise`` (re-raise / wrap),
   - call a logger method (``log.warn`` / ``logger.error`` / ...),
   - call the logger-independent terminal fallback
     (``report_terminal`` / ``_report_terminal``),
   - or carry an explicit ``# noqa: silent-fallback <reason>`` marker (used only
     where even stderr is unavailable, i.e. the terminal fallback itself).
2. No ``print(...)`` calls.
3. No direct ``cmds.warning(...)`` calls.

Usage:
    python scripts/check_no_silent_pass.py
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_LOGGER_METHODS = {
    "debug", "info", "warn", "warning", "error", "critical",
    "exception", "skip", "ok",
}
_TERMINAL_FALLBACKS = {"report_terminal", "_report_terminal"}
_NOQA_MARKER = "noqa: silent-fallback"


def _is_logger_call(node):
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in _LOGGER_METHODS or func.attr in _TERMINAL_FALLBACKS
    if isinstance(func, ast.Name):
        return func.id in _TERMINAL_FALLBACKS
    return False


def _handler_has_marker(handler, lines):
    start = handler.lineno - 1
    end = max((getattr(child, "end_lineno", None) or handler.lineno)
              for child in handler.body)
    segment = "\n".join(lines[start:end])
    return _NOQA_MARKER in segment


def _handler_is_silent(handler, lines):
    for node in ast.walk(ast.Module(body=handler.body, type_ignores=[])):
        if isinstance(node, ast.Raise):
            return False
        if _is_logger_call(node):
            return False
    return not _handler_has_marker(handler, lines)


def check_python_file(path):
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [f"{exc.lineno}: syntax error: {exc.msg}"]

    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                problems.append(f"{node.lineno}: print call")
            elif (isinstance(func, ast.Attribute) and func.attr == "warning"
                  and isinstance(func.value, ast.Name) and func.value.id == "cmds"):
                problems.append(f"{node.lineno}: direct cmds.warning call")
        elif isinstance(node, ast.ExceptHandler) and _handler_is_silent(node, lines):
            problems.append(
                f"{node.lineno}: except handler neither logs, raises, nor is "
                f"marked '# {_NOQA_MARKER}'")
    return problems


def main():
    failed = False
    for base in ("core", "ui"):
        for path in sorted((ROOT / base).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            for problem in check_python_file(path):
                failed = True
                print(f"{path.relative_to(ROOT)}:{problem}")
    if failed:
        sys.exit(1)
    print("No silent except / print / cmds.warning markers found.")


if __name__ == "__main__":
    main()
