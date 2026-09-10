import os

from ui import QtWidgets, QtCore, QtGui
from ui.widgets import populate_material_targets
from core.builder_context import BuilderContext
from core.logger import get_logger
from core.texture_scanner import TextureScanner
from core.batch_builder import BatchBuilder

_SOURCE = "BatchBuilderTab"


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
        self.target_combo = None
        self.cb_full_chain = None
        self.cb_qss = None
        self.table = None
        self.materials_to_build_list = None
        self.materials_to_build_label = None
        self.progress_bar = None

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

        dir_layout.addWidget(self.directory_input, 1)
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

        self.cb_full_chain = QtWidgets.QCheckBox("Use Full Builder Pipeline (CC/Layered)")
        self.cb_full_chain.setChecked(True)
        opt_layout.addWidget(self.cb_full_chain)

        self.cb_qss = QtWidgets.QCheckBox("Add To Quick Select Set")
        self.cb_qss.setChecked(True)
        opt_layout.addWidget(self.cb_qss)

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

        self.scan_result = self.scanner.scan(directory)
        self._populate_table()
        self._populate_materials_to_build()

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

        total = len(materials)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        QtWidgets.QApplication.processEvents()

        def _on_progress(done, total_count, result):
            # Throttle repaints: roughly every 5 materials and always the last one.
            if done == total_count or done % 5 == 0:
                self.progress_bar.setValue(done)
                QtWidgets.QApplication.processEvents()

        self.batch_builder.build_all(
            materials,
            target_node_type,
            use_full_chain=use_full_chain,
            use_qss=use_qss,
            on_progress=_on_progress,
        )

        self.progress_bar.setValue(total)
        self.progress_bar.setVisible(False)
