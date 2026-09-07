from ui import QtWidgets, QtCore, QtGui, cmds
from core.colorspace import ColorSpaceMatcher, MatchState
from core.logger import get_logger

_SOURCE = "ColorspaceTab"

_STATE_RANK = {
    MatchState.CONFLICT: 0,
    MatchState.AMBIGUOUS: 1,
    MatchState.INVALID: 2,
    MatchState.UNMATCHED: 3,
    MatchState.MATCHED: 4,
}


class _StateItem(QtWidgets.QTableWidgetItem):
    """Diagnostic column item that sorts by problem severity, not alphabetically."""

    def _key(self):
        try:
            return MatchState(self.text().split(":", 1)[0])
        except ValueError:
            return None

    def __lt__(self, other):
        return _STATE_RANK.get(self._key(), 99) < _STATE_RANK.get(other._key(), 99)


class ColorspaceTab:

    def __init__(self, logger=None):
        self.log = logger or get_logger()
        self.matcher = ColorSpaceMatcher(logger=self.log)
        self.refresh_btn = None
        self.status_label = None
        self.table = None
        self.manual_combo = None
        self._loading = False

    def build_ui(self):
        widget = QtWidgets.QWidget()
        widget.setObjectName("colorspaceTab")
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        list_group = QtWidgets.QGroupBox("Scene File Nodes")
        list_layout = QtWidgets.QVBoxLayout(list_group)
        list_layout.setContentsMargins(12, 14, 12, 12)
        list_layout.setSpacing(8)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.setObjectName("refreshBtn")
        self.refresh_btn.setMinimumHeight(32)
        self.refresh_btn.clicked.connect(self._refresh)
        btn_row.addWidget(self.refresh_btn)

        btn_ignore = QtWidgets.QPushButton("Set ignoreColorSpaceFileRules on All File Nodes")
        btn_ignore.setMinimumHeight(32)
        btn_ignore.clicked.connect(self._ignore_color_space_rules)
        btn_row.addWidget(btn_ignore)

        btn_row.addStretch()
        list_layout.addLayout(btn_row)

        self.status_label = QtWidgets.QLabel("No scan yet. Click Refresh.")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("logStatus")
        list_layout.addWidget(self.status_label)

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["File Node", "File Path", "Colorspace", "Prematch Colorspace", "Diagnostic"]
        )
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(1, 380)
        self.table.setColumnWidth(2, 170)
        self.table.setColumnWidth(3, 190)
        self.table.itemSelectionChanged.connect(self._sync_selection)
        list_layout.addWidget(self.table)

        layout.addWidget(list_group, stretch=3)

        manual_group = QtWidgets.QGroupBox("Manual Colorspace Assignment")
        manual_layout = QtWidgets.QHBoxLayout(manual_group)
        manual_layout.setContentsMargins(12, 14, 12, 12)
        manual_layout.setSpacing(8)

        manual_layout.addWidget(QtWidgets.QLabel("Colorspace:"))
        self.manual_combo = QtWidgets.QComboBox()
        self.manual_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        manual_layout.addWidget(self.manual_combo, 1)

        btn_apply_manual = QtWidgets.QPushButton("Apply to Selected File Nodes")
        btn_apply_manual.setObjectName("applyCsBtn")
        btn_apply_manual.setMinimumHeight(32)
        btn_apply_manual.clicked.connect(self._apply_manual)
        manual_layout.addWidget(btn_apply_manual)
        layout.addWidget(manual_group)

        apply_group = QtWidgets.QGroupBox("Apply Automatic Match")
        apply_layout = QtWidgets.QHBoxLayout(apply_group)
        apply_layout.setContentsMargins(12, 14, 12, 12)
        apply_layout.setSpacing(8)

        btn_apply_selected = QtWidgets.QPushButton("Apply Selected")
        btn_apply_selected.setObjectName("convertBtn")
        btn_apply_selected.setMinimumHeight(32)
        btn_apply_selected.clicked.connect(self._apply_selected)
        apply_layout.addWidget(btn_apply_selected)

        btn_apply_all = QtWidgets.QPushButton("Apply All Matched")
        btn_apply_all.setObjectName("convertBtn")
        btn_apply_all.setMinimumHeight(32)
        btn_apply_all.clicked.connect(self._apply_all_matched)
        apply_layout.addWidget(btn_apply_all)

        apply_layout.addStretch()
        layout.addWidget(apply_group)

        self._populate_manual_combo()
        self._widget = widget
        return widget

    def _populate_manual_combo(self):
        current = self.manual_combo.currentText()
        available = sorted(self.matcher.resolver.available_spaces())
        self.manual_combo.clear()
        self.manual_combo.addItems(available)
        if current and current in available:
            self.manual_combo.setCurrentText(current)

    def _refresh(self):
        try:
            file_nodes = cmds.ls(type="file") or []
        except Exception as exc:
            self.log.error(f"Failed to list file nodes: {exc}", source=_SOURCE)
            self.status_label.setText(f"Error scanning scene: {exc}")
            return

        self.matcher.reset()
        self._populate_manual_combo()
        self._populate_table(file_nodes)

    def _populate_table(self, file_nodes):
        self._loading = True
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for node in file_nodes:
            try:
                result = self.matcher.match(node)
            except Exception as exc:
                self.log.error(f"Failed to match colorspace for {node}: {exc}", source=_SOURCE)
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            node_item = QtWidgets.QTableWidgetItem(result.file_node)
            node_item.setData(QtCore.Qt.UserRole, {
                "node": result.file_node,
                "state": result.state.value,
                "prematch": result.prematch_colorspace,
            })
            self.table.setItem(row, 0, node_item)
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(result.file_path))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(result.actual_colorspace))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(result.prematch_colorspace or ""))
            self.table.setItem(row, 4, _StateItem(f"{result.state.value}: {result.diagnostic}"))
            path_item = self.table.item(row, 1)
            if path_item:
                path_item.setToolTip(result.file_path)

            if result.state != MatchState.MATCHED:
                for col in range(5):
                    item = self.table.item(row, col)
                    if item:
                        item.setBackground(QtGui.QColor("#4a2b2b"))

        self.table.setSortingEnabled(True)
        self._update_status(len(file_nodes))
        self._loading = False

    def _update_status(self, total):
        counts = {}
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                data = item.data(QtCore.Qt.UserRole)
                state = data.get("state") if data else None
                if state:
                    counts[state] = counts.get(state, 0) + 1
        ordered = sorted(
            counts.items(),
            key=lambda kv: _STATE_RANK.get(MatchState._value2member_map_.get(kv[0]), 99),
        )
        summary = ", ".join(f"{k} {v}" for k, v in ordered)
        self.status_label.setText(f"{total} file node(s): {summary}")

    def _selected_rows(self):
        rows = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item:
                data = item.data(QtCore.Qt.UserRole)
                if data:
                    rows.append(data)
        return rows

    def _sync_selection(self):
        if self._loading:
            return
        nodes = [data["node"] for data in self._selected_rows()]
        try:
            if nodes:
                cmds.select(nodes, replace=True)
            else:
                cmds.select(clear=True)
        except Exception as exc:
            self.log.warn(f"Failed to sync Maya selection: {exc}", source=_SOURCE)

    def _apply_selected(self):
        rows = self._selected_rows()
        if not rows:
            self.log.warn("Please select file node rows first.", source=_SOURCE)
            return
        self._apply_rows(rows, "Apply Selected")

    def _apply_all_matched(self):
        rows = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                data = item.data(QtCore.Qt.UserRole)
                if data and data.get("state") == MatchState.MATCHED.value:
                    rows.append(data)
        if not rows:
            self.log.info("No MATCHED file nodes to apply.", source=_SOURCE)
            return
        self._apply_rows(rows, "Apply All Matched")

    def _apply_rows(self, rows, label):
        try:
            cmds.undoInfo(openChunk=True)
        except Exception as exc:
            self.log.warn(f"Failed to open undo chunk: {exc}", source=_SOURCE)

        applied = 0
        skipped = 0
        try:
            for data in rows:
                node = data["node"]
                state = data["state"]
                prematch = data.get("prematch") or ""
                if state == MatchState.MATCHED.value and prematch:
                    try:
                        cmds.setAttr(f"{node}.colorSpace", prematch, type="string")
                        applied += 1
                        self._set_colorspace_column(node, prematch)
                        self.log.debug(f"Set {node}.colorSpace = {prematch}", source=_SOURCE)
                    except Exception as exc:
                        self.log.warn(f"Failed to set color space on {node}: {exc}", source=_SOURCE)
                else:
                    skipped += 1
                    self.log.warn(
                        f"Skipped {node}: state {state} is not auto-applicable "
                        "(only MATCHED can be applied automatically).",
                        source=_SOURCE,
                    )
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception as exc:
                self.log.warn(f"Failed to close undo chunk: {exc}", source=_SOURCE)

        self.log.info(
            f"{label}: applied {applied}, skipped {skipped} non-MATCHED row(s).",
            source=_SOURCE,
        )

    def _apply_manual(self):
        cs = self.manual_combo.currentText().strip()
        if not cs:
            self.log.warn("Please pick a colorspace first.", source=_SOURCE)
            return
        rows = self._selected_rows()
        if not rows:
            self.log.warn("Please select file node rows first.", source=_SOURCE)
            return

        try:
            cmds.undoInfo(openChunk=True)
        except Exception as exc:
            self.log.warn(f"Failed to open undo chunk: {exc}", source=_SOURCE)

        applied = 0
        try:
            for data in rows:
                node = data["node"]
                try:
                    cmds.setAttr(f"{node}.colorSpace", cs, type="string")
                    applied += 1
                    self._set_colorspace_column(node, cs)
                    self.log.debug(f"Set {node}.colorSpace = {cs}", source=_SOURCE)
                except Exception as exc:
                    self.log.warn(f"Failed to set color space on {node}: {exc}", source=_SOURCE)
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception as exc:
                self.log.warn(f"Failed to close undo chunk: {exc}", source=_SOURCE)

        self.log.info(
            f"Manual assignment: set '{cs}' on {applied}/{len(rows)} file node(s).",
            source=_SOURCE,
        )

    def _set_colorspace_column(self, node, value):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if not item:
                continue
            data = item.data(QtCore.Qt.UserRole)
            if data and data.get("node") == node:
                self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(value))
                break

    def _ignore_color_space_rules(self):
        try:
            file_nodes = cmds.ls(type="file") or []
        except Exception as exc:
            self.log.error(f"Failed to list file nodes: {exc}", source=_SOURCE)
            return
        if not file_nodes:
            self.log.warn("No file nodes found in scene.", source=_SOURCE)
            return
        count = 0
        for f in file_nodes:
            try:
                cmds.setAttr(f"{f}.ignoreColorSpaceFileRules", 1)
                count += 1
            except Exception as exc:
                self.log.warn(f"Failed to set ignoreColorSpaceFileRules on {f}: {exc}", source=_SOURCE)
        cmds.select(file_nodes, replace=True)
        self.log.info(
            f"Set ignoreColorSpaceFileRules=1 on {count}/{len(file_nodes)} file nodes.",
            source=_SOURCE,
        )