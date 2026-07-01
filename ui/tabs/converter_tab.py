from ui import QtWidgets, QtCore, QtGui
import pymel.core as pm

from core.config_loader import ConfigLoader
from core.converter import MaterialConverter
from core.logger import Logger
import core.node_utils as node_utils


class ConverterTab:

    def __init__(self):
        self.config = ConfigLoader()
        self.logger = Logger()
        self.converter_obj = MaterialConverter(logger=self.logger)
        self.current_materials = []
        self.selection_display = None
        self.mat_list = None
        self.target_combo = None
        self.log_output = None

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

        log_group = QtWidgets.QGroupBox("Process Log")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        log_layout.setContentsMargins(12, 14, 12, 12)

        self.log_output = QtWidgets.QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setObjectName("logOutput")

        layout.addWidget(log_group, stretch=3)
        log_layout.addWidget(self.log_output)

        self.logger.set_callback(self._add_log)

        self._populate_target_list()
        return widget

    def _populate_target_list(self):
        self.target_combo.clear()
        all_configs = self.config.get_all_material_configs()
        for node_type in sorted(all_configs.keys()):
            display_name = self.config.get_display_name(node_type)
            self.target_combo.addItem(display_name, node_type)

    def refresh_materials(self):
        self.mat_list.clear()
        self.current_materials = []

        selection = pm.ls(sl=True)
        if not selection:
            self.selection_display.setText("(Nothing Selected)")
            self._add_log("No Maya objects currently selected.")
            return

        names = [obj.name() for obj in selection[:5]]
        display = ", ".join(names)
        if len(selection) > 5:
            display += f" (+{len(selection) - 5} more)"
        self.selection_display.setText(display)

        materials = node_utils.get_materials_from_selection()
        self.current_materials = materials

        if not materials:
            self._add_log("No PBR shader nodes found on selection.")
            return

        for mat in materials:
            node_type = node_utils.identify_node_type(mat)
            display_name = self.config.get_display_name(node_type)
            item_text = f" {mat.name()}   ({display_name})"
            item = QtWidgets.QListWidgetItem(item_text)
            item.setData(256, mat)
            self.mat_list.addItem(item)

        self._add_log(f"Successfully tracked {len(materials)} material(s).")

    def _run_conversion(self):
        if not self.current_materials:
            self._add_log("[ERROR] Execution halted: material queue is empty.", error=True)
            return

        target_node_type = self.target_combo.currentData()
        if not target_node_type:
            self._add_log("[ERROR] Execution halted: Target format undefined.", error=True)
            return

        target_display = self.config.get_display_name(target_node_type)
        self._add_log(f"--- Converting to {target_display} ---")

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
        self._add_log(f"--- {summary} ---")

        self.progress_bar.setVisible(False)

        new_mats = [r["new_material"] for r in results if r.get("success") and r.get("new_material")]
        if new_mats:
            pm.select(new_mats)

        self.refresh_materials()

    def _add_log(self, message, error=False):
        if error and "[ERROR]" not in message:
            message = f"[ERROR] {message}"

        cursor = self.log_output.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)

        fmt = QtGui.QTextCharFormat()
        if "[ERROR]" in message:
            fmt.setForeground(QtGui.QColor("#E06C75"))
        elif message.startswith("DONE"):
            fmt.setForeground(QtGui.QColor("#98C379"))
            fmt.setFontWeight(QtGui.QFont.Weight.Bold)
        elif message.startswith("---"):
            fmt.setForeground(QtGui.QColor("#61AFEF"))
            fmt.setFontWeight(QtGui.QFont.Weight.Bold)
        else:
            fmt.setForeground(QtGui.QColor("#ABB2BF"))

        cursor.insertText(message + "\n", fmt)
        self.log_output.setTextCursor(cursor)
        self.log_output.ensureCursorVisible()
