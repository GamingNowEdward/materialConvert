"""Unit tests for the path-based module purge (no Maya, no filesystem reads)."""

import sys
import types

from core.module_reload import is_project_module, purge_project_modules


def _module(name, path):
    mod = types.ModuleType(name)
    if path is not None:
        mod.__file__ = path
    return mod


def test_is_project_module_matches_only_files_under_root(tmp_path):
    root = tmp_path / "materialConvert"
    (root / "core").mkdir(parents=True)
    (root / "ui").mkdir()
    elsewhere = tmp_path / "other_tool"
    elsewhere.mkdir()

    assert is_project_module(_module("core", str(root / "core" / "__init__.py")), str(root))
    assert is_project_module(_module("core.logger", str(root / "core" / "logger.py")), str(root))
    assert is_project_module(_module("ui", str(root / "ui" / "__init__.py")), str(root))

    # Foreign packages that merely share the core/ui prefixes must be excluded.
    assert not is_project_module(_module("ui", str(elsewhere / "ui" / "__init__.py")), str(root))
    assert not is_project_module(_module("corex", str(elsewhere / "corex.py")), str(root))

    # Modules without an own __file__ are never ours.
    assert not is_project_module(_module("math", None), str(root))
    assert not is_project_module(None, str(root))


def test_purge_removes_only_project_modules(tmp_path):
    root = tmp_path / "materialConvert"
    (root / "core").mkdir(parents=True)
    (root / "ui").mkdir()
    elsewhere = tmp_path / "other_tool"
    (elsewhere / "ui").mkdir(parents=True)

    project_core = _module("_t_proj_core", str(root / "core" / "__init__.py"))
    project_ui = _module("_t_proj_ui.sub", str(root / "ui" / "sub.py"))
    foreign_ui = _module("_t_foreign_ui", str(elsewhere / "ui" / "__init__.py"))
    builtin = _module("_t_math", None)

    sys.modules["_t_proj_core"] = project_core
    sys.modules["_t_proj_ui.sub"] = project_ui
    sys.modules["_t_foreign_ui"] = foreign_ui
    sys.modules["_t_math"] = builtin
    try:
        purged = purge_project_modules(root=str(root))
        assert purged == 2
        assert "_t_proj_core" not in sys.modules
        assert "_t_proj_ui.sub" not in sys.modules
        assert "_t_foreign_ui" in sys.modules
        assert "_t_math" in sys.modules
    finally:
        for name in ("_t_proj_core", "_t_proj_ui.sub", "_t_foreign_ui", "_t_math"):
            sys.modules.pop(name, None)
