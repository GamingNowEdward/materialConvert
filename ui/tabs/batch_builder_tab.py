import os

from ui import QtWidgets, QtCore, QtGui
from ui.widgets import populate_material_targets
from ui.feedback import show_result_banner
from ui.operation_state import OperationGuard
from core.builder_context import BuilderContext
from core.logger import get_logger
from core.texture_scanner import TextureScanner
from core.batch_builder import BatchBuilder
from core.results import summarize_build_results

_SOURCE = "BatchBuilderTab"

#: Row backgrounds by status.  ``CONFLICT (kept)`` is informational (that file is
#: the one used), a dropped duplicate and an unrecognised file need attention.
_KEPT_CONFLICT_BG = "#4a3d1f"
_DROPPED_CONFLICT_BG = "#5a2d2d"
_UNPARSED_BG = "#333a44"


class BatchBuilderTab:

    def __init__(self, ctx: BuilderContext, logger=None):
        self.ctx = ctx
        self.log = logger or get_logger()
        self.config = ctx.config
        self.scanner = TextureScanner(logger=self.log)
        self.batch_builder = BatchBuilder(ctx, logger=self.log)
        self.scan_result = {
            "materials": [],
            "unparsed": [],
            "conflicts": [],
        }
        self.directory_input = None
        self.cb_recursive = None
        self.target_combo = None
        self.cb_full_chain = None
        self.cb_qss = None
        self.cb_skip_conflicts = None
        self.table = None
        self.materials_to_build_list = None
        self.materials_to_build_label = None
        self.progress_bar = None
        self.guard = OperationGuard(logger=self.log, source=_SOURCE)
        self._busy_widgets = []

    @property
    def on_busy_change(self):
        return self.guard.on_change

    @on_busy_change.setter
    def on_busy_change(self, callback):
        self.guard.on_change = callback

    def build_ui(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        dir_group = QtWidgets.QGroupBox("Texture Directory")
        dir_layout = QtWidgets.QHBoxLayout(dir_group)
        dir_layout.setContentsMargins(12, 14, 12, 12)

        self.directory_input = QtWidgets.QLineEdit()
        self.directory_input.setPlaceholderText("Select a folder containing PBR textures...")
        btn_browse = QtWidgets.QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_directory)
        btn_scan = QtWidgets.QPushButton("Scan Directory")
        btn_scan.setObjectName("scanBtn")
        btn_scan.clicked.connect(self._scan_directory)

        self.cb_recursive = QtWidgets.QCheckBox("Include Subfolders")
        self.cb_recursive.setChecked(False)

        dir_layout.addWidget(self.directory_input, 1)
        dir_layout.addWidget(self.cb_recursive)
        dir_layout.addWidget(btn_browse)
        dir_layout.addWidget(btn_scan)
        layout.addWidget(dir_group)

        opt_group = QtWidgets.QGroupBox("Build Options")
        opt_layout = QtWidgets.QHBoxLayout(opt_group)
        opt_layout.setContentsMargins(12, 14, 12, 12)

        opt_layout.addWidget(QtWidgets.QLabel("Target Material:"))
        self.target_combo = QtWidgets.QComboBox()
        self.target_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._populate_target_list()
        opt_layout.addWidget(self.target_combo, 1)

        self.cb_full_chain = QtWidgets.QCheckBox("Use Full Builder Pipeline")
        self.cb_full_chain.setChecked(True)
        opt_layout.addWidget(self.cb_full_chain)

        self.cb_qss = QtWidgets.QCheckBox("Add To Quick Select Set")
        self.cb_qss.setChecked(True)
        opt_layout.addWidget(self.cb_qss)

        self.cb_skip_conflicts = QtWidgets.QCheckBox("Skip Materials With Conflicts")
        self.cb_skip_conflicts.setChecked(False)
        opt_layout.addWidget(self.cb_skip_conflicts)

        layout.addWidget(opt_group)

        btn_row = QtWidgets.QHBoxLayout()
        btn_build_all = QtWidgets.QPushButton("Build All")
        btn_build_all.setObjectName("convertBtn")
        btn_build_all.clicked.connect(lambda: self._build_materials(selected_only=False))
        btn_build_selected = QtWidgets.QPushButton("Build Selected")
        btn_build_selected.setObjectName("convertBtn")
        btn_build_selected.clicked.connect(lambda: self._build_materials(selected_only=True))
        btn_row.addStretch()
        btn_row.addWidget(btn_build_all)
        btn_row.addWidget(btn_build_selected)
        layout.addLayout(btn_row)
        self._busy_widgets = [
            btn_scan, btn_browse, self.directory_input, self.cb_recursive,
            self.target_combo, self.cb_full_chain, self.cb_qss,
            self.cb_skip_conflicts, btn_build_all, btn_build_selected,
        ]

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v / %m")
        layout.addWidget(self.progress_bar)

        table_group = QtWidgets.QGroupBox("Texture / Material List")
        table_layout = QtWidgets.QVBoxLayout(table_group)
        table_layout.setContentsMargins(12, 14, 12, 12)

        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Material", "Channel", "File", "Status"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 420)
        table_layout.addWidget(self.table)

        self.table_legend = QtWidgets.QLabel(
            "CONFLICT (kept): the file used for a duplicated channel. "
            "CONFLICT: duplicate dropped in favour of the kept file. "
            "UNPARSED: no channel keyword found in the file name."
        )
        self.table_legend.setWordWrap(True)
        self.table_legend.setObjectName("debugStatus")
        table_layout.addWidget(self.table_legend)

        layout.addWidget(table_group, stretch=3)

        mtb_group = QtWidgets.QGroupBox("Materials to Build")
        mtb_layout = QtWidgets.QVBoxLayout(mtb_group)
        mtb_layout.setContentsMargins(12, 14, 12, 12)
        self.materials_to_build_label = QtWidgets.QLabel("No materials scanned yet.")
        self.materials_to_build_list = QtWidgets.QListWidget()
        mtb_layout.addWidget(self.materials_to_build_label)
        mtb_layout.addWidget(self.materials_to_build_list)
        layout.addWidget(mtb_group, stretch=1)

        return widget

    def _populate_target_list(self):
        populate_material_targets(
            self.target_combo, self.config, logger=self.log,
            source=_SOURCE, label="batch builder",
        )

    def _browse_directory(self):
        directory = QtWidgets.QFileDialog.getExistingDirectory(None, "Select Texture Directory")
        if directory:
            self.directory_input.setText(directory)
            self.log.debug(f"Selected texture directory: {directory}", source=_SOURCE)

    def _scan_directory(self):
        directory = self.directory_input.text().strip()
        if not directory or not os.path.isdir(directory):
            self.log.warn("Please select a valid directory first.", source=_SOURCE)
            return

        recursive = self.cb_recursive.isChecked()
        self.scan_result = self.scanner.scan(directory, recursive=recursive)
        self._populate_table()
        self._populate_materials_to_build()

    def _populate_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        conflicts = self.scan_result.get("conflicts", [])
        conflicting = {(item["material"], item["common_attr"]) for item in conflicts}

        for material in self.scan_result["materials"]:
            for common_attr, data in material["channels"].items():
                row = self.table.rowCount()
                self.table.insertRow(row)

                name_item = QtWidgets.QTableWidgetItem(material["name"])
                name_item.setData(QtCore.Qt.UserRole, {
                    "type": "parsed",
                    "material": material["name"],
                })
                self.table.setItem(row, 0, name_item)
                self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(data["channel"]))
                self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(data["path"]))
                status = ("CONFLICT (kept)"
                          if (material["name"], common_attr) in conflicting else "OK")
                status_item = QtWidgets.QTableWidgetItem(status)
                self.table.setItem(row, 3, status_item)
                if (material["name"], common_attr) in conflicting:
                    self._paint_row(row, _KEPT_CONFLICT_BG)

        # Every rejected candidate gets its own row so the conflict is visible
        # instead of only living in the log.
        for item in conflicts:
            for path in item.get("dropped", []):
                row = self.table.rowCount()
                self.table.insertRow(row)

                name_item = QtWidgets.QTableWidgetItem(item["material"])
                name_item.setData(QtCore.Qt.UserRole, {
                    "type": "parsed",
                    "material": item["material"],
                })
                self.table.setItem(row, 0, name_item)
                self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(
                    self._channel_label(item["material"], item["common_attr"])))
                self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(path))
                self.table.setItem(row, 3, QtWidgets.QTableWidgetItem("CONFLICT"))
                self._paint_row(row, _DROPPED_CONFLICT_BG)

        for path in self.scan_result["unparsed"]:
            row = self.table.rowCount()
            self.table.insertRow(row)

            name_item = QtWidgets.QTableWidgetItem("(Unparsed)")
            name_item.setData(QtCore.Qt.UserRole, {"type": "unparsed"})
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem("-"))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(path))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem("UNPARSED"))

            self._paint_row(row, _UNPARSED_BG)

        self.table.setSortingEnabled(True)

    def _paint_row(self, row, color):
        if color is None:
            return
        for col in range(4):
            item = self.table.item(row, col)
            if item:
                item.setBackground(QtGui.QColor(color))

    def _channel_label(self, material_name, common_attr):
        for material in self.scan_result["materials"]:
            if material["name"] != material_name:
                continue
            data = material["channels"].get(common_attr)
            if data:
                return data.get("channel", common_attr)
        return common_attr

    def _populate_materials_to_build(self):
        self.materials_to_build_list.clear()
        materials = self.scan_result["materials"]
        if not materials:
            self.materials_to_build_label.setText("No materials scanned yet.")
            return

        self.materials_to_build_label.setText(
            f"{len(materials)} material(s) will be created."
        )
        conflicts_per_material = {}
        for item in self.scan_result.get("conflicts", []):
            name = item["material"]
            conflicts_per_material[name] = conflicts_per_material.get(name, 0) + 1
        for material in materials:
            channel_count = len(material["channels"])
            conflict_count = conflicts_per_material.get(material["name"], 0)
            suffix = f", {conflict_count} conflict(s)" if conflict_count else ""
            self.materials_to_build_list.addItem(
                f"{material['name']} ({channel_count} channels{suffix})"
            )

    def _selected_material_names(self):
        names = set()
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if not item:
                continue
            data = item.data(QtCore.Qt.UserRole)
            if data and data.get("type") == "parsed":
                names.add(data["material"])
        return names

    def _build_materials(self, selected_only=False):
        if not self.scan_result["materials"]:
            self.log.error("No scanned materials to build.", source=_SOURCE)
            return

        target_node_type = self.target_combo.currentData()
        if not target_node_type:
            self.log.error("Target material type is not selected.", source=_SOURCE)
            return

        use_full_chain = self.cb_full_chain.isChecked()
        use_qss = self.cb_qss.isChecked()

        if selected_only:
            selected_names = self._selected_material_names()
            materials = [
                m for m in self.scan_result["materials"] if m["name"] in selected_names
            ]
            if not materials:
                self.log.error("No materials selected in the table.", source=_SOURCE)
                return
        else:
            materials = self.scan_result["materials"]

        # Snapshot the list: a re-scan while the batch runs must not alter it.
        materials = list(materials)
        conflict_names = set(self.scan_result.get("conflict_materials", []))
        if conflict_names and self.cb_skip_conflicts.isChecked():
            kept = [m for m in materials if m["name"] not in conflict_names]
            skipped = len(materials) - len(kept)
            if skipped:
                self.log.warn(
                    f"Skipping {skipped} material(s) with unresolved texture conflicts: "
                    f"{', '.join(sorted(conflict_names))}",
                    source=_SOURCE,
                )
            materials = kept
            if not materials:
                self.log.error(
                    "Every selected material has unresolved texture conflicts; nothing built.",
                    source=_SOURCE,
                )
                return

        total = len(materials)
        if not self.guard.try_begin():
            return
        try:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            QtWidgets.QApplication.processEvents()

            def _on_progress(done, total_count, result):
                # Throttle repaints: roughly every 5 materials and always the last one.
                if done == total_count or done % 5 == 0:
                    try:
                        self.progress_bar.setValue(done)
                        QtWidgets.QApplication.processEvents()
                    except RuntimeError as exc:
                        self.log.debug(f"Progress UI unavailable: {exc}", source=_SOURCE)

            results = self.batch_builder.build_all(
                materials,
                target_node_type,
                use_full_chain=use_full_chain,
                use_qss=use_qss,
                on_progress=_on_progress,
            )

            self.progress_bar.setValue(total)
            self.progress_bar.setVisible(False)

            summary = summarize_build_results(results)
            issue_results = [r for r in results if r.has_issues]
            if issue_results:
                self.log.warn(
                    f"{summary['with_issues']} material(s) built with channel issue(s); "
                    f"see the log for details",
                    source=_SOURCE,
                    nodes=tuple(r.new_material or r.material for r in issue_results),
                )
            failed_results = [r for r in results if not r.built]
            if failed_results:
                self.log.error(
                    f"{summary['failed']} material(s) failed to build; see the log for details",
                    source=_SOURCE,
                    nodes=tuple(r.new_material or r.material for r in failed_results),
                )
            show_result_banner(
                summary["failed"], summary["with_issues"],
                ok_message=f"{summary['built']} material(s) built",
            )
        finally:
            self.guard.end()
            try:
                self.progress_bar.setVisible(False)
            except RuntimeError as exc:
                self.log.debug(f"Progress bar already destroyed: {exc}", source=_SOURCE)
