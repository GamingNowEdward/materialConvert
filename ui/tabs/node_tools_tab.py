from ui import QtWidgets, cmds
from core.builder_context import BuilderContext, DEFAULT_MATERIALS
from core.config_loader import ConfigLoader
from core.logger import get_logger

_SOURCE = "NodeToolsTab"


class NodeToolsTab:

    def __init__(self, ctx: BuilderContext, logger=None):
        self.ctx = ctx
        self.log = logger or get_logger()
        self.config = ConfigLoader()

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
        try:
            material_types = cmds.listNodeTypes('shader') or []
        except Exception as exc:
            self.log.error(f"Failed to list shader node types: {exc}", source=_SOURCE)
            return
        all_materials = []
        for mat_type in material_types:
            try:
                materials = cmds.ls(type=mat_type) or []
            except Exception as exc:
                self.log.warn(f"Failed to list nodes of type {mat_type}: {exc}", source=_SOURCE)
                continue
            if materials:
                all_materials.extend([m for m in materials if m not in DEFAULT_MATERIALS])
        if all_materials:
            cmds.select(all_materials, replace=True)
            self.log.info(f"Selected {len(all_materials)} material node(s).", source=_SOURCE)
        else:
            cmds.select(clear=True)
            self.log.warn("No material nodes found to select.", source=_SOURCE)

    def _select_all_file_nodes(self):
        try:
            nodes = cmds.ls(type='file') or []
        except Exception as exc:
            self.log.error(f"Failed to list file nodes: {exc}", source=_SOURCE)
            return
        if nodes:
            cmds.select(nodes, replace=True)
            self.log.info(f"Selected {len(nodes)} file node(s).", source=_SOURCE)
        else:
            cmds.select(clear=True)
            self.log.warn("No file nodes found to select.", source=_SOURCE)

    def _select_all_bump_nodes(self):
        bn_types = self.config.get_all_bn_types()
        nodes = []
        for bt in bn_types:
            try:
                found = cmds.ls(type=bt) or []
            except Exception as exc:
                self.log.warn(f"Failed to list bump/normal nodes of type {bt}: {exc}", source=_SOURCE)
                continue
            if found:
                nodes.extend(found)
        if nodes:
            cmds.select(nodes, replace=True)
            self.log.info(f"Selected {len(nodes)} bump/normal node(s).", source=_SOURCE)
        else:
            cmds.select(clear=True)
            self.log.warn("No bump/normal nodes found to select.", source=_SOURCE)

    def _select_all_layer_textures(self):
        try:
            nodes = cmds.ls(type='layeredTexture') or []
        except Exception as exc:
            self.log.error(f"Failed to list layeredTexture nodes: {exc}", source=_SOURCE)
            return
        if nodes:
            cmds.select(nodes, replace=True)
            self.log.info(f"Selected {len(nodes)} layeredTexture node(s).", source=_SOURCE)
        else:
            cmds.select(clear=True)
            self.log.warn("No layeredTexture nodes found to select.", source=_SOURCE)

    def _select_all_color_corrections(self):
        cc_types = self.config.get_all_cc_types()
        nodes = []
        for ct in cc_types:
            try:
                found = cmds.ls(type=ct) or []
            except Exception as exc:
                self.log.warn(f"Failed to list CC nodes of type {ct}: {exc}", source=_SOURCE)
                continue
            if found:
                nodes.extend(found)
        if nodes:
            cmds.select(nodes, replace=True)
            self.log.info(f"Selected {len(nodes)} color correction node(s).", source=_SOURCE)
        else:
            cmds.select(clear=True)
            self.log.warn("No color correction nodes found to select.", source=_SOURCE)

    def _rename_selected_sg(self):
        mats = cmds.ls(selection=True, materials=True)
        if not mats:
            self.log.warn("Please select material nodes first.", source=_SOURCE)
            return
        for m in mats:
            self._rename_sg(m)
        self.log.info(f"Processed {len(mats)} material(s) SG rename.", source=_SOURCE)

    def _rename_all_sg(self):
        all_mats = cmds.ls(materials=True)
        mats = [m for m in all_mats if m not in DEFAULT_MATERIALS]
        for m in mats:
            self._rename_sg(m)
        self.log.info(f"Processed {len(mats)} material(s) SG rename.", source=_SOURCE)

    def _rename_sg(self, mat):
        connections = cmds.listConnections(mat, type="shadingEngine") or []
        for sg in connections:
            new_name = mat + "SG"
            if cmds.objExists(new_name):
                if sg == new_name:
                    continue
                self.log.warn(f"Name conflict: {new_name} exists, skipping {sg}", source=_SOURCE)
                continue
            try:
                cmds.rename(sg, new_name)
                self.log.info(f"{sg} renamed to {new_name}", source=_SOURCE)
            except Exception as exc:
                self.log.warn(f"Cannot rename {sg}: {exc}", source=_SOURCE)