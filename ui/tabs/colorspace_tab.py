from ui import QtWidgets, QtCore, QtGui, cmds
from core.colorspace import ColorSpaceMatcher, MatchState
from core.logger import get_logger
from ui.operation_state import OperationGuard

_SOURCE = "ColorspaceTab"

#: Upper bound on table rows: a scene with thousands of file nodes would
#: otherwise build 5*N Qt items on every Refresh.
MAX_TABLE_ROWS = 5000

_STATE_RANK = {
    MatchState.CONFLICT: 0,
    MatchState.AMBIGUOUS: 1,
    MatchState.INVALID: 2,
    MatchState.UNMATCHED: 3,
    MatchState.MATCHED: 4,
}


def _state_from_value(value):
    """``MatchState`` for a raw value, or None when it is not a valid state.

    Uses the public constructor instead of the private
    ``Enum._value2member_map_`` so it keeps working across Python versions.
    """
    try:
        return MatchState(value)
    except ValueError:  # noqa: silent-fallback unknown value -> None
        return None


class _StateItem(QtWidgets.QTableWidgetItem):
    """Diagnostic column item that sorts by problem severity, not alphabetically."""

    def _key(self):
        try:
            return MatchState(self.text().split(":", 1)[0])
        except ValueError:  # noqa: silent-fallback unknown state sorts last
            return None

    def __lt__(self, other):
        # ``other`` may be a plain QTableWidgetItem if a row is ever built
        # differently; sort it last instead of raising AttributeError.
        other_key = getattr(other, "_key", lambda: None)()
        return _STATE_RANK.get(self._key(), 99) < _STATE_RANK.get(other_key, 99)


class ColorspaceTab:

    def __init__(self, logger=None, config=None):
        self.log = logger or get_logger()
        self.matcher = ColorSpaceMatcher(config_loader=config, logger=self.log)
        self.refresh_btn = None
        self.status_label = None
        self.table = None
        self.manual_combo = None
        self._loading = False
        self._results = []
        self.guard = OperationGuard(logger=self.log, source=_SOURCE)
        self._busy_widgets = []

    @property
    def on_busy_change(self):
        return self.guard.on_change

    @on_busy_change.setter
    def on_busy_change(self, callback):
        self.guard.on_change = callback

    def _guarded(self, action):
        """Run a scene-modifying action under the busy guard.

        Rejects re-entry and reports the busy state window-wide, so a batch on
        another tab and this action can never overlap.
        """
        if not self.guard.try_begin():
            return
        try:
            return action()
        finally:
            self.guard.end()

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
        self.refresh_btn.clicked.connect(lambda: self._guarded(self._refresh))
        btn_row.addWidget(self.refresh_btn)

        btn_ignore = QtWidgets.QPushButton("Set ignoreColorSpaceFileRules on All File Nodes")
        btn_ignore.setMinimumHeight(32)
        btn_ignore.clicked.connect(lambda: self._guarded(self._ignore_color_space_rules))
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
        btn_apply_manual.clicked.connect(lambda: self._guarded(self._apply_manual))
        manual_layout.addWidget(btn_apply_manual)
        layout.addWidget(manual_group)

        apply_group = QtWidgets.QGroupBox("Apply Automatic Match")
        apply_layout = QtWidgets.QHBoxLayout(apply_group)
        apply_layout.setContentsMargins(12, 14, 12, 12)
        apply_layout.setSpacing(8)

        btn_apply_selected = QtWidgets.QPushButton("Apply Selected")
        btn_apply_selected.setObjectName("convertBtn")
        btn_apply_selected.setMinimumHeight(32)
        btn_apply_selected.clicked.connect(lambda: self._guarded(self._apply_selected))
        apply_layout.addWidget(btn_apply_selected)

        btn_apply_all = QtWidgets.QPushButton("Apply All Matched")
        btn_apply_all.setObjectName("convertBtn")
        btn_apply_all.setMinimumHeight(32)
        btn_apply_all.clicked.connect(lambda: self._guarded(self._apply_all_matched))
        apply_layout.addWidget(btn_apply_all)

        apply_layout.addStretch()
        layout.addWidget(apply_group)

        self._populate_manual_combo()
        self._busy_widgets = [
            self.refresh_btn, btn_ignore, self.manual_combo,
            btn_apply_manual, btn_apply_selected, btn_apply_all,
        ]
        self._widget = widget
        return widget

    def _populate_manual_combo(self):
        current = self.manual_combo.currentText()
        available = sorted(self.matcher.available_spaces())
        self.manual_combo.clear()
        self.manual_combo.addItems(available)
        if current and current in available:
            self.manual_combo.setCurrentText(current)

    def _refresh(self):
        # Pick up session-only channel overrides set in the Batch Builder tab.
        self.matcher.reload_name_driver()
        try:
            results = self.matcher.scan()
        except Exception as exc:
            self.log.error(f"Failed to scan file nodes: {exc}", source=_SOURCE)
            self.status_label.setText(f"Error scanning scene: {exc}")
            return

        self._results = results
        self._populate_manual_combo()
        self._populate_table(results)

    def _populate_table(self, results):
        self._loading = True
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        # A scene with thousands of file nodes would otherwise build 5*N Qt
        # items on every Refresh; bound the table and tell the user.
        shown = results[:MAX_TABLE_ROWS]
        for result in shown:
            row = self.table.rowCount()
            self.table.insertRow(row)

            node_item = QtWidgets.QTableWidgetItem(result.file_node)
            node_item.setData(QtCore.Qt.UserRole, result)
            self.table.setItem(row, 0, node_item)
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(result.file_path))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(result.actual_colorspace))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(result.prematch_colorspace or ""))
            diagnostic = f"{result.state.value}: {result.diagnostic}"
            if not result.evidence_complete:
                # "No conflict found" is weaker when the channel trace was
                # truncated; surface that instead of leaving it invisible.
                diagnostic += " [channel evidence incomplete]"
            self.table.setItem(row, 4, _StateItem(diagnostic))
            path_item = self.table.item(row, 1)
            if path_item:
                path_item.setToolTip(result.file_path)

            if result.state != MatchState.MATCHED:
                for col in range(5):
                    item = self.table.item(row, col)
                    if item:
                        item.setBackground(QtGui.QColor("#4a2b2b"))

        self.table.setSortingEnabled(True)
        self._update_status(len(results), shown=len(shown))
        self._loading = False

    def _update_status(self, total, shown=None):
        counts = {}
        for result in self._results:
            state = result.state.value
            counts[state] = counts.get(state, 0) + 1
        ordered = sorted(
            counts.items(),
            key=lambda kv: _STATE_RANK.get(_state_from_value(kv[0]), 99),
        )
        summary = ", ".join(f"{k} {v}" for k, v in ordered)
        suffix = ""
        if shown is not None and shown < total:
            suffix = f" (showing first {shown}; apply still covers every match)"
        self.status_label.setText(f"{total} file node(s): {summary}{suffix}")

    def _selected_results(self):
        results = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item:
                result = item.data(QtCore.Qt.UserRole)
                if result:
                    results.append(result)
        return results

    def _sync_selection(self):
        if self._loading:
            return
        nodes = [result.file_node for result in self._selected_results()]
        try:
            if nodes:
                cmds.select(nodes, replace=True)
            else:
                cmds.select(clear=True)
        except Exception as exc:
            self.log.warn(f"Failed to sync Maya selection: {exc}", source=_SOURCE)

    def _apply_selected(self):
        results = self._selected_results()
        if not results:
            self.log.warn("Please select file node rows first.", source=_SOURCE)
            return
        self._apply_rows(results, "Apply Selected")

    def _apply_all_matched(self):
        results = [
            result for result in self._results
            if result.state == MatchState.MATCHED
        ]
        if not results:
            self.log.info("No MATCHED file nodes to apply.", source=_SOURCE)
            return
        self._apply_rows(results, "Apply All Matched")

    def _apply_rows(self, results, label):
        # Revalidate right before writing: a cached recommendation can be stale
        # after a re-path or an OCIO config change.
        outcome = self.matcher.apply_matched(results, revalidate=True)
        for node, colorspace in outcome["applied"]:
            self._set_colorspace_column(node, colorspace)

        stale = outcome.get("stale", [])
        self.log.info(
            f"{label}: applied {len(outcome['applied'])}, "
            f"skipped {outcome['skipped']} non-MATCHED/stale row(s), "
            f"failed {len(outcome['failed'])}.",
            source=_SOURCE,
        )
        if stale:
            self.log.warn(
                f"{label}: {len(stale)} recommendation(s) are no longer valid and "
                f"were not applied; refresh the list and re-check",
                source=_SOURCE,
                nodes=tuple(stale),
            )

    def _apply_manual(self):
        cs = self.manual_combo.currentText().strip()
        if not cs:
            self.log.warn("Please pick a colorspace first.", source=_SOURCE)
            return
        results = self._selected_results()
        if not results:
            self.log.warn("Please select file node rows first.", source=_SOURCE)
            return

        outcome = self.matcher.set_colorspace(
            [result.file_node for result in results], cs
        )
        for node, colorspace in outcome["applied"]:
            self._set_colorspace_column(node, colorspace)

        self.log.info(
            f"Manual assignment: set '{cs}' on "
            f"{len(outcome['applied'])}/{len(results)} file node(s), "
            f"failed {len(outcome['failed'])}.",
            source=_SOURCE,
        )

    def _set_colorspace_column(self, node, value):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if not item:
                continue
            result = item.data(QtCore.Qt.UserRole)
            if result and result.file_node == node:
                self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(value))
                break

    def _ignore_color_space_rules(self):
        try:
            outcome = self.matcher.ignore_color_space_file_rules()
        except Exception as exc:
            self.log.error(f"Failed to set color space file rules: {exc}", source=_SOURCE)
            return
        file_nodes = outcome["nodes"]
        if not file_nodes:
            self.log.warn("No file nodes found in scene.", source=_SOURCE)
            return
        cmds.select(file_nodes, replace=True)
        self.log.info(
            f"Set ignoreColorSpaceFileRules=1 on "
            f"{len(outcome['applied'])}/{len(file_nodes)} file nodes.",
            source=_SOURCE,
        )