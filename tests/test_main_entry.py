"""Startup contract tests.

``main.py`` is launched by ``exec(open(...).read())`` from a Maya shelf, which
does not define ``__file__``.  The project root must be resolved from the
candidate's contents or from ``sys.path``, never from a foreign ``__file__``.
"""

import os
import sys
import types

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PATH = os.path.join(PROJECT_ROOT, "main.py")


def _stub_modules(monkeypatch, purged):
    """Replace core/ui imports with project-owned stubs.

    The stubs carry a project ``__file__`` so ``main.py``'s takeover step treats
    them as its own instead of evicting them.
    """
    core_stub = types.ModuleType("core")
    core_stub.__path__ = []
    core_stub.__file__ = os.path.join(PROJECT_ROOT, "core", "__init__.py")

    reload_stub = types.ModuleType("core.module_reload")
    reload_stub.__file__ = os.path.join(PROJECT_ROOT, "core", "module_reload.py")

    def purge_project_modules(root=None):
        purged.append(root)
        return 0

    reload_stub.purge_project_modules = purge_project_modules
    core_stub.module_reload = reload_stub

    ui_stub = types.ModuleType("ui")
    ui_stub.__path__ = []
    ui_stub.__file__ = os.path.join(PROJECT_ROOT, "ui", "__init__.py")

    mw_stub = types.ModuleType("ui.main_window")
    mw_stub.__file__ = os.path.join(PROJECT_ROOT, "ui", "main_window.py")
    mw_stub.show = lambda: None
    ui_stub.main_window = mw_stub

    monkeypatch.setitem(sys.modules, "core", core_stub)
    monkeypatch.setitem(sys.modules, "core.module_reload", reload_stub)
    monkeypatch.setitem(sys.modules, "ui", ui_stub)
    monkeypatch.setitem(sys.modules, "ui.main_window", mw_stub)


def _run_entry(namespace, extra_path=()):
    """Execute main.py in *namespace*, exactly like ``exec(open(...).read())``."""
    original_path = list(sys.path)
    try:
        sys.path.insert(0, PROJECT_ROOT)
        for entry in extra_path:
            sys.path.insert(0, entry)
        with open(MAIN_PATH, "r", encoding="utf-8") as handle:
            source = handle.read()
        code = compile(source, MAIN_PATH, "exec")
        exec(code, namespace)  # noqa: S102 - the documented launch mechanism
        return namespace
    finally:
        sys.path[:] = original_path


def test_root_resolved_from_sys_path_without_file(monkeypatch):
    purged = []
    _stub_modules(monkeypatch, purged)

    namespace = {"__name__": "__main__"}
    _run_entry(namespace)

    assert os.path.normcase(namespace["_ROOT"]) == os.path.normcase(PROJECT_ROOT)
    assert purged and os.path.normcase(purged[-1]) == os.path.normcase(PROJECT_ROOT)


def test_root_resolved_from_valid_file(monkeypatch):
    purged = []
    _stub_modules(monkeypatch, purged)

    namespace = {"__name__": "__main__", "__file__": MAIN_PATH}
    _run_entry(namespace)

    assert os.path.normcase(namespace["_ROOT"]) == os.path.normcase(PROJECT_ROOT)


def test_foreign_file_is_ignored_in_favour_of_sys_path(monkeypatch):
    purged = []
    _stub_modules(monkeypatch, purged)

    # another tool's __file__ is still bound in the Script Editor namespace
    namespace = {"__name__": "__main__", "__file__": "C:/other_tool/main.py"}
    _run_entry(namespace)

    assert os.path.normcase(namespace["_ROOT"]) == os.path.normcase(PROJECT_ROOT)


def test_unresolvable_root_degrades_without_raising(monkeypatch, capsys):
    purged = []
    _stub_modules(monkeypatch, purged)

    namespace = {"__name__": "__main__"}
    original_path = list(sys.path)
    try:
        # remove every directory that looks like this project
        sys.path[:] = [p for p in sys.path
                       if os.path.normcase(os.path.abspath(p or ".")) !=
                       os.path.normcase(PROJECT_ROOT)]
        with open(MAIN_PATH, "r", encoding="utf-8") as handle:
            source = handle.read()
        exec(compile(source, MAIN_PATH, "exec"), namespace)  # noqa: S102
    finally:
        sys.path[:] = original_path

    assert namespace["_ROOT"] is None
    assert purged == []
    assert "project root not found" in capsys.readouterr().err
