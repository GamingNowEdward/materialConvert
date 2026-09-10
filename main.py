import os
import sys

try:
    _ROOT = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _ROOT = None


def _owned_by_root(module, root):
    """Whether *module* physically lives under *root*.

    Inlined on purpose: importing ``core.module_reload`` for this check is
    exactly what may resolve into a foreign ``core`` package.
    """
    path = getattr(module, "__file__", None)
    if not isinstance(path, str) or not path:
        return False
    module_path = os.path.normcase(os.path.abspath(path))
    root_path = os.path.normcase(os.path.abspath(root))
    return module_path == root_path or module_path.startswith(root_path + os.sep)


if _ROOT:
    # Take over the generic top-level names if another tool with the same flat
    # layout already owns them; otherwise the import below
    # ("from core.module_reload import ...") would resolve into that foreign
    # package and this tool could not start at all.
    for _name in ("core", "ui", "main"):
        # Evict every foreign module under this name - the top-level package and
        # its cached submodules. Submodules are checked independently of the
        # top-level key: a foreign failure can leave a mixed state (a stale
        # foreign "core.results" while the top-level "core" is already gone),
        # which would otherwise shadow our imports.
        for _key in list(sys.modules):
            if _key != _name and not _key.startswith(_name + "."):
                continue
            _sub = sys.modules.get(_key)
            if _sub is not None and not _owned_by_root(_sub, _ROOT):
                sys.modules.pop(_key, None)

    # Always resolve this project's modules before any other tool's.
    while _ROOT in sys.path:
        sys.path.remove(_ROOT)
    sys.path.insert(0, _ROOT)

# Reload only this project's own modules on re-exec (path-based, not name
# prefix based), so foreign packages named core/ui in the same Maya session
# are never touched.
if _ROOT:
    from core.module_reload import purge_project_modules
    purge_project_modules(root=_ROOT)

from ui.main_window import show

if __name__ == "__main__":
    show()
