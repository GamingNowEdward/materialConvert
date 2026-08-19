from ui import QtWidgets, shiboken
from core.builder_context import BuilderContext
from ui.styles import FULL_STYLESHEET
from ui.tabs import (ConverterTab, BuilderTab, NodeToolsTab, BatchBuilderTab, DebugTab)


def _maya_main_window():
    for widget in QtWidgets.QApplication.topLevelWidgets():
        try:
            if widget.objectName() == "MayaWindow":
                return widget
        except Exception:
            pass
    return None


class ConverterWindow(QtWidgets.QMainWindow):

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
        self.batch_builder_tab = BatchBuilderTab(self.ctx)
        self.debug_tab = DebugTab()

        self.setObjectName(self.WINDOW_NAME)
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setMinimumSize(960, 800)

        self._build_ui()
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet(FULL_STYLESHEET)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setObjectName("mainTabs")
        main_layout.addWidget(self.tab_widget)

        self.tab_widget.addTab(self.converter_tab.build_ui(), "  Converter  ")
        self.tab_widget.addTab(self.builder_tab.build_ui(), "  Material Builder  ")
        self.tab_widget.addTab(self.batch_builder_tab.build_ui(), "  Batch Builder  ")
        self.tab_widget.addTab(self.node_tools_tab.build_ui(), "  Node Tools  ")
        self.tab_widget.addTab(self.debug_tab.build_ui(), "  Debug  ")

        self.setCentralWidget(central)


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
