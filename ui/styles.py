FULL_STYLESHEET = """
QDialog { background-color: #232323; }
QLabel { color: #DCDCDC; font-family: 'Segoe UI'; }
QCheckBox { color: #DCDCDC; }
QCheckBox::indicator:unchecked { border: 1px solid #555; background-color: #151515; }
QCheckBox::indicator:checked { border: 1px solid #00AFFF; background-color: #00AFFF; }
QLineEdit {
    background-color: #151515; border: 1px solid #333; border-radius: 4px;
    padding: 8px; color: #00FFAD; font-family: 'Consolas';
}

QPushButton {
    background-color: #2E3D4D; color: #8DBAE8; border-radius: 4px; font-weight: bold; font-family: 'Segoe UI';
}
QPushButton:hover { background-color: #3E4D5D; color: white; border: 1px solid #00AFFF; }

QPushButton#rsBtn { background-color: #4D2E2E; color: #E88D8D; }
QPushButton#rsBtn:hover { background-color: #5D3E3E; color: white; border: 1px solid #FF4F4F; }
QPushButton#vrayBtn { background-color: #4D3D2E; color: #E8BA8D; }
QPushButton#vrayBtn:hover { background-color: #5D4D3E; color: white; border: 1px solid #FFB34F; }
QPushButton#createFileBtn { background-color: #2b5c46; color: #8de8b8; }
QPushButton#createFileBtn:hover { background-color: #3b7c5e; color: white; border: 1px solid #00FFAD; }
QPushButton#applyCsBtn { background-color: #3d2b5c; color: #c48de8; }
QPushButton#applyCsBtn:hover { background-color: #4e3b7c; color: white; border: 1px solid #B500FF; }
QPushButton#applyTransformBtn { background-color: #2b5c46; color: #8de8b8; }
QPushButton#applyTransformBtn:hover { background-color: #3b7c5e; color: white; border: 1px solid #00FFAD; }
QPushButton#setLocBtn { background-color: #4D3D2E; color: #E8BA8D; }
QPushButton#setLocBtn:hover { background-color: #5D4D3E; color: white; border: 1px solid #FFB34F; }
QPushButton#execModifyBtn { background-color: #2b5c46; color: #8de8b8; }
QPushButton#execModifyBtn:hover { background-color: #3b7c5e; color: white; border: 1px solid #00FFAD; }

/* Converter tab 专用按钮 */
QPushButton#convertBtn { background-color: #2b5c46; color: #8de8b8; }
QPushButton#convertBtn:hover { background-color: #3b7c5e; color: white; border: 1px solid #00FFAD; }
QPushButton#refreshBtn { background-color: #3d2b5c; color: #c48de8; }
QPushButton#refreshBtn:hover { background-color: #4e3b7c; color: white; border: 1px solid #B500FF; }
QPushButton#closeBtn { background-color: #4C3232; color: #E0A3A3; }
QPushButton#closeBtn:hover { background-color: #5C3D3D; border: 1px solid #E06C75; }

QGroupBox {
    color: #8DBAE8; font-weight: bold; border: 1px solid #333;
    margin-top: 10px; padding-top: 15px; background-color: #282828; border-radius: 4px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #00AFFF; }

QTabWidget#mainTabs::pane { border: none; background-color: #232323; }
QTabBar { qproperty-elideMode: ElideNone; }
QTabBar::tab {
    background-color: #1a1a1a; color: #888; border: 1px solid #333;
    min-width: 130px; padding: 6px 10px; margin-right: 2px;
    border-top-left-radius: 4px; border-top-right-radius: 4px;
    font-weight: bold; font-size: 13px; font-family: 'Segoe UI', 'Microsoft YaHei';
}
QTabBar::tab:selected {
    background-color: #232323; color: #00AFFF; border-bottom: 2px solid #00AFFF;
}
QTabBar::tab:hover:!selected { background-color: #2a2a2a; color: #aaa; }

QComboBox {
    background-color: #151515; border: 1px solid #333; border-radius: 4px;
    padding: 6px 10px; color: #00FFAD; font-family: 'Consolas';
}
QComboBox:hover { border: 1px solid #00AFFF; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 6px solid #8DBAE8; margin-right: 5px; }
QComboBox QAbstractItemView {
    background-color: #1a1a1a; color: #DCDCDC; border: 1px solid #333;
    selection-background-color: #2E3D4D; selection-color: white;
}

QSpinBox, QDoubleSpinBox {
    background-color: #151515; border: 1px solid #333; border-radius: 4px;
    padding: 6px 10px; color: #00FFAD; font-family: 'Consolas';
}
QSpinBox:hover, QDoubleSpinBox:hover { border: 1px solid #00AFFF; }
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border; subcontrol-position: top right;
    background-color: #2a2a2a; border-left: 1px solid #333; border-bottom: 1px solid #333;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border; subcontrol-position: bottom right;
    background-color: #2a2a2a; border-left: 1px solid #333;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-bottom: 5px solid #8DBAE8; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #8DBAE8; }

QScrollArea#toolScrollArea { background-color: transparent; border: none; }
QWidget#toolContainer { background-color: #232323; }
QScrollBar:vertical { background-color: #1a1a1a; width: 8px; border-radius: 4px; }
QScrollBar::handle:vertical { background-color: #444; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background-color: #555; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }

QListWidget {
    background-color: #151515; border: 1px solid #333; border-radius: 4px;
    color: #DCDCDC; font-family: 'Segoe UI'; font-size: 12px;
}
QListWidget::item { padding: 4px 8px; }
QListWidget::item:selected { background-color: #2E3D4D; color: white; }

QPlainTextEdit#logOutput {
    background-color: #1C1C1C; border: 1px solid #3A3A3A; border-radius: 4px;
    color: #DCDCDC; font-family: 'Consolas';
}
"""
