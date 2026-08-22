import os
from collections import deque

from ui import QtWidgets, cmds
from core.builder_context import BuilderContext, DEFAULT_MATERIALS
from core.config_loader import ConfigLoader, normalize_keyword
from core.logger import get_logger

_SOURCE = "NodeToolsTab"


class NodeToolsTab:

    def __init__(self, ctx: BuilderContext, logger=None):
        self.ctx = ctx
        self.log = logger or get_logger()
        self.config = ConfigLoader()
        self.cs_config = self.config.get_color_space_config()
        self.expanded_keywords = self.config.get_expanded_attribute_keywords()
        self._filename_role_keywords = self.config.get_filename_role_keywords()
        self._shader_types = None
        self._material_node_cache = {}

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

        btn_auto_cs = QtWidgets.QPushButton("Auto Match Selected")
        btn_auto_cs.setFixedHeight(35)
        btn_auto_cs.setObjectName("autoCsBtn")
        btn_auto_cs.clicked.connect(self._auto_match_color_space)
        cs_layout.addWidget(btn_auto_cs)

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

    def _apply_color_space(self):
        target = self.input_color_space.text().strip()
        selected = cmds.ls(selection=True, type="file")
        if not selected:
            self.log.warn("Please select one or more file nodes first.", source=_SOURCE)
            return
        applied = 0
        for f in selected:
            try:
                cmds.setAttr(f"{f}.colorSpace", target, type="string")
                applied += 1
                self.log.debug(f"Set {f}.colorSpace = {target}", source=_SOURCE)
            except Exception as exc:
                self.log.warn(f"Failed to set color space on {f}: {exc}", source=_SOURCE)
        self.log.info(f"Applied color space '{target}' to {applied}/{len(selected)} file node(s).", source=_SOURCE)

    def _ignore_color_space_rules(self):
        try:
            file_nodes = cmds.ls(type='file') or []
        except Exception as exc:
            self.log.error(f"Failed to list file nodes: {exc}", source=_SOURCE)
            return
        if not file_nodes:
            self.log.warn("No file nodes found in scene.", source=_SOURCE)
            return
        count = 0
        for f in file_nodes:
            try:
                cmds.setAttr(f"{f}.ignoreColorSpaceFileRules", 1)
                count += 1
            except Exception as exc:
                self.log.warn(f"Failed to set ignoreColorSpaceFileRules on {f}: {exc}", source=_SOURCE)
        cmds.select(file_nodes, replace=True)
        self.log.info(f"Set ignoreColorSpaceFileRules=1 on {count}/{len(file_nodes)} file nodes.", source=_SOURCE)

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

    def _get_available_color_spaces(self):
        try:
            result = cmds.colorManagementPrefs(q=True, inputSpaceNames=True)
        except Exception as exc:
            self.log.warn(f"Failed to query available color spaces: {exc}", source=_SOURCE)
            return set()
        if result:
            return set(result)
        return set()

    def _set_color_space(self, file_node, role):
        available = self._get_available_color_spaces()
        cs_data = self.cs_config.get("colorSpaces", {}).get(role, {})
        for cs_name in cs_data.get("aliases", []):
            if cs_name in available:
                try:
                    cmds.setAttr(f"{file_node}.colorSpace", cs_name, type="string")
                    return True
                except Exception as exc:
                    self.log.warn(f"Failed to set color space on {file_node}: {exc}", source=_SOURCE)
                    return False
        return False

    def _match_by_filename(self, file_node):
        try:
            path = cmds.getAttr(f"{file_node}.fileTextureName")
        except Exception as exc:
            self.log.warn(f"Failed to read fileTextureName on {file_node}: {exc}", source=_SOURCE)
            return None
        if not path:
            return None
        filename = os.path.basename(path).lower().replace("_", "").replace("-", "")
        for role, keywords in self._filename_role_keywords.items():
            for kw in keywords:
                if kw in filename:
                    return role
        return None

    def _get_shader_types(self):
        if self._shader_types is None:
            try:
                self._shader_types = set(cmds.listNodeTypes("shader") or [])
            except Exception as exc:
                self.log.warn(f"Failed to list shader node types: {exc}", source=_SOURCE)
                self._shader_types = set()
        return self._shader_types

    def _is_material_node(self, node):
        """Return True when *node* is a shader node type.

        Uses ``listNodeTypes("shader")`` instead of probing ``node.outColor``.
        Probing ``.outColor`` is both expensive and invalid for utility nodes
        such as place2dTexture, which produced warning floods and slowed large
        Auto Match operations to a crawl.
        """
        cached = self._material_node_cache.get(node)
        if cached is not None:
            return cached

        try:
            result = cmds.nodeType(node) in self._get_shader_types()
        except Exception as exc:
            self.log.warn(f"Failed to identify node type for {node}: {exc}", source=_SOURCE)
            result = False

        self._material_node_cache[node] = result
        return result

    _TRACE_NODE_BUDGET = 1000

    _TRACE_SKIP_NODES = {
        # Maya default bookkeeping containers.
        "defaultTextureList1", "defaultRenderUtilityList1",
        "defaultShaderList1", "defaultColorMgtGlobals",
        # Texture/UV source nodes.  They are not material targets and should
        # never be traversed as downstream shading nodes.
        "place2dTexture", "file",
    }

    def _trace_channel_targets(self, file_node, max_depth=4):
        """BFS trace all output endpoints of a file node, returning the list of attribute
        names on hit materials.
        """
        targets = []
        material_targets = set()
        visited = {file_node}
        queue = deque([(file_node, 0)])
        checked = 0
        budget_exceeded = False

        while queue:
            node, depth = queue.popleft()
            if depth >= max_depth:
                continue
            try:
                destinations = cmds.listConnections(
                    node, plugs=True, source=False, destination=True
                ) or []
            except Exception as exc:
                self.log.warn(f"Failed to trace downstream from {node}: {exc}", source=_SOURCE)
                continue

            for dest in dict.fromkeys(destinations):
                if "." not in dest:
                    continue
                dnode, attr_path = dest.split(".", 1)
                if dnode in self._TRACE_SKIP_NODES:
                    continue

                if self._is_material_node(dnode):
                    target_attr = attr_path.rsplit(".", 1)[-1]
                    key = (dnode, target_attr)
                    if key not in material_targets:
                        material_targets.add(key)
                        targets.append(target_attr)
                    continue

                if dnode in visited:
                    continue

                checked += 1
                if checked > self._TRACE_NODE_BUDGET:
                    budget_exceeded = True
                    break

                visited.add(dnode)
                queue.append((dnode, depth + 1))

            if budget_exceeded:
                self.log.warn(
                    f"Channel trace budget exceeded for {file_node} "
                    f"({self._TRACE_NODE_BUDGET} nodes); using partial targets",
                    source=_SOURCE,
                )
                break

        return targets

    def _match_by_channel(self, file_node):
        for attr_name in self._trace_channel_targets(file_node):
            n_attr = normalize_keyword(attr_name)
            for role, keywords in self.expanded_keywords.items():
                if n_attr in keywords:
                    return role
        return None

    def _auto_match_color_space(self):
        selected = cmds.ls(selection=True, type="file")
        if not selected:
            self.log.warn("Please select file nodes first.", source=_SOURCE)
            return

        self._material_node_cache.clear()
        default_role = self.cs_config.get("default", "raw")
        count = 0
        suspicious = []

        for f in selected:
            role_fn = self._match_by_filename(f)
            role_chan = self._match_by_channel(f)

            if role_fn and role_chan and role_fn != role_chan:
                suspicious.append((f, role_fn, role_chan))
                continue

            role = role_fn or role_chan or default_role

            if self._set_color_space(f, role):
                count += 1
                self.log.debug(f"{f}: set to {role}", source=_SOURCE)
            else:
                self.log.warn(f"{f}: no matching color space found for role '{role}'", source=_SOURCE)

        if suspicious:
            cmds.select([item[0] for item in suspicious], replace=True)
            for f, role_fn, role_chan in suspicious:
                path = cmds.getAttr(f"{f}.fileTextureName") or ""
                self.log.warn(
                    f"[Ambiguous] {path} ({f}): filename→{role_fn} "
                    f"vs channel→{role_chan}, skipped, handle manually",
                    source=_SOURCE,
                )
            self.log.info(
                f"Auto matched color space on {count}/{len(selected)} file node(s); "
                f"{len(suspicious)} ambiguous node(s) selected for manual review "
                f"(selection replaced with the ambiguous nodes).",
                source=_SOURCE,
            )
        else:
            self.log.info(f"Auto matched color space on {count}/{len(selected)} file node(s).", source=_SOURCE)
