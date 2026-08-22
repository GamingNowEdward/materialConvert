import time
from collections import deque

from ui import QtCore, QtGui, QtWidgets

from core.logger import LogLevel, get_logger

_LEVEL_COLORS = {
    LogLevel.ERROR: "#E06C75",
    LogLevel.WARN: "#E5C07B",
    LogLevel.OK: "#98C379",
    LogLevel.SKIP: "#6A737D",
    LogLevel.INFO: "#61AFEF",
    LogLevel.DEBUG: "#8A9199",
}

_FILTER_ORDER = (LogLevel.ERROR, LogLevel.WARN, LogLevel.SKIP, LogLevel.INFO, LogLevel.OK, LogLevel.DEBUG)
_DEFAULT_CHECKED = {LogLevel.ERROR, LogLevel.WARN, LogLevel.SKIP, LogLevel.INFO}
_VALIDATION_LEVELS = {LogLevel.ERROR, LogLevel.WARN, LogLevel.SKIP, LogLevel.INFO}
_ERRORS_ONLY_LEVELS = {LogLevel.ERROR, LogLevel.WARN}


class LogModel(QtCore.QAbstractTableModel):
    _HEADERS = ("Time", "Level", "Source", "Context", "Message")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records = deque()

    def clear(self):
        self.beginResetModel()
        self._records.clear()
        self.endResetModel()

    def append_records(self, records):
        if not records:
            return
        start = len(self._records)
        end = start + len(records) - 1
        self.beginInsertRows(QtCore.QModelIndex(), start, end)
        self._records.extend(records)
        self.endInsertRows()

    def rowCount(self, parent=QtCore.QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._records)

    def columnCount(self, parent=QtCore.QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._HEADERS)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        record = self._records[index.row()]
        col = index.column()

        if role == QtCore.Qt.DisplayRole:
            if col == 0:
                local = time.localtime(record.ts)
                return time.strftime("%H:%M:%S", local) + f".{int(record.ts % 1 * 1000):03d}"
            if col == 1:
                return record.level
            if col == 2:
                return record.source
            if col == 3:
                if not record.context:
                    return ""
                return " ".join(f"{k}={v}" for k, v in record.context.items())
            if col == 4:
                return record.message
        elif role == QtCore.Qt.ToolTipRole:
            local = time.localtime(record.ts)
            ts = time.strftime("%Y-%m-%d %H:%M:%S", local) + f".{int(record.ts % 1 * 1000):03d}"
            context = " ".join(f"{k}={v}" for k, v in record.context.items())
            return f"{ts} [{record.level}] {record.source} {context}\n{record.message}"
        elif role == QtCore.Qt.ForegroundRole:
            return QtGui.QColor(_LEVEL_COLORS.get(record.level, "#ABB2BF"))
        elif role == QtCore.Qt.FontRole:
            if record.level in (LogLevel.ERROR, LogLevel.WARN, LogLevel.OK):
                font = QtGui.QFont()
                font.setBold(True)
                return font
        return None

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._HEADERS[section]
        return None

    def record_at(self, row):
        if 0 <= row < len(self._records):
            return self._records[row]
        return None


class LogFilterProxy(QtCore.QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._levels = set(_DEFAULT_CHECKED)
        self._source = ""
        self._text = ""

    def set_levels(self, levels):
        self._levels = set(levels)
        self.invalidateFilter()

    def set_source(self, source):
        self._source = source or ""
        self.invalidateFilter()

    def set_text(self, text):
        self._text = (text or "").lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        record = model.record_at(source_row)
        if record is None:
            return False
        if record.level not in self._levels:
            return False
        if self._source and record.source != self._source:
            return False
        if self._text:
            if self._text not in record.message.lower():
                if self._text not in record.source.lower():
                    context = " ".join(str(v) for v in record.context.values()).lower()
                    if self._text not in context:
                        return False
        return True


class LogViewer(QtWidgets.QWidget):
    """Embedded global log viewer used by the Log tab.

    The viewer polls ``Logger.poll(after_seq)`` with a QTimer.  While the
    parent tab is hidden, polling can be paused with ``set_active(False)`` so
    large batch conversions never update a hidden table.
    """

    POLL_INTERVAL_MS = 150

    def __init__(self, logger=None, parent=None):
        super().__init__(parent)
        self.logger = logger or get_logger()
        self._last_seq = 0
        self._active = False
        self._pending_sources = set()

        self.setObjectName("logViewer")
        self._build_ui()

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(self.POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._drain_logs)

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Row 1: level filters
        level_row = QtWidgets.QHBoxLayout()
        level_row.setSpacing(8)
        level_row.addWidget(QtWidgets.QLabel("Filter:"))
        self._filters = {}
        for level in _FILTER_ORDER:
            cb = QtWidgets.QCheckBox(level.title())
            cb.setChecked(level in _DEFAULT_CHECKED)
            cb.setStyleSheet(f"QCheckBox {{ color: {_LEVEL_COLORS[level]}; }}")
            cb.stateChanged.connect(self._refresh_filters)
            self._filters[level] = cb
            level_row.addWidget(cb)
        level_row.addStretch()
        root.addLayout(level_row)

        # Row 2: presets / search / source / actions
        tool_row = QtWidgets.QHBoxLayout()
        tool_row.setSpacing(6)

        tool_row.addWidget(QtWidgets.QLabel("View:"))
        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.addItem("All", "all")
        self.preset_combo.addItem("Validation", "validation")
        self.preset_combo.addItem("Errors Only", "errors")
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        tool_row.addWidget(self.preset_combo)

        tool_row.addWidget(QtWidgets.QLabel("Text:"))
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Filter message / source / context")
        self.search_edit.textChanged.connect(self._on_search_changed)
        tool_row.addWidget(self.search_edit, 1)

        tool_row.addWidget(QtWidgets.QLabel("Source:"))
        self.source_combo = QtWidgets.QComboBox()
        self.source_combo.addItem("All Sources", "")
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        tool_row.addWidget(self.source_combo, 1)

        self.auto_scroll = QtWidgets.QCheckBox("Auto scroll")
        self.auto_scroll.setChecked(True)
        tool_row.addWidget(self.auto_scroll)

        self.clear_btn = QtWidgets.QPushButton("Clear")
        self.clear_btn.setObjectName("closeBtn")
        self.clear_btn.clicked.connect(self.clear_logs)
        tool_row.addWidget(self.clear_btn)

        self.copy_btn = QtWidgets.QPushButton("Copy")
        self.copy_btn.clicked.connect(self.copy_visible_logs)
        tool_row.addWidget(self.copy_btn)
        root.addLayout(tool_row)

        self.model = LogModel(self)
        self.proxy = LogFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        self.table = QtWidgets.QTableView()
        self.table.setObjectName("logTable")
        self.table.setModel(self.proxy)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 78)
        self.table.setColumnWidth(1, 58)
        self.table.setColumnWidth(2, 118)
        self.table.setColumnWidth(3, 130)
        root.addWidget(self.table, 1)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setObjectName("logStatus")
        root.addWidget(self.status_label)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_active(self, active):
        self._active = bool(active)
        if self._active:
            self._drain_logs()
            self._timer.start()
        else:
            self._timer.stop()

    def apply_preset(self, preset_name):
        idx = self.preset_combo.findData(preset_name)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        else:
            self._on_preset_changed()
        self._drain_logs()

    def refresh(self):
        self._drain_logs()

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------
    def _refresh_filters(self):
        self.proxy.set_levels(
            level for level, cb in self._filters.items() if cb.isChecked()
        )

    def _on_search_changed(self, text):
        self.proxy.set_text(text)

    def _on_source_changed(self):
        self.proxy.set_source(self.source_combo.currentData() or "")

    def _on_preset_changed(self):
        preset = self.preset_combo.currentData()
        if preset == "validation":
            self._set_levels(_VALIDATION_LEVELS)
            self._select_source("ConfigValidator")
        elif preset == "errors":
            self._set_levels(_ERRORS_ONLY_LEVELS)
            self._select_source("")
        else:
            self._set_levels(set(_FILTER_ORDER))
            self._select_source("")
        self._refresh_filters()

    def _set_levels(self, levels):
        for level, cb in self._filters.items():
            cb.blockSignals(True)
            cb.setChecked(level in levels)
            cb.blockSignals(False)

    def _select_source(self, source):
        if not source:
            self.source_combo.setCurrentIndex(0)
            return
        idx = self.source_combo.findData(source)
        if idx < 0:
            self.source_combo.addItem(source, source)
            idx = self.source_combo.findData(source)
        self.source_combo.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # Data polling
    # ------------------------------------------------------------------
    def _drain_logs(self):
        records = self.logger.poll(self._last_seq)
        if records:
            self._last_seq = records[-1].seq
            self.model.append_records(records)
            self._update_source_combo(records)
            if self.auto_scroll.isChecked():
                self._scroll_to_bottom()
        self._update_status()

    def _update_source_combo(self, records):
        current = self.source_combo.currentData() or ""
        changed = False
        for record in records:
            if record.source and record.source not in self._pending_sources:
                self._pending_sources.add(record.source)
                self.source_combo.addItem(record.source, record.source)
                changed = True
        if changed and current:
            idx = self.source_combo.findData(current)
            if idx >= 0:
                self.source_combo.setCurrentIndex(idx)

    def _scroll_to_bottom(self):
        if self.proxy.rowCount():
            self.table.scrollToBottom()

    def _update_status(self):
        total = self.model.rowCount(QtCore.QModelIndex())
        shown = self.proxy.rowCount()
        drop = self.logger.dropped
        critical = self.logger.dropped_critical
        text = f"{shown}/{total} shown"
        if drop:
            text += f" | dropped {drop}"
        if critical:
            text += f" (critical {critical})"
        text += f" | buffer {self.logger.max_records}"
        self.status_label.setText(text)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def clear_logs(self):
        self.logger.clear()
        self.model.clear()
        self._last_seq = self.logger.last_seq
        self._update_status()

    def copy_visible_logs(self):
        records = []
        for row in range(self.proxy.rowCount()):
            src = self.proxy.mapToSource(self.proxy.index(row, 0))
            record = self.model.record_at(src.row())
            if record:
                records.append(f"[{record.level}] {record.source} {record.message}")
        QtWidgets.QApplication.clipboard().setText("\n".join(records))

    def showEvent(self, event):
        super().showEvent(event)
        if self._active:
            self._drain_logs()
