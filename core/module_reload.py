"""Helpers for cleanly reloading this project when its code changed.

The tool is launched from a Maya shelf by ``exec()``-ing ``main.py`` again.
Without unloading the previously imported ``core.*`` / ``ui.*`` modules the
edited code would never run.

Because ``core`` and ``ui`` are very generic package names, the purge must be
driven by the *physical location* of each module file, never by name prefixes:
a foreign plugin running in the same Maya session may well own its own
``core``/``ui`` packages, and purging those would break it.
"""

import os
import sys


def is_project_module(mod, root):
    """Return whether *mod* physically lives under *root*.

    Modules without an own string ``__file__`` (builtins, namespace packages,
    ``None``) are never considered project modules, even when their name
    suggests otherwise.  The check is intentionally exception-free: "not ours"
    is a normal outcome here, not an error condition to log.
    """
    if mod is None:
        return False
    path = getattr(mod, "__file__", None)
    if not isinstance(path, str) or not path:
        return False
    if not isinstance(root, str) or not root:
        return False
    module_path = os.path.normcase(os.path.abspath(path))
    root_path = os.path.normcase(os.path.abspath(root))
    return module_path == root_path or module_path.startswith(root_path + os.sep)


def purge_project_modules(root=None):
    """Remove previously imported modules whose files live under *root*.

    Returns the number of purged modules.  Only this project's own files are
    unloaded; foreign packages that merely share the ``core``/``ui`` name
    prefixes are left untouched.  ``root`` defaults to this file's directory
    (i.e. the ``core/`` folder); callers usually pass the project root.
    """
    if root is None:
        root = os.path.dirname(os.path.abspath(__file__))
    if not root:
        return 0
    purged = 0
    for name, mod in list(sys.modules.items()):
        if is_project_module(mod, root):
            del sys.modules[name]
            purged += 1
    return purged
