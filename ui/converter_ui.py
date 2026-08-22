from ui import QtWidgets, shiboken
from core.builder_context import BuilderContext
from core.logger import get_logger
from ui.styles import FULL_STYLESHEET
from ui.tabs import (ConverterTab, BuilderTab, NodeToolsTab, BatchBuilderTab, LogTab)


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
        self.log_tab = LogTab(logger=self.logger)

        self.setObjectName(self.WINDOW_NAME)
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setMinimumSize(960, 800)

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
        main_layout.addWidget(self.tab_widget)

        self.tab_widget.addTab(self.converter_tab.build_ui(), "  Converter  ")
        self.tab_widget.addTab(self.builder_tab.build_ui(), "  Material Builder  ")
        self.tab_widget.addTab(self.batch_builder_tab.build_ui(), "  Batch Builder  ")
        self.tab_widget.addTab(self.node_tools_tab.build_ui(), "  Node Tools  ")

        self.log_tab_widget = self.log_tab.build_ui()
        self.tab_widget.addTab(self.log_tab_widget, "  Log  ")

        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self._on_tab_changed(self.tab_widget.currentIndex())

        self.setCentralWidget(central)

    def _on_tab_changed(self, index):
        active = self.tab_widget.widget(index) is self.log_tab_widget
        self.log_tab.set_active(active)


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
