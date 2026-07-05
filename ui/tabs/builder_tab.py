from ui import QtWidgets, QtCore, QtGui
from core.builder_context import qt_maya_logger, BuilderContext
from core.config_loader import ConfigLoader


class BuilderTab:

    P2D_ATTRS = ['coverage', 'translateFrame', 'rotateFrame', 'mirrorU', 'mirrorV',
                 'stagger', 'wrapU', 'wrapV', 'repeatUV', 'offset', 'rotateUV', 'noiseUV']

    def __init__(self, ctx: BuilderContext):
        self.ctx = ctx
        self.config = ConfigLoader()

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
        for cb in [self.cb_nrm, self.cb_sss, self.cb_disp]:
            cb_layout.addWidget(cb)
        layout.addLayout(cb_layout)

        btn_layout = QtWidgets.QHBoxLayout()
        renderer_styles = {
            'arnold': None,
            'redshift': 'rsBtn',
            'vray': 'vrayBtn',
        }
        for renderer in ['arnold', 'redshift', 'vray']:
            spec = self.config.get_builder_spec(renderer)
            if not spec:
                continue
            display_name = renderer.upper()
            btn = QtWidgets.QPushButton(f"BUILD {display_name}")
            btn.setFixedHeight(45)
            style = renderer_styles.get(renderer)
            if style:
                btn.setObjectName(style)
            btn.clicked.connect(lambda checked=False, r=renderer: self._create_material_logic(r))
            btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)

        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet("background-color: #333;")
        layout.addWidget(line)

        btn_create_file = QtWidgets.QPushButton("Create File From P2D")
        btn_create_file.setFixedHeight(35)
        btn_create_file.setObjectName("createFileBtn")
        btn_create_file.clicked.connect(self._create_file_from_p2d)
        layout.addWidget(btn_create_file)

        return widget

    def _browse_file(self, line_edit):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            None, "Select Texture", "",
            "Images (*.png *.jpg *.jpeg *.exr *.tif *.tiff *.tx *.hdr);;All Files (*.*)"
        )
        if file_path:
            line_edit.setText(file_path)

    @qt_maya_logger
    def _create_material_logic(self, renderer):
        import maya.cmds as cmds
        self.ctx._current_build_nodes = []
        spec = self.ctx.get_builder_spec(renderer)
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

        if not cmds.pluginInfo(spec['plugin'], q=True, l=True):
            cmds.loadPlugin(spec['plugin'])

        m_node = self.ctx.create_node(spec['shader_type'], 'material', mat_base, as_type='shader')
        sg_node = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=f"{m_node}SG")
        self.ctx._current_build_nodes.append(sg_node)

        self.ctx.connect(m_node, "outColor", sg_node, "surfaceShader")
        p2d = self.ctx.create_node('place2dTexture', 'p2d', mat_base)

        if 'mat_init_attrs' in spec:
            for attr, val in spec['mat_init_attrs'].items():
                if cmds.attributeQuery(attr, node=m_node, exists=True):
                    cmds.setAttr(f"{m_node}.{attr}", val)

        def make_tex(key, is_alpha=False):
            f = self.ctx.create_node('file', 'file', mat_base, key, 'texture')
            if is_alpha:
                cmds.setAttr(f"{f}.alphaIsLuminance", 1)
            target_path = input_paths.get(key, "")
            if target_path:
                cmds.setAttr(f"{f}.fileTextureName", target_path, type="string")
            for attr in self.P2D_ATTRS:
                self.ctx.connect(p2d, attr, f, attr)
            self.ctx.connect(p2d, "outUV", f, "uvCoord")
            self.ctx.connect(p2d, "outUvFilterSize", f, "uvFilterSize")
            return f

        tex_color = make_tex('color')
        for ch in (['color', 'sss'] if use_sss else ['color']):
            cc = self.ctx.create_node(spec['cc_type'], 'cc', mat_base, ch)
            lyr = self.ctx.build_layered_node(mat_base, ch)
            self.ctx.connect(tex_color, "outColor", cc, spec['cc_in'])
            self.ctx.connect(cc, spec.get('cc_out', 'outColor'), lyr, "inputs[1].color")
            self.ctx.connect(lyr, "outColor", m_node, spec['attr_map'][ch])
            if ch == 'sss' and renderer == 'vray':
                if cmds.attributeQuery('ssOn', node=m_node, exists=True):
                    cmds.setAttr(f"{m_node}.ssOn", 1)

        tex_rough = make_tex('rough', True)
        ramp = self.ctx.create_node('ramp', 'ramp', mat_base, 'rough', 'texture')
        self.ctx.connect(tex_rough, "outAlpha", ramp, "vCoord")
        self.ctx.connect(ramp, "outAlpha", m_node, spec['attr_map']['rough'])

        nb_key = 'nrm' if use_nrm else 'bump'
        nb_spec = spec['nb']
        tex_nb = make_tex(nb_key, not use_nrm)
        middle_node_type = nb_spec['node'].get(nb_key)

        if middle_node_type:
            nb_node = self.ctx.create_node(middle_node_type, nb_key, mat_base)
            mode_attrs = nb_spec['init_attrs'].get(nb_key, {})
            for attr, val in mode_attrs.items():
                cmds.setAttr(f"{nb_node}.{attr}", val)
            self.ctx.connect(tex_nb, nb_spec['file_src'][nb_key], nb_node, nb_spec['in'][nb_key])
            self.ctx.connect(nb_node, nb_spec['out'][nb_key], m_node, spec['attr_map']['nrm'])
        else:
            self.ctx.connect(tex_nb, nb_spec['file_src'][nb_key], m_node, spec['attr_map']['nrm'])
            if 'mat_attrs' in nb_spec and nb_key in nb_spec['mat_attrs']:
                for attr, val in nb_spec['mat_attrs'][nb_key].items():
                    if cmds.attributeQuery(attr, node=m_node, exists=True):
                        cmds.setAttr(f"{m_node}.{attr}", val)

        if use_disp:
            d_spec = spec['disp']
            tex_disp = make_tex('disp', True)
            lyr_disp = self.ctx.build_layered_node(mat_base, 'disp', layers=2)
            for rgb in 'RGB':
                self.ctx.connect(tex_disp, d_spec['file_src'], lyr_disp, f"inputs[1].color{rgb}")
            d_node = self.ctx.create_node(d_spec['node'], 'disp', mat_base, as_type='shader')
            self.ctx.connect(lyr_disp, d_spec['lyr_src'], d_node, d_spec['in'])
            self.ctx.connect(d_node, d_spec['out'], sg_node, "displacementShader")

        qss_nodes = [n for n in self.ctx._current_build_nodes if cmds.nodeType(n) != 'file']
        if qss_nodes:
            cmds.sets(qss_nodes, name=f"{self.ctx.get_naming()['qss_prefix']}{mat_base}")

        cmds.select(m_node)

    @qt_maya_logger
    def _create_file_from_p2d(self):
        import maya.cmds as cmds
        sel = cmds.ls(selection=True)
        if not sel or cmds.nodeType(sel[0]) != "place2dTexture":
            raise RuntimeError("Please select a place2dTexture node first.")
        p2d = sel[0]
        f_node = cmds.shadingNode('file', asTexture=True, isColorManaged=True)
        for attr in self.P2D_ATTRS:
            self.ctx.connect(p2d, attr, f_node, attr)
        self.ctx.connect(p2d, "outUV", f_node, "uvCoord")
        self.ctx.connect(p2d, "outUvFilterSize", f_node, "uvFilterSize")
        cmds.select(f_node)
        return "File creation from P2D"
