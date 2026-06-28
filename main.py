import os
import sys

for mod in list(sys.modules.keys()):
    if mod.startswith("core") or mod.startswith("ui"):
        del sys.modules[mod]

try:
    _ROOT = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _ROOT = None

if _ROOT and _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from ui.converter_ui import show

if __name__ == "__main__":
    show()
