from ui import QtWidgets, QtCore
import maya.cmds as cmds

from core.config_loader import ConfigLoader
from core.converter import MaterialConverter
from core.logger import get_logger
import core.node_utils as node_utils

_SOURCE = "ConverterTab"


class ConverterTab:

    def __init__(self, logger=None):
        self.log = logger or get_logger()
        self.config = ConfigLoader()
        self.converter_obj = MaterialConverter(logger=self.log)
        self.current_materials = []
        self.selection_display = None
        self.mat_list = None
        self.target_combo = None
        self.progress_bar = None

    def build_ui(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        sel_group = QtWidgets.QGroupBox("Selection Source")
        sel_layout = QtWidgets.QVBoxLayout(sel_group)
        sel_layout.setSpacing(8)
        sel_layout.setContentsMargins(12, 14, 12, 12)

        sel_form = QtWidgets.QFormLayout()
        sel_form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        sel_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        sel_form.setSpacing(8)

        obj_row = QtWidgets.QHBoxLayout()
        obj_row.setSpacing(6)
        self.selection_display = QtWidgets.QLineEdit()
        self.selection_display.setReadOnly(True)
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.setObjectName("refreshBtn")
        refresh_btn.clicked.connect(self.refresh_materials)
        obj_row.addWidget(self.selection_display)
        obj_row.addWidget(refresh_btn)

        sel_form.addRow("Selected Objects:", obj_row)

        self.mat_list = QtWidgets.QListWidget()
        sel_form.addRow("Found Materials:", self.mat_list)

        sel_layout.addLayout(sel_form)
        layout.addWidget(sel_group, stretch=2)

        conv_group = QtWidgets.QGroupBox("Conversion Settings")
        conv_layout = QtWidgets.QVBoxLayout(conv_group)
        conv_layout.setSpacing(10)
        conv_layout.setContentsMargins(12, 14, 12, 12)

        conv_form = QtWidgets.QFormLayout()
        conv_form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        conv_form.setSpacing(8)

        self.target_combo = QtWidgets.QComboBox()
        self.target_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        conv_form.addRow("Target Engine/Shader:", self.target_combo)
        conv_layout.addLayout(conv_form)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        convert_btn = QtWidgets.QPushButton("Convert All Materials")
        convert_btn.setObjectName("convertBtn")
        convert_btn.setMinimumHeight(28)
        convert_btn.clicked.connect(self._run_conversion)
        btn_row.addStretch()
        btn_row.addWidget(convert_btn)
        conv_layout.addLayout(btn_row)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v / %m")
        conv_layout.addWidget(self.progress_bar)

        layout.addWidget(conv_group, stretch=0)
        layout.addStretch(3)

        self._populate_target_list()
        return widget

    def _populate_target_list(self):
        self.target_combo.clear()
        all_configs = self.config.get_all_material_configs()
        for node_type in sorted(all_configs.keys()):
            display_name = self.config.get_display_name(node_type)
            self.target_combo.addItem(display_name, node_type)
        self.log.debug(f"Populated {self.target_combo.count()} conversion target(s)", source=_SOURCE)

    def refresh_materials(self):
        self.mat_list.clear()
        self.current_materials = []

        try:
            selection = cmds.ls(sl=True)
        except Exception as exc:
            self.log.warn(f"Failed to query Maya selection: {exc}", source=_SOURCE)
            selection = []

        if not selection:
            self.selection_display.setText("(Nothing Selected)")
            self.log.warn("No Maya objects currently selected.", source=_SOURCE)
            return

        names = selection[:5]
        display = ", ".join(names)
        if len(selection) > 5:
            display += f" (+{len(selection) - 5} more)"
        self.selection_display.setText(display)

        try:
            materials = node_utils.get_materials_from_selection(logger=self.log)
        except Exception as exc:
            self.log.error(f"Failed to collect materials from selection: {exc}", source=_SOURCE)
            materials = []

        self.current_materials = materials

        if not materials:
            self.log.warn("No PBR shader nodes found on selection.", source=_SOURCE)
            return

        for mat in materials:
            try:
                node_type = node_utils.identify_node_type(mat)
            except Exception as exc:
                self.log.warn(f"Failed to identify material {mat}: {exc}", source=_SOURCE)
                node_type = ""
            display_name = self.config.get_display_name(node_type)
            item_text = f" {mat}   ({display_name})"
            item = QtWidgets.QListWidgetItem(item_text)
            item.setData(256, mat)
            self.mat_list.addItem(item)

        self.log.info(f"Successfully tracked {len(materials)} material(s).", source=_SOURCE)

    def _run_conversion(self):
        if not self.current_materials:
            self.log.error("Execution halted: material queue is empty.", source=_SOURCE)
            return

        target_node_type = self.target_combo.currentData()
        if not target_node_type:
            self.log.error("Execution halted: Target format undefined.", source=_SOURCE)
            return

        target_display = self.config.get_display_name(target_node_type)
        self.log.info(f"--- Converting to {target_display} ---", source=_SOURCE)

        total = len(self.current_materials)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        QtWidgets.QApplication.processEvents()

        results = self.converter_obj.convert_all(self.current_materials, target_node_type)

        converted = 0
        skipped = 0
        failed = 0

        for i, r in enumerate(results):
            if (i + 1) % 5 == 0 or i == total - 1:
                self.progress_bar.setValue(i + 1)
                QtWidgets.QApplication.processEvents()
            if r.get("skipped"):
                skipped += 1
            elif r.get("success"):
                converted += 1
            else:
                failed += 1

        summary = f"DONE: {converted} converted, {skipped} skipped"
        if failed:
            summary += f", {failed} failed"
        self.log.info(f"--- {summary} ---", source=_SOURCE)

        self.progress_bar.setVisible(False)

        new_mats = [r["new_material"] for r in results if r.get("success") and r.get("new_material")]
        if new_mats:
            try:
                cmds.select(new_mats)
            except Exception as exc:
                self.log.warn(f"Failed to select converted materials: {exc}", source=_SOURCE)

        self.refresh_materials()
