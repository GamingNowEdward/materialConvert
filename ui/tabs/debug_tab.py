from ui import QtWidgets, QtGui
from core.config_validator import ConfigValidator, Level


class DebugTab:

    _LEVEL_COLORS = {
        Level.ERROR: "#E06C75",
        Level.WARN: "#E5C07B",
        Level.OK: "#98C379",
        Level.SKIP: "#6A737D",
        Level.INFO: "#61AFEF",
    }
    _RENDER_ORDER = (Level.ERROR, Level.WARN, Level.SKIP, Level.INFO, Level.OK)
    _FILTER_LABELS = (
        (Level.ERROR, "Errors"),
        (Level.WARN, "Warnings"),
        (Level.SKIP, "Skipped"),
        (Level.OK, "OK"),
        (Level.INFO, "Info"),
    )
    _DEFAULT_CHECKED = {Level.ERROR, Level.WARN, Level.SKIP}

    def __init__(self):
        self.log_output = None
        self.validate_btn = None
        self._filters = {}
        self._header_entries = []
        self._entries = []

    def build_ui(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        group = QtWidgets.QGroupBox("Config Validation")
        glayout = QtWidgets.QVBoxLayout(group)
        glayout.setSpacing(8)
        glayout.setContentsMargins(12, 14, 12, 12)

        hint = QtWidgets.QLabel(
            "Validate all JSON config attribute spelling against actual Maya node "
            "types. Renderers without an installed plugin are skipped automatically."
        )
        hint.setWordWrap(True)
        glayout.addWidget(hint)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        self.validate_btn = QtWidgets.QPushButton("Validate All JSON Configs")
        self.validate_btn.setObjectName("convertBtn")
        self.validate_btn.setMinimumHeight(32)
        self.validate_btn.clicked.connect(self._run_validation)
        clear_btn = QtWidgets.QPushButton("Clear Log")
        clear_btn.setObjectName("closeBtn")
        clear_btn.setMinimumHeight(32)
        clear_btn.clicked.connect(self._clear_log)
        btn_row.addStretch()
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(self.validate_btn)
        glayout.addLayout(btn_row)

        layout.addWidget(group, stretch=0)

        log_group = QtWidgets.QGroupBox("Validation Log")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        log_layout.setContentsMargins(12, 14, 12, 12)
        log_layout.setSpacing(8)

        filter_row = QtWidgets.QHBoxLayout()
        filter_row.setSpacing(12)
        filter_row.addWidget(QtWidgets.QLabel("Filter:"))
        for level, label in self._FILTER_LABELS:
            cb = QtWidgets.QCheckBox(label)
            cb.setChecked(level in self._DEFAULT_CHECKED)
            cb.setStyleSheet(
                f"QCheckBox {{ color: {self._LEVEL_COLORS[level]}; }}"
            )
            cb.stateChanged.connect(self._refresh_log)
            self._filters[level] = cb
            filter_row.addWidget(cb)
        filter_row.addStretch()
        log_layout.addLayout(filter_row)

        self.log_output = QtWidgets.QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setObjectName("logOutput")
        log_layout.addWidget(self.log_output)

        layout.addWidget(log_group, stretch=3)

        return widget

    def _clear_log(self):
        self._header_entries = []
        self._entries = []
        self._refresh_log()

    def _is_filtered(self, level):
        cb = self._filters.get(level)
        return bool(cb and cb.isChecked())

    def _append_line(self, message, level=Level.INFO, fixed=False):
        if fixed:
            self._header_entries.append(message)
        else:
            self._entries.append((level, message))
        self._refresh_log()

    def _refresh_log(self):
        if self.log_output is None:
            return
        self.log_output.clear()

        for message in self._header_entries:
            self._insert_line(message, Level.INFO)

        for level in self._RENDER_ORDER:
            if not self._is_filtered(level):
                continue
            for entry_level, message in self._entries:
                if entry_level != level:
                    continue
                self._insert_line(f"[{level}] {message}", level)

        self.log_output.ensureCursorVisible()

    def _insert_line(self, message, level):
        cursor = self.log_output.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)

        fmt = QtGui.QTextCharFormat()
        fmt.setForeground(QtGui.QColor(self._LEVEL_COLORS.get(level, "#ABB2BF")))
        if level in (Level.ERROR, Level.WARN, Level.OK):
            fmt.setFontWeight(QtGui.QFont.Weight.Bold)

        cursor.insertText(message + "\n", fmt)
        self.log_output.setTextCursor(cursor)
        QtWidgets.QApplication.processEvents()

    def _run_validation(self):
        self.validate_btn.setEnabled(False)
        try:
            self._clear_log()
            self._append_line("Running JSON config validation in Maya...",
                              Level.INFO, fixed=True)
            validator = ConfigValidator()
            results, summary = validator.validate_all()
            self._append_line(
                f"--- DONE: {summary['ok']} OK, {summary['error']} ERROR, "
                f"{summary['warn']} WARN, {summary['skip']} SKIP "
                f"({summary['total']} checks) ---",
                Level.INFO,
                fixed=True,
            )
            if summary["skip"]:
                self._append_line(
                    f"{summary['skip']} item(s) skipped (missing renderer / empty "
                    "mapping / common placeholder) - not errors.",
                    Level.WARN,
                    fixed=True,
                )
            for result in results:
                self._append_line(
                    f"{result.scope}: {result.detail}",
                    result.level,
                )
        finally:
            self.validate_btn.setEnabled(True)