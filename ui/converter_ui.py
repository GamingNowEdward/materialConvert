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

from core.builder_context import BuilderContext
from ui.styles import FULL_STYLESHEET
from ui.tabs import ConverterTab, BuilderTab, NodeToolsTab, TransformTab, AttrModifierTab


def _maya_main_window():
    for widget in QtWidgets.QApplication.topLevelWidgets():
        try:
            if widget.objectName() == "MayaWindow":
                return widget
        except Exception:
            pass
    return None


class ConverterWindow(QtWidgets.QDialog):

    WINDOW_NAME = "pbrConverterWindow"
    WINDOW_TITLE = "Material Builder & Converter"

    def __init__(self, parent=None):
        if parent is None:
            parent = _maya_main_window()
        super().__init__(parent)

        self.ctx = BuilderContext()

        self.converter_tab = ConverterTab()
        self.builder_tab = BuilderTab(self.ctx)
        self.node_tools_tab = NodeToolsTab(self.ctx)
        self.transform_tab = TransformTab(self.ctx)
        self.attr_modifier_tab = AttrModifierTab(self.ctx)

        self.setObjectName(self.WINDOW_NAME)
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setMinimumSize(860, 800)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)

        self._build_ui()
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet(FULL_STYLESHEET)

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setObjectName("mainTabs")
        main_layout.addWidget(self.tab_widget)

        self.tab_widget.addTab(self.converter_tab.build_ui(), "  Converter  ")
        self.tab_widget.addTab(self.builder_tab.build_ui(), "  Material Builder  ")
        self.tab_widget.addTab(self.node_tools_tab.build_ui(), "  Node Tools  ")
        self.tab_widget.addTab(self.transform_tab.build_ui(), "  Transform Tools  ")
        self.tab_widget.addTab(self.attr_modifier_tab.build_ui(), "  Attr Modifier  ")


def show():
    global _converter_window

    if shiboken is not None:
        maya_win = _maya_main_window()
        if maya_win:
            for child in maya_win.children():
                try:
                    if (isinstance(child, QtWidgets.QWidget) and
                            child.objectName() == ConverterWindow.WINDOW_NAME):
                        child.close()
                        child.deleteLater()
                except Exception:
                    pass

    try:
        _converter_window.close()
        _converter_window.deleteLater()
    except Exception:
        pass

    _converter_window = ConverterWindow()
    _converter_window.show()
    return _converter_window
