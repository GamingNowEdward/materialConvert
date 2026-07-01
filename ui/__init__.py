try:
    from PySide2 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide6 import QtWidgets, QtCore, QtGui

try:
    import shiboken2 as shiboken
except ImportError:
    try:
        import shiboken6 as shiboken
    except ImportError:
        shiboken = None

import maya.cmds as cmds
