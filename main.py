import os
import sys

try:
    _ROOT = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _ROOT = None

if _ROOT and _ROOT not in sys.path:
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
