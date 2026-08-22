from ui import QtCore, QtWidgets, shiboken
from core.builder_context import BuilderContext
from core.logger import get_logger
from ui.log_panel import LogPanel
from ui.styles import FULL_STYLESHEET
from ui.tabs import (ConverterTab, BuilderTab, NodeToolsTab, BatchBuilderTab, DebugTab)


def _maya_main_window(logger=None):
    log = logger or get_logger()
    for widget in QtWidgets.QApplication.topLevelWidgets():
        try:
            if widget.objectName() == "MayaWindow":
                return widget
        except Exception as exc:
            log.debug(f"Failed to inspect top-level widget {widget}: {exc}", source="ConverterWindow")
    return None


class ConverterWindow(QtWidgets.QMainWindow):

    WINDOW_NAME = "pbrConverterWindow"
    WINDOW_TITLE = "Material Builder & Converter"

    def __init__(self, parent=None):
        if parent is None:
            parent = _maya_main_window()
        super().__init__(parent)

        self.logger = get_logger()
        self.ctx = BuilderContext(logger=self.logger)

        self.converter_tab = ConverterTab(logger=self.logger)
        self.builder_tab = BuilderTab(self.ctx, logger=self.logger)
        self.node_tools_tab = NodeToolsTab(self.ctx, logger=self.logger)
        self.batch_builder_tab = BatchBuilderTab(self.ctx, logger=self.logger)
        self.debug_tab = DebugTab(logger=self.logger)
        self.log_panel = LogPanel(logger=self.logger)

        self.setObjectName(self.WINDOW_NAME)
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setMinimumSize(1200, 800)

        self._build_ui()
        self._apply_style()
        self.logger.debug("Converter window initialized", source="ConverterWindow")

    def _apply_style(self):
        self.setStyleSheet(FULL_STYLESHEET)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setObjectName("mainTabs")

        self.tab_widget.addTab(self.converter_tab.build_ui(), "  Converter  ")
        self.tab_widget.addTab(self.builder_tab.build_ui(), "  Material Builder  ")
        self.tab_widget.addTab(self.batch_builder_tab.build_ui(), "  Batch Builder  ")
        self.tab_widget.addTab(self.node_tools_tab.build_ui(), "  Node Tools  ")
        self.tab_widget.addTab(self.debug_tab.build_ui(), "  Debug  ")

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self.tab_widget)
        splitter.addWidget(self.log_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        main_layout.addWidget(splitter)

        self.setCentralWidget(central)


def show():
    global _converter_window
    logger = get_logger()

    if shiboken is not None:
        try:
            maya_win = _maya_main_window(logger)
            if maya_win:
                for child in maya_win.children():
                    try:
                        if (isinstance(child, QtWidgets.QWidget) and
                                child.objectName() == ConverterWindow.WINDOW_NAME):
                            child.close()
                            child.deleteLater()
                    except Exception as exc:
                        logger.debug(f"Failed to clean up old converter window child: {exc}", source="ConverterWindow")
        except Exception as exc:
            logger.warn(f"Failed to locate Maya main window during cleanup: {exc}", source="ConverterWindow")

    try:
        _converter_window.close()
        _converter_window.deleteLater()
    except Exception as exc:
        logger.debug(f"No previous converter window to close: {exc}", source="ConverterWindow")

    _converter_window = ConverterWindow()
    _converter_window.show()
    return _converter_window
