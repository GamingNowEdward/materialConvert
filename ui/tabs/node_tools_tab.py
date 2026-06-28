from ui import QtWidgets, QtCore, QtGui, cmds
from core.builder_context import BuilderContext, DEFAULT_MATERIALS


class NodeToolsTab:

    def __init__(self, ctx: BuilderContext):
        self.ctx = ctx

    def build_ui(self):
        widget = QtWidgets.QWidget()
        widget.setObjectName("nodeToolsTab")

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setObjectName("toolScrollArea")

        container = QtWidgets.QWidget()
        container.setObjectName("toolContainer")
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        grp_select = QtWidgets.QGroupBox("Select Nodes")
        grp_layout = QtWidgets.QVBoxLayout(grp_select)
        grp_layout.setSpacing(8)
        grp_layout.setContentsMargins(15, 20, 15, 15)

        select_buttons = [
            ("Select All Materials (Exclude Default)", self._select_all_materials),
            ("Select All File Nodes", self._select_all_file_nodes),
            ("Select All Bump / Normal Nodes", self._select_all_bump_nodes),
            ("Select All LayeredTexture", self._select_all_layer_textures),
            ("Select All Color Correction Nodes", self._select_all_color_corrections),
        ]
        for label, handler in select_buttons:
            btn = QtWidgets.QPushButton(label)
            btn.setFixedHeight(35)
            btn.clicked.connect(handler)
            grp_layout.addWidget(btn)

        layout.addWidget(grp_select)

        grp_cs = QtWidgets.QGroupBox("Set File Color Space")
        cs_layout = QtWidgets.QVBoxLayout(grp_cs)
        cs_layout.setSpacing(10)
        cs_layout.setContentsMargins(15, 20, 15, 15)

        cs_row = QtWidgets.QHBoxLayout()
        cs_label = QtWidgets.QLabel("Target Color Space:")
        cs_label.setFixedWidth(120)
        self.input_color_space = QtWidgets.QLineEdit()
        self.input_color_space.setPlaceholderText("e.g. sRGB - Texture, Raw, ACEScg...")
        cs_row.addWidget(cs_label)
        cs_row.addWidget(self.input_color_space, 1)
        cs_layout.addLayout(cs_row)

        btn_apply_cs = QtWidgets.QPushButton("Apply to Selected File Nodes")
        btn_apply_cs.setFixedHeight(35)
        btn_apply_cs.setObjectName("applyCsBtn")
        btn_apply_cs.clicked.connect(self._apply_color_space)
        cs_layout.addWidget(btn_apply_cs)

        layout.addWidget(grp_cs)

        grp_cm = QtWidgets.QGroupBox("Color Management")
        cm_layout = QtWidgets.QVBoxLayout(grp_cm)
        cm_layout.setSpacing(8)
        cm_layout.setContentsMargins(15, 20, 15, 15)

        btn_ignore_cs = QtWidgets.QPushButton("Select File ignoreColorFileRules")
        btn_ignore_cs.setFixedHeight(35)
        btn_ignore_cs.clicked.connect(self._ignore_color_space_rules)
        cm_layout.addWidget(btn_ignore_cs)

        layout.addWidget(grp_cm)

        grp_sg = QtWidgets.QGroupBox("Shader Group Operations")
        sg_layout = QtWidgets.QVBoxLayout(grp_sg)
        sg_layout.setSpacing(8)
        sg_layout.setContentsMargins(15, 20, 15, 15)

        sg_buttons = [
            ("Rename Selected SG", self._rename_selected_sg),
            ("Rename All SG (Exclude Default)", self._rename_all_sg),
        ]
        for label, handler in sg_buttons:
            btn = QtWidgets.QPushButton(label)
            btn.setFixedHeight(35)
            btn.clicked.connect(handler)
            sg_layout.addWidget(btn)

        layout.addWidget(grp_sg)
        layout.addStretch()

        scroll.setWidget(container)
        tab_layout = QtWidgets.QVBoxLayout(widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

        return widget

    def _select_all_materials(self):
        material_types = cmds.listNodeTypes('shader') or []
        all_materials = []
        for mat_type in material_types:
            materials = cmds.ls(type=mat_type)
            if materials:
                all_materials.extend([m for m in materials if m not in DEFAULT_MATERIALS])
        if all_materials:
            cmds.select(all_materials, replace=True)
            print(f"Selected {len(all_materials)} material node(s).")
        else:
            cmds.select(clear=True)

    def _select_all_file_nodes(self):
        nodes = cmds.ls(type='file')
        if nodes:
            cmds.select(nodes, replace=True)
            print(f"Selected {len(nodes)} file node(s).")
        else:
            cmds.select(clear=True)

    def _select_all_bump_nodes(self):
        bump_types = ["RedshiftBumpMap", "aiNormalMap", "aiBump2d", "bump2d", "bump3d"]
        nodes = []
        for bt in bump_types:
            found = cmds.ls(type=bt)
            if found:
                nodes.extend(found)
        if nodes:
            cmds.select(nodes, replace=True)
            print(f"Selected {len(nodes)} bump/normal node(s).")
        else:
            cmds.select(clear=True)

    def _select_all_layer_textures(self):
        nodes = cmds.ls(type='layeredTexture')
        if nodes:
            cmds.select(nodes, replace=True)
            print(f"Selected {len(nodes)} layeredTexture node(s).")
        else:
            cmds.select(clear=True)

    def _select_all_color_corrections(self):
        cc_types = ["RedshiftColorCorrection", "colorCorrect", "aiColorCorrect", "VRayColorCorrection"]
        nodes = []
        for ct in cc_types:
            found = cmds.ls(type=ct)
            if found:
                nodes.extend(found)
        if nodes:
            cmds.select(nodes, replace=True)
            print(f"Selected {len(nodes)} color correction node(s).")
        else:
            cmds.select(clear=True)

    def _apply_color_space(self):
        target = self.input_color_space.text().strip()
        selected = cmds.ls(selection=True, type="file")
        if not selected:
            cmds.warning("Please select one or more file nodes first.")
            return
        for f in selected:
            try:
                cmds.setAttr(f"{f}.colorSpace", target, type="string")
            except Exception as e:
                cmds.warning(f"Failed: {f}: {e}")

    def _ignore_color_space_rules(self):
        file_nodes = cmds.ls(type='file')
        if not file_nodes:
            cmds.warning("No file nodes found in scene.")
            return
        count = 0
        for f in file_nodes:
            try:
                cmds.setAttr(f"{f}.ignoreColorSpaceFileRules", 1)
                count += 1
            except Exception:
                pass
        cmds.select(file_nodes, replace=True)
        print(f"Set ignoreColorSpaceFileRules=1 on {count}/{len(file_nodes)} file nodes.")

    def _rename_selected_sg(self):
        mats = cmds.ls(selection=True, materials=True)
        if not mats:
            cmds.warning("Please select material nodes first.")
            return
        for m in mats:
            self._rename_sg(m)
        print(f"Processed {len(mats)} material(s) SG rename.")

    def _rename_all_sg(self):
        all_mats = cmds.ls(materials=True)
        mats = [m for m in all_mats if m not in DEFAULT_MATERIALS]
        for m in mats:
            self._rename_sg(m)
        print(f"Processed {len(mats)} material(s) SG rename.")

    def _rename_sg(self, mat):
        connections = cmds.listConnections(mat, type="shadingEngine") or []
        for sg in connections:
            new_name = mat + "SG"
            if cmds.objExists(new_name):
                if sg == new_name:
                    continue
                cmds.warning(f"Name conflict: {new_name} exists, skipping {sg}")
                continue
            try:
                cmds.rename(sg, new_name)
                print(f"{sg} renamed to {new_name}")
            except Exception as e:
                cmds.warning(f"Cannot rename {sg}: {str(e)}")
