from ui import QtWidgets, QtCore, QtGui, cmds


class LocatorTab:

    def __init__(self, ctx):
        self.ctx = ctx
        self._current_color = QtGui.QColor(64, 117, 128)

    def build_ui(self):
        widget = QtWidgets.QWidget()
        widget.setObjectName("locatorTab")

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setObjectName("toolScrollArea")

        container = QtWidgets.QWidget()
        container.setObjectName("toolContainer")
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        grp_prefix = QtWidgets.QGroupBox("Prefix")
        prefix_layout = QtWidgets.QVBoxLayout(grp_prefix)
        prefix_layout.setContentsMargins(15, 20, 15, 15)
        self.prefix_edit = QtWidgets.QLineEdit("loc_")
        prefix_layout.addWidget(self.prefix_edit)
        layout.addWidget(grp_prefix)

        grp_scale = QtWidgets.QGroupBox("Locator Scale Multipliers")
        scale_layout = QtWidgets.QHBoxLayout(grp_scale)
        scale_layout.setContentsMargins(15, 20, 15, 15)
        scale_layout.setSpacing(8)
        self.scale_x_sb = QtWidgets.QDoubleSpinBox()
        self.scale_x_sb.setRange(0.001, 9999.0)
        self.scale_x_sb.setValue(1.0)
        self.scale_x_sb.setDecimals(3)
        self.scale_y_sb = QtWidgets.QDoubleSpinBox()
        self.scale_y_sb.setRange(0.001, 9999.0)
        self.scale_y_sb.setValue(1.0)
        self.scale_y_sb.setDecimals(3)
        self.scale_z_sb = QtWidgets.QDoubleSpinBox()
        self.scale_z_sb.setRange(0.001, 9999.0)
        self.scale_z_sb.setValue(1.0)
        self.scale_z_sb.setDecimals(3)
        scale_layout.addWidget(self.scale_x_sb)
        scale_layout.addWidget(self.scale_y_sb)
        scale_layout.addWidget(self.scale_z_sb)
        layout.addWidget(grp_scale)

        grp_color = QtWidgets.QGroupBox("Color Override")
        color_layout = QtWidgets.QVBoxLayout(grp_color)
        color_layout.setContentsMargins(15, 20, 15, 15)
        color_layout.setSpacing(8)

        self.color_cb = QtWidgets.QCheckBox("Enable Override Color")
        color_layout.addWidget(self.color_cb)

        color_row = QtWidgets.QHBoxLayout()
        color_row.addWidget(QtWidgets.QLabel("Color:"))
        self.color_btn = QtWidgets.QPushButton()
        self.color_btn.setFixedSize(60, 28)
        self._update_color_btn()
        self.color_btn.clicked.connect(self._pick_color)
        color_row.addWidget(self.color_btn)
        color_row.addStretch()
        color_layout.addLayout(color_row)

        layout.addWidget(grp_color)

        layout.addStretch()

        btn_exec = QtWidgets.QPushButton("Create Layout Locator")
        btn_exec.setObjectName("execModifyBtn")
        btn_exec.setFixedHeight(42)
        btn_exec.clicked.connect(self._execute)
        layout.addWidget(btn_exec)

        scroll.setWidget(container)
        tab_layout = QtWidgets.QVBoxLayout(widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

        return widget

    def _update_color_btn(self):
        r, g, b = self._current_color.red(), self._current_color.green(), self._current_color.blue()
        self.color_btn.setStyleSheet(
            "background-color: rgb({}, {}, {}); border: 1px solid #555; border-radius: 4px;".format(r, g, b)
        )

    def _pick_color(self):
        cmds.colorEditor(rgbValue=(
            self._current_color.redF(),
            self._current_color.greenF(),
            self._current_color.blueF()
        ))

        if cmds.colorEditor(query=True, result=True):
            r, g, b = cmds.colorEditor(query=True, rgb=True)
            self._current_color = QtGui.QColor.fromRgbF(r, g, b)
            self._update_color_btn()

    def _execute(self):
        selection = cmds.ls(sl=True, long=True, type="transform")

        if not selection:
            cmds.warning("请选择至少一个 Transform。")
            return

        prefix = self.prefix_edit.text()
        scale_x = self.scale_x_sb.value()
        scale_y = self.scale_y_sb.value()
        scale_z = self.scale_z_sb.value()
        color_enable = self.color_cb.isChecked()
        color_r = self._current_color.redF()
        color_g = self._current_color.greenF()
        color_b = self._current_color.blueF()

        cmds.undoInfo(openChunk=True)

        try:
            for obj in selection:
                shapes = cmds.listRelatives(obj, s=True, f=True) or []
                if shapes and cmds.nodeType(shapes[0]) == "locator":
                    continue

                short_name = obj.split("|")[-1]
                parent = cmds.listRelatives(obj, p=True, f=True)
                world_matrix = cmds.xform(obj, q=True, ws=True, matrix=True)
                bbox = cmds.exactWorldBoundingBox(obj)

                size_x = bbox[3] - bbox[0]
                size_y = bbox[4] - bbox[1]
                size_z = bbox[5] - bbox[2]
                size = max(size_x, size_y, size_z, 0.001)

                locator = cmds.spaceLocator(name=prefix + short_name)[0]

                if parent:
                    locator = cmds.parent(locator, parent[0])[0]

                cmds.xform(locator, ws=True, matrix=world_matrix)

                obj = cmds.parent(obj, locator)[0]

                cmds.setAttr(obj + ".translateX", 0)
                cmds.setAttr(obj + ".translateY", 0)
                cmds.setAttr(obj + ".translateZ", 0)
                cmds.setAttr(obj + ".rotateX", 0)
                cmds.setAttr(obj + ".rotateY", 0)
                cmds.setAttr(obj + ".rotateZ", 0)
                cmds.setAttr(obj + ".scaleX", 1)
                cmds.setAttr(obj + ".scaleY", 1)
                cmds.setAttr(obj + ".scaleZ", 1)

                locator_shape = cmds.listRelatives(locator, s=True, f=True)[0]

                cmds.setAttr(locator_shape + ".localScaleX", size * scale_x)
                cmds.setAttr(locator_shape + ".localScaleY", size * scale_y)
                cmds.setAttr(locator_shape + ".localScaleZ", size * scale_z)

                if color_enable:
                    cmds.setAttr(locator_shape + ".overrideEnabled", 1)
                    cmds.setAttr(locator_shape + ".overrideRGBColors", 1)
                    cmds.setAttr(locator_shape + ".overrideColorR", color_r)
                    cmds.setAttr(locator_shape + ".overrideColorG", color_g)
                    cmds.setAttr(locator_shape + ".overrideColorB", color_b)

        finally:
            cmds.undoInfo(closeChunk=True)
