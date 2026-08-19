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

        self.channel_entries = {}

        color_channels = [
            ('baseColor', "Color:", True),
            ('subsurfaceColor', "SSS:", False),
            ('emissionColor', "Emission:", False),
            ('transmissionColor', "Transmission:", False),
            ('specularColor', "Reflection:", False),
            ('fuzzColor', "Sheen:", False),
        ]
        color_group = self._build_channel_group("Color Channels", color_channels)
        layout.addWidget(color_group)

        scalar_channels = [
            ('specularRoughness', "Roughness:", True),
            ('metallic', "Metallic:", False),
            ('opacity', "Opacity:", False),
        ]
        scalar_group, scalar_opts = self._build_channel_group("Scalar Channels", scalar_channels, with_options=True)
        layout.addWidget(scalar_group)

        self.cb_glossiness = scalar_opts.get('glossiness')

        geo_channels = [
            ('normal_bump', "Normal/Bump:", True),
            ('displacementTexture', "Displacement:", False),
        ]
        geo_group, geo_opts = self._build_channel_group("Geometry Channels", geo_channels, with_options=True)
        layout.addWidget(geo_group)

        self.cb_normal_mode = geo_opts.get('normal_mode')

        opt_layout = QtWidgets.QHBoxLayout()
        self.cb_qss = QtWidgets.QCheckBox("Add To Quick Select Set")
        self.cb_qss.setChecked(True)
        opt_layout.addWidget(self.cb_qss)
        opt_layout.addStretch()
        layout.addLayout(opt_layout)

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

    def _build_channel_group(self, title, channels, with_options=False):
        group = QtWidgets.QGroupBox(title)
        grid = QtWidgets.QGridLayout(group)
        grid.setSpacing(6)
        opts = {}

        for row, (common_attr, label_text, default_checked) in enumerate(channels):
            cb = QtWidgets.QCheckBox(label_text)
            cb.setChecked(default_checked)
            cb.setFixedWidth(120)
            le = QtWidgets.QLineEdit()
            le.setPlaceholderText("Leave empty to create unassigned node...")
            btn = QtWidgets.QPushButton("...")
            btn.setFixedSize(30, 25)
            btn.clicked.connect(lambda checked=False, le=le: self._browse_file(le))
            grid.addWidget(cb, row, 0)
            grid.addWidget(le, row, 1)
            grid.addWidget(btn, row, 2)
            self.channel_entries[common_attr] = {'cb': cb, 'le': le}

            if with_options and common_attr == 'specularRoughness':
                cb_gloss = QtWidgets.QCheckBox("Glossiness (Invert)")
                grid.addWidget(cb_gloss, row, 3)
                opts['glossiness'] = cb_gloss

            if with_options and common_attr == 'normal_bump':
                cb_nrm = QtWidgets.QCheckBox("Normal (Uncheck for Bump)")
                cb_nrm.setChecked(True)
                grid.addWidget(cb_nrm, row, 3)
                opts['normal_mode'] = cb_nrm

        return (group, opts) if with_options else group

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

        input_paths = {}
        channel_options = {}

        for common_attr, entry in self.channel_entries.items():
            if entry['cb'].isChecked():
                path = self.ctx.clean_path(entry['le'].text())
                input_paths[common_attr] = path

        use_nrm = True
        if 'normal_bump' in input_paths and self.cb_normal_mode is not None:
            mode = 'normal' if self.cb_normal_mode.isChecked() else 'bump'
            channel_options['normal_bump'] = {'mode': mode}
            use_nrm = mode == 'normal'

        if self.cb_glossiness is not None and self.cb_glossiness.isChecked():
            channel_options['specularRoughness'] = {'invert': True}

        use_sss = 'subsurfaceColor' in input_paths
        use_disp = 'displacementTexture' in input_paths

        return self.builder.build(node_type, mat_base, input_paths, use_nrm, use_sss, use_disp,
                                  use_qss=self.cb_qss.isChecked(),
                                  channel_options=channel_options)

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
