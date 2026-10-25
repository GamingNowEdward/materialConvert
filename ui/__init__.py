try:
    from PySide2 import QtWidgets, QtCore, QtGui
except ImportError:  # noqa: silent-fallback PySide version probe
    from PySide6 import QtWidgets, QtCore, QtGui

try:
    import shiboken2 as shiboken
except ImportError:  # noqa: silent-fallback shiboken version probe
    try:
        import shiboken6 as shiboken
    except ImportError:  # noqa: silent-fallback no shiboken available
        shiboken = None

import maya.cmds as cmds
