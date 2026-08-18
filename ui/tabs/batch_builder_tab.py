import os

from ui import QtWidgets, QtCore, QtGui, cmds
from core.builder_context import BuilderContext
from core.config_loader import ConfigLoader
from core.texture_scanner import TextureScanner
from core.batch_builder import BatchBuilder


class BatchBuilderTab:

    def __init__(self, ctx: BuilderContext):
        self.ctx = ctx
        self.config = ConfigLoader()
        self.scanner = TextureScanner()
        self.batch_builder = BatchBuilder(ctx)
        self.scan_result = {
            "materials": [],
            "unparsed": [],
            "conflicts": [],
        }
        self.directory_input = None
        self.target_combo = None
        self.cb_full_chain = None
        self.cb_qss = None
        self.table = None
        self.materials_to_build_list = None
        self.materials_to_build_label = None
        self.log_output = None
        self.progress_bar = None

    def build_ui(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Directory
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

        dir_layout.addWidget(self.directory_input, 1)
        dir_layout.addWidget(btn_browse)
        dir_layout.addWidget(btn_scan)
        layout.addWidget(dir_group)

        # Build options
        opt_group = QtWidgets.QGroupBox("Build Options")
        opt_layout = QtWidgets.QHBoxLayout(opt_group)
        opt_layout.setContentsMargins(12, 14, 12, 12)

        opt_layout.addWidget(QtWidgets.QLabel("Target Material:"))
        self.target_combo = QtWidgets.QComboBox()
        self.target_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._populate_target_list()
        opt_layout.addWidget(self.target_combo, 1)

        self.cb_full_chain = QtWidgets.QCheckBox("Use Full Builder Pipeline (CC/Layered)")
        self.cb_full_chain.setChecked(True)
        opt_layout.addWidget(self.cb_full_chain)

        self.cb_qss = QtWidgets.QCheckBox("Add To Quick Select Set")
        self.cb_qss.setChecked(True)
        opt_layout.addWidget(self.cb_qss)

        layout.addWidget(opt_group)

        # Action buttons
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

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v / %m")
        layout.addWidget(self.progress_bar)

        # Texture / Material List (parsed + unparsed)
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

        layout.addWidget(table_group, stretch=3)

        # Materials to Build (planned materials from current scan)
        mtb_group = QtWidgets.QGroupBox("Materials to Build")
        mtb_layout = QtWidgets.QVBoxLayout(mtb_group)
        mtb_layout.setContentsMargins(12, 14, 12, 12)
        self.materials_to_build_label = QtWidgets.QLabel("No materials scanned yet.")
        self.materials_to_build_list = QtWidgets.QListWidget()
        mtb_layout.addWidget(self.materials_to_build_label)
        mtb_layout.addWidget(self.materials_to_build_list)
        layout.addWidget(mtb_group, stretch=1)

        # Log
        log_group = QtWidgets.QGroupBox("Log")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        log_layout.setContentsMargins(12, 14, 12, 12)
        self.log_output = QtWidgets.QPlainTextEdit()
        self.log_output.setReadOnly(True)
        log_layout.addWidget(self.log_output)
        layout.addWidget(log_group, stretch=2)

        return widget

    def _populate_target_list(self):
        self.target_combo.clear()
        all_configs = self.config.get_all_material_configs()
        for node_type in sorted(all_configs.keys()):
            display_name = self.config.get_display_name(node_type)
            self.target_combo.addItem(display_name, node_type)

    def _browse_directory(self):
        directory = QtWidgets.QFileDialog.getExistingDirectory(None, "Select Texture Directory")
        if directory:
            self.directory_input.setText(directory)

    def _scan_directory(self):
        directory = self.directory_input.text().strip()
        if not directory or not os.path.isdir(directory):
            cmds.warning("Please select a valid directory first.")
            return

        self.scan_result = self.scanner.scan(directory)
        self._populate_table()
        self._populate_materials_to_build()

        materials = self.scan_result["materials"]
        unparsed = self.scan_result["unparsed"]
        conflicts = self.scan_result["conflicts"]
        self._log(
            f"Scanned {directory}: {len(materials)} material(s), "
            f"{len(unparsed)} unparsed file(s), {len(conflicts)} conflict(s)."
        )
        for conflict in conflicts:
            self._log(
                f"Conflict: {conflict['material']} / {conflict['common_attr']} -> "
                f"{conflict['existing']} vs {conflict['new']}"
            )

    def _populate_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

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
                self.table.setItem(row, 3, QtWidgets.QTableWidgetItem("OK"))

        for path in self.scan_result["unparsed"]:
            row = self.table.rowCount()
            self.table.insertRow(row)

            name_item = QtWidgets.QTableWidgetItem("(Unparsed)")
            name_item.setData(QtCore.Qt.UserRole, {"type": "unparsed"})
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem("-"))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(path))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem("UNPARSED"))

            for col in range(4):
                item = self.table.item(row, col)
                if item:
                    item.setBackground(QtGui.QColor("#5a2d2d"))

        self.table.setSortingEnabled(True)

    def _populate_materials_to_build(self):
        self.materials_to_build_list.clear()
        materials = self.scan_result["materials"]
        if not materials:
            self.materials_to_build_label.setText("No materials scanned yet.")
            return

        self.materials_to_build_label.setText(
            f"{len(materials)} material(s) will be created."
        )
        for material in materials:
            channel_count = len(material["channels"])
            self.materials_to_build_list.addItem(
                f"{material['name']} ({channel_count} channels)"
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
            self._log("[ERROR] No scanned materials to build.", error=True)
            return

        target_node_type = self.target_combo.currentData()
        if not target_node_type:
            self._log("[ERROR] Target material type is not selected.", error=True)
            return

        use_full_chain = self.cb_full_chain.isChecked()
        use_qss = self.cb_qss.isChecked()

        if selected_only:
            selected_names = self._selected_material_names()
            materials = [
                m for m in self.scan_result["materials"] if m["name"] in selected_names
            ]
            if not materials:
                self._log("[ERROR] No materials selected in the table.", error=True)
                return
        else:
            materials = self.scan_result["materials"]

        self.progress_bar.setMaximum(len(materials))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        QtWidgets.QApplication.processEvents()

        cmds.undoInfo(openChunk=True)
        try:
            for i, material in enumerate(materials):
                try:
                    new_mat = self.batch_builder.build_material(
                        target_node_type,
                        material,
                        use_full_chain=use_full_chain,
                        use_qss=use_qss,
                    )
                    self._log(f"Built {material['name']} -> {new_mat}")
                except Exception as e:
                    self._log(f"Failed {material['name']}: {e}", error=True)
                self.progress_bar.setValue(i + 1)
                QtWidgets.QApplication.processEvents()
        finally:
            cmds.undoInfo(closeChunk=True)

        self.progress_bar.setVisible(False)
        self._log("--- Batch build finished ---")

    def _log(self, message, error=False):
        if error and "[ERROR]" not in message:
            message = f"[ERROR] {message}"
        self.log_output.appendPlainText(message)
