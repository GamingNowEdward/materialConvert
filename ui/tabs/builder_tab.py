from ui import QtWidgets
from ui.feedback import qt_maya_logger
from ui.widgets import populate_material_targets
from core.builder_context import BuilderContext
from core.logger import get_logger
from core.material_builder import MaterialBuilder

_SOURCE = "BuilderTab"


class BuilderTab:

    def __init__(self, ctx: BuilderContext, logger=None):
        self.ctx = ctx
        self.log = logger or get_logger()
        self.config = ctx.config
        self.builder = MaterialBuilder(ctx, logger=self.log)

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
        populate_material_targets(
            self.mat_combo, self.config, logger=self.log,
            source=_SOURCE, label="builder material",
        )

    def _browse_file(self, line_edit):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            None, "Select Texture", "",
            "Images (*.png *.jpg *.jpeg *.exr *.tif *.tiff *.tx *.hdr);;All Files (*.*)"
        )
        if file_path:
            line_edit.setText(file_path)
            self.log.debug(f"Selected texture path: {file_path}", source=_SOURCE)

    @qt_maya_logger("Builder")
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

        if 'normal_bump' in input_paths and self.cb_normal_mode is not None:
            mode = 'normal' if self.cb_normal_mode.isChecked() else 'bump'
            channel_options['normal_bump'] = {'mode': mode}

        if self.cb_glossiness is not None and self.cb_glossiness.isChecked():
            channel_options['specularRoughness'] = {'invert': True}

        self.log.debug(
            f"Builder submit: material={node_type}, base={mat_base}, "
            f"channels={sorted(input_paths)}",
            source=_SOURCE,
        )
        return self.builder.build(
            node_type, mat_base, input_paths,
            use_qss=self.cb_qss.isChecked(),
            channel_options=channel_options,
        )