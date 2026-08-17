from ui import QtWidgets, QtCore, QtGui
from core.builder_context import qt_maya_logger, BuilderContext
from core.material_builder import MaterialBuilder
from core.config_loader import ConfigLoader


class BuilderTab:

    def __init__(self, ctx: BuilderContext):
        self.ctx = ctx
        self.config = ConfigLoader()
        self.builder = MaterialBuilder(ctx)

    def build_ui(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        self.name_input = QtWidgets.QLineEdit(self.ctx.get_naming()["default_name"])
        layout.addWidget(self.name_input)

        tex_group = QtWidgets.QGroupBox("Texture Paths (Optional)")
        tex_layout = QtWidgets.QGridLayout(tex_group)
        tex_layout.setSpacing(8)

        self.path_inputs = {}
        texture_types = [
            ('color', "Color:"), ('rough', "Roughness:"),
            ('nrm', "Normal/Bump:"), ('disp', "Displacement:")
        ]

        for row, (key, label_text) in enumerate(texture_types):
            lbl = QtWidgets.QLabel(label_text)
            lbl.setFixedWidth(85)
            le = QtWidgets.QLineEdit()
            le.setPlaceholderText("Leave empty to keep unassigned...")
            btn = QtWidgets.QPushButton("...")
            btn.setFixedSize(30, 25)
            btn.clicked.connect(lambda checked=False, le=le: self._browse_file(le))
            tex_layout.addWidget(lbl, row, 0)
            tex_layout.addWidget(le, row, 1)
            tex_layout.addWidget(btn, row, 2)
            self.path_inputs[key] = le

        layout.addWidget(tex_group)

        cb_layout = QtWidgets.QHBoxLayout()
        self.cb_nrm = QtWidgets.QCheckBox("Normal (Uncheck for Bump)")
        self.cb_nrm.setChecked(True)
        self.cb_sss = QtWidgets.QCheckBox("SSS")
        self.cb_disp = QtWidgets.QCheckBox("Displacement")
        self.cb_qss = QtWidgets.QCheckBox("Add To Quick Select Set")
        self.cb_qss.setChecked(True)
        for cb in [self.cb_nrm, self.cb_sss, self.cb_disp, self.cb_qss]:
            cb_layout.addWidget(cb)
        layout.addLayout(cb_layout)

        self.mat_combo = QtWidgets.QComboBox()
        self.mat_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        layout.addWidget(self.mat_combo)

        btn_build = QtWidgets.QPushButton("BUILD")
        btn_build.setObjectName("convertBtn")
        btn_build.setFixedHeight(52)
        btn_build.clicked.connect(self._create_material_logic)
        layout.addWidget(btn_build)

        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet("background-color: #333;")
        layout.addWidget(line)

        btn_create_file = QtWidgets.QPushButton("Create File From P2D")
        btn_create_file.setFixedHeight(35)
        btn_create_file.setObjectName("createFileBtn")
        btn_create_file.clicked.connect(self._create_file_from_p2d)
        layout.addWidget(btn_create_file)

        self._populate_material_list()
        return widget

    def _populate_material_list(self):
        self.mat_combo.clear()
        all_configs = self.config.get_all_material_configs()
        for node_type in sorted(all_configs.keys()):
            display_name = self.config.get_display_name(node_type)
            self.mat_combo.addItem(display_name, node_type)

    def _browse_file(self, line_edit):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            None, "Select Texture", "",
            "Images (*.png *.jpg *.jpeg *.exr *.tif *.tiff *.tx *.hdr);;All Files (*.*)"
        )
        if file_path:
            line_edit.setText(file_path)

    @qt_maya_logger
    def _create_material_logic(self):
        node_type = self.mat_combo.currentData()
        if not node_type:
            raise RuntimeError("No material type selected.")
        mat_base = self.name_input.text() or "Default"
        use_nrm = self.cb_nrm.isChecked()
        use_sss = self.cb_sss.isChecked()
        use_disp = self.cb_disp.isChecked()

        input_paths = {
            'color': self.ctx.clean_path(self.path_inputs['color'].text()),
            'rough': self.ctx.clean_path(self.path_inputs['rough'].text()),
            'nrm': self.ctx.clean_path(self.path_inputs['nrm'].text()),
            'bump': self.ctx.clean_path(self.path_inputs['nrm'].text()),
            'disp': self.ctx.clean_path(self.path_inputs['disp'].text())
        }

        return self.builder.build(node_type, mat_base, input_paths, use_nrm, use_sss, use_disp,
                                  use_qss=self.cb_qss.isChecked())

    @qt_maya_logger
    def _create_file_from_p2d(self):
        import maya.cmds as cmds
        sel = cmds.ls(selection=True)
        if not sel or cmds.nodeType(sel[0]) != "place2dTexture":
            raise RuntimeError("Please select a place2dTexture node first.")
        p2d = sel[0]
        f_node = cmds.shadingNode('file', asTexture=True, isColorManaged=True)
        for attr in MaterialBuilder.P2D_ATTRS:
            self.ctx.connect(p2d, attr, f_node, attr)
        self.ctx.connect(p2d, "outUV", f_node, "uvCoord")
        self.ctx.connect(p2d, "outUvFilterSize", f_node, "uvFilterSize")
        cmds.select(f_node)
        return "File creation from P2D"
