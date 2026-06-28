from core.builder_context import BuilderContext

try:
    from PySide2 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide6 import QtWidgets, QtCore, QtGui
import maya.cmds as cmds


class AttrModifierTab:

    def __init__(self, ctx: BuilderContext):
        self.ctx = ctx

    def build_ui(self):
        widget = QtWidgets.QWidget()
        widget.setObjectName("batchAttrTab")

        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        attr_row = QtWidgets.QHBoxLayout()
        attr_label = QtWidgets.QLabel("Attr Name:")
        attr_label.setFixedWidth(80)
        self.attr_input = QtWidgets.QLineEdit()
        self.attr_input.setPlaceholderText("e.g. visibility, primaryVisibility")
        attr_row.addWidget(attr_label)
        attr_row.addWidget(self.attr_input)
        layout.addLayout(attr_row)

        type_row = QtWidgets.QHBoxLayout()
        type_label = QtWidgets.QLabel("Data Type:")
        type_label.setFixedWidth(80)
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(["Boolean", "Float", "Integer", "String"])
        self.type_combo.currentIndexChanged.connect(self._on_attr_type_changed)
        type_row.addWidget(type_label)
        type_row.addWidget(self.type_combo)
        layout.addLayout(type_row)

        value_group = QtWidgets.QGroupBox("Target Value")
        value_layout = QtWidgets.QVBoxLayout(value_group)
        value_layout.setContentsMargins(15, 20, 15, 15)

        self.value_stacked = QtWidgets.QStackedWidget()
        self.bool_checkbox = QtWidgets.QCheckBox("True / Enable")
        self.value_stacked.addWidget(self.bool_checkbox)
        self.float_spin = QtWidgets.QDoubleSpinBox()
        self.float_spin.setRange(-999999.0, 999999.0)
        self.float_spin.setDecimals(4)
        self.float_spin.setValue(0.0)
        self.value_stacked.addWidget(self.float_spin)
        self.int_spin = QtWidgets.QSpinBox()
        self.int_spin.setRange(-999999, 999999)
        self.int_spin.setValue(0)
        self.value_stacked.addWidget(self.int_spin)
        self.string_input = QtWidgets.QLineEdit()
        self.string_input.setPlaceholderText("Enter string value...")
        self.value_stacked.addWidget(self.string_input)

        value_layout.addWidget(self.value_stacked)
        layout.addWidget(value_group)
        layout.addStretch()

        btn_exec = QtWidgets.QPushButton("Execute Modification")
        btn_exec.setObjectName("execModifyBtn")
        btn_exec.setFixedHeight(42)
        btn_exec.clicked.connect(self._batch_modify_attributes)
        layout.addWidget(btn_exec)

        return widget

    def _on_attr_type_changed(self, index):
        self.value_stacked.setCurrentIndex(index)

    def _get_attr_target_value(self, data_type):
        if data_type == "bool":
            return self.bool_checkbox.isChecked()
        elif data_type == "float":
            return self.float_spin.value()
        elif data_type == "int":
            return self.int_spin.value()
        elif data_type == "string":
            return self.string_input.text()
        return None

    def _batch_modify_attributes(self):
        attr_name = self.attr_input.text().strip()
        if not attr_name:
            cmds.warning("Please specify an Attribute Name.")
            return

        selected_nodes = cmds.ls(selection=True)
        if not selected_nodes:
            cmds.warning("No objects selected.")
            return

        type_mapping = ["bool", "float", "int", "string"]
        current_type = type_mapping[self.type_combo.currentIndex()]
        value = self._get_attr_target_value(current_type)
        success_count = 0

        for node in selected_nodes:
            targets = []
            if cmds.attributeQuery(attr_name, node=node, exists=True):
                targets.append(node)
            if cmds.objectType(node) == "transform":
                shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
                for shape in shapes:
                    if cmds.attributeQuery(attr_name, node=shape, exists=True):
                        targets.append(shape)
            if not targets:
                print(f"Skipped '{node}': Attribute '{attr_name}' not found.")
                continue
            for target in targets:
                full_attr_path = f"{target}.{attr_name}"
                try:
                    if current_type == "string":
                        cmds.setAttr(full_attr_path, value, type="string")
                    else:
                        cmds.setAttr(full_attr_path, value)
                    success_count += 1
                except Exception as e:
                    cmds.warning(f"Failed to set '{target}.{attr_name}': {str(e)}")

        print(f"Successfully modified {success_count} attribute(s).")
