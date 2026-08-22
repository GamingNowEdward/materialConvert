import maya.cmds as cmds

from core.logger import get_logger
from core.node_utils import RENDERER_SHORT

_SOURCE = "BumpConverter"


class BumpConverter:

    def __init__(self, config, utils, logger=None):
        self.config = config
        self.utils = utils
        self.log = logger or get_logger()

    def convert(self, source_mat, target_mat, source_renderer, target_renderer):
        src_bn_config = self.config.get_bump_normal_config(source_renderer)
        tgt_bn_config = self.config.get_bump_normal_config(target_renderer)

        if not src_bn_config or not tgt_bn_config:
            self.log.skip(
                f"Bump/Normal conversion skipped: no config "
                f"(src={source_renderer}, tgt={target_renderer})",
                source=_SOURCE,
            )
            return

        tgt_bump = tgt_bn_config.bump
        tgt_normal = tgt_bn_config.normal

        src_bn_info = self._collect(source_mat, src_bn_config)
        if not src_bn_info:
            self.log.skip(f"No source bump/normal data found on {source_mat}", source=_SOURCE)
            return

        bump_info = src_bn_info.get("bump")
        normal_info = src_bn_info.get("normal")

        info = bump_info or normal_info
        if not info:
            self.log.skip(f"No usable bump/normal mapping collected from {source_mat}", source=_SOURCE)
            return

        node = info.pop("bn_node", None)
        base_name = node if node else source_mat
        is_normal_mode = info.get("is_normal", False)
        tgt_mapping = tgt_normal if is_normal_mode else tgt_bump

        self._do_convert(
            info, target_mat, tgt_mapping,
            target_renderer, is_normal=is_normal_mode, source_name=base_name
        )

    def reuse_existing(self, source_mat, new_mat, source_renderer):
        src_bn_config = self.config.get_bump_normal_config(source_renderer)
        if not src_bn_config:
            self.log.skip(f"No bump/normal config for source renderer {source_renderer}", source=_SOURCE)
            return

        try:
            source_type = self.utils.identify_node_type(source_mat)
        except Exception as exc:
            self.log.warn(f"Failed to identify source material {source_mat}: {exc}", source=_SOURCE)
            return
        src_mat_config = self.config.get_material_config(source_type)
        if not src_mat_config:
            self.log.warn(f"No material config for {source_type}", source=_SOURCE)
            return
        src_bump_attr = src_mat_config.attr_map.get("normal_bump", "")
        if not src_bump_attr:
            self.log.skip(f"Source material {source_mat} has no normal_bump mapping", source=_SOURCE)
            return

        try:
            target_type = self.utils.identify_node_type(new_mat)
        except Exception as exc:
            self.log.warn(f"Failed to identify target material {new_mat}: {exc}", source=_SOURCE)
            return
        new_mat_config = self.config.get_material_config(target_type)
        if not new_mat_config:
            self.log.warn(f"No material config for {target_type}", source=_SOURCE)
            return
        new_bump_attr = new_mat_config.attr_map.get("normal_bump", "")
        if not new_bump_attr:
            self.log.skip(f"Target material {new_mat} has no normal_bump mapping", source=_SOURCE)
            return

        try:
            conns = cmds.listConnections(f"{source_mat}.{src_bump_attr}", source=True, destination=False) or []
            if not conns:
                self.log.skip(f"No source bump connection on {source_mat}.{src_bump_attr}", source=_SOURCE)
                return
            src_node = conns[0]
            cmds.connectAttr(f"{src_node}.{src_bn_config.bump.target_connection}",
                             f"{new_mat}.{new_bump_attr}", force=True)
            self.log.info(
                f"Bump/Normal: reconnected existing {src_node} -> {new_mat}.{new_bump_attr}",
                source=_SOURCE,
            )
        except Exception as exc:
            self.log.warn(f"Bump/Normal reuse failed for {source_mat} -> {new_mat}: {exc}", source=_SOURCE)

    def _collect(self, source_mat, src_bn_config):
        result = {}

        if src_bn_config.bump:
            if src_bn_config.bump.is_material_attribute:
                data = self._read_material_bn(source_mat, src_bn_config.bump)
                if data and not data["should_skip"]:
                    result["bump"] = {
                        "scale": data["scale_val"],
                        "input_plug": data["input_plug"],
                        "is_normal": False,
                    }
                else:
                    self.log.debug(f"Source bump material attribute skipped on {source_mat}", source=_SOURCE)
            else:
                bump = self._collect_node(source_mat, src_bn_config.bump, "bump")
                if bump:
                    result["bump"] = bump
                else:
                    self.log.debug(f"No bump node found on {source_mat}", source=_SOURCE)

        if src_bn_config.normal:
            if src_bn_config.normal.is_material_attribute:
                data = self._read_material_bn(source_mat, src_bn_config.normal)
                if data and not data["should_skip"]:
                    result["normal"] = {
                        "scale": data["scale_val"],
                        "input_plug": data["input_plug"],
                        "is_normal": True,
                    }
                else:
                    self.log.debug(f"Source normal material attribute skipped on {source_mat}", source=_SOURCE)
            else:
                normal = self._collect_node(source_mat, src_bn_config.normal, "normal")
                if normal:
                    result["normal"] = normal
                else:
                    self.log.debug(f"No normal node found on {source_mat}", source=_SOURCE)

        self.log.debug(
            f"Bump/Normal collection result for {source_mat}: {sorted(result.keys())}",
            source=_SOURCE,
        )
        return result

    def _read_material_bn(self, source_mat, bn_mapping):
        scale_attr = bn_mapping.scale
        input_attr = bn_mapping.input
        input_type_attr = bn_mapping.input_type
        input_type_value = bn_mapping.input_type_value

        scale_val = None
        if scale_attr:
            try:
                scale_val = cmds.getAttr(f"{source_mat}.{scale_attr}")
                self.log.debug(f"Read {source_mat}.{scale_attr} = {scale_val!r}", source=_SOURCE)
            except Exception as exc:
                self.log.warn(f"Failed to read scale [{scale_attr}] on {source_mat}: {exc}", source=_SOURCE)

        input_plug = None
        if input_attr:
            try:
                conns = cmds.listConnections(f"{source_mat}.{input_attr}", plugs=True, source=True) or []
                if conns:
                    input_plug = conns[0]
                    self.log.debug(f"Read bump/normal input on {source_mat}.{input_attr}: {input_plug}", source=_SOURCE)
                else:
                    self.log.debug(f"No bump/normal input connected to {source_mat}.{input_attr}", source=_SOURCE)
            except Exception as exc:
                self.log.warn(f"Failed to read bump/normal input on {source_mat}.{input_attr}: {exc}", source=_SOURCE)

        should_skip = False
        if input_type_attr and input_type_value is not None:
            try:
                actual = cmds.getAttr(f"{source_mat}.{input_type_attr}")
                if actual != input_type_value:
                    should_skip = True
                    self.log.debug(
                        f"{source_mat}.{input_type_attr}={actual!r} != {input_type_value!r}; skipping",
                        source=_SOURCE,
                    )
            except Exception as exc:
                self.log.warn(f"Failed to read {source_mat}.{input_type_attr}: {exc}", source=_SOURCE)
        elif bn_mapping.is_normal:
            try:
                actual = cmds.getAttr(f"{source_mat}.{bn_mapping.is_normal}")
                if actual != bn_mapping.is_normal_value:
                    should_skip = True
                    self.log.debug(
                        f"{source_mat}.{bn_mapping.is_normal}={actual!r} != "
                        f"{bn_mapping.is_normal_value!r}; skipping",
                        source=_SOURCE,
                    )
            except Exception as exc:
                self.log.warn(f"Failed to read {source_mat}.{bn_mapping.is_normal}: {exc}", source=_SOURCE)

        return {
            "scale_val": scale_val,
            "input_plug": input_plug,
            "should_skip": should_skip,
        }

    def _collect_node(self, material, bn_mapping, mode):
        bn_node = self._find_bn_node(material, bn_mapping)
        if bn_node is None:
            return None

        node_actual_type = cmds.nodeType(bn_node)
        bn_renderer, bn_cfg = self.config.find_bn_renderer(node_actual_type)

        is_normal = self._detect_bn_mode(bn_node, node_actual_type, bn_renderer, mode)
        scale_val = self._read_bn_attrs(bn_node, bn_cfg, "scale")
        input_plug = self._read_bn_attrs(bn_node, bn_cfg, "source_connection", is_connection=True)

        common_config = self.config.get_material_config(self.utils.identify_node_type(material))
        bump_attr_name = common_config.attr_map.get("normal_bump", "") if common_config else ""

        self.log.debug(
            f"Collected bump/normal node {bn_node}: type={node_actual_type}, "
            f"renderer={bn_renderer}, is_normal={is_normal}",
            source=_SOURCE,
        )
        return {
            "bn_node": bn_node,
            "target_attr": bump_attr_name,
            "scale": scale_val,
            "input_plug": input_plug,
            "is_normal": is_normal,
        }

    def _find_bn_node(self, material, bn_mapping):
        try:
            material_type = self.utils.identify_node_type(material)
        except Exception as exc:
            self.log.warn(f"Failed to identify material {material}: {exc}", source=_SOURCE)
            return None

        common_config = self.config.get_material_config(material_type)
        if common_config:
            bump_attr_name = common_config.attr_map.get("normal_bump", "")
            if bump_attr_name:
                try:
                    conns = cmds.listConnections(f"{material}.{bump_attr_name}",
                                                 source=True, destination=False) or []
                    for conn in conns:
                        if cmds.nodeType(conn) in self.config.get_all_bn_types():
                            self.log.debug(f"Found bump/normal node {conn} on {material}.{bump_attr_name}", source=_SOURCE)
                            return conn
                except Exception as exc:
                    self.log.warn(
                        f"Failed to list bump/normal connections on {material}.{bump_attr_name}: {exc}",
                        source=_SOURCE,
                    )

        all_nodes = []
        for nt in self.config.get_all_bn_types():
            try:
                found = cmds.ls(type=nt) or []
            except Exception as exc:
                self.log.warn(f"Failed to list bump/normal nodes of type {nt}: {exc}", source=_SOURCE)
                continue
            all_nodes.extend(found)

        self.log.debug(f"Scanning {len(all_nodes)} bump/normal node(s) for {material}", source=_SOURCE)
        for node in all_nodes:
            try:
                out_conns = cmds.listConnections(f"{node}.{bn_mapping.target_connection}",
                                                 destination=True, source=False) or []
            except Exception as exc:
                self.log.warn(
                    f"Failed to list outputs for {node}.{bn_mapping.target_connection}: {exc}",
                    source=_SOURCE,
                )
                continue
            for conn in out_conns:
                if conn == material:
                    self.log.debug(f"Found bump/normal node {node} feeding {material}", source=_SOURCE)
                    return node

        self.log.debug(f"No bump/normal node found for {material}", source=_SOURCE)
        return None

    def _detect_bn_mode(self, bn_node, node_actual_type, bn_renderer, default_mode):
        if bn_renderer is None:
            self.log.warn(
                f"Unknown bump/normal node type {node_actual_type}; defaulting mode to "
                f"{'normal' if default_mode == 'normal' else 'bump'}",
                source=_SOURCE,
            )
            return default_mode == "normal"

        r_config = self.config.get_bump_normal_config(bn_renderer)
        bump_type = r_config.bump.node_type if r_config.bump else ""
        normal_type = r_config.normal.node_type if r_config.normal else ""

        if normal_type and normal_type == node_actual_type and normal_type != bump_type:
            return True
        if bump_type and bump_type == node_actual_type and bump_type != normal_type:
            return False
        if r_config.bump and r_config.bump.is_normal:
            try:
                actual = cmds.getAttr(f"{bn_node}.{r_config.bump.is_normal}")
                if r_config.normal and r_config.normal.is_normal_value is not None:
                    return actual == r_config.normal.is_normal_value
            except Exception as exc:
                self.log.warn(f"Failed to read {bn_node}.{r_config.bump.is_normal}: {exc}", source=_SOURCE)
        return default_mode == "normal"

    def _read_bn_attrs(self, bn_node, bn_cfg, attr_name, is_connection=False):
        if bn_cfg is None:
            return None
        attr_val = getattr(bn_cfg, attr_name, None)
        if not attr_val:
            return None
        try:
            if is_connection:
                conns = cmds.listConnections(f"{bn_node}.{attr_val}", plugs=True, source=True) or []
                result = conns[0] if conns else None
                self.log.debug(f"Read connection {bn_node}.{attr_val}: {result}", source=_SOURCE)
                return result
            result = cmds.getAttr(f"{bn_node}.{attr_val}")
            self.log.debug(f"Read {bn_node}.{attr_val} = {result!r}", source=_SOURCE)
            return result
        except Exception as exc:
            self.log.warn(f"Failed to read {bn_node}.{attr_val}: {exc}", source=_SOURCE)
        return None

    def _do_convert(self, bn_info, target_mat, tgt_mapping,
                    target_renderer, is_normal, source_name):
        if not tgt_mapping:
            self.log.skip(
                f"Target renderer {target_renderer} has no "
                f"{'normal' if is_normal else 'bump'} mapping",
                source=_SOURCE,
            )
            return

        input_plug = bn_info.get("input_plug")
        if not input_plug:
            self.log.skip("Bump/Normal conversion skipped: no input connection", source=_SOURCE)
            return

        if tgt_mapping.is_material_attribute:
            self._convert_to_material(bn_info, target_mat, tgt_mapping, input_plug)
        else:
            self._convert_to_node(bn_info, target_mat, tgt_mapping,
                                  target_renderer, is_normal, source_name, input_plug)

    def _convert_to_material(self, bn_info, target_mat, tgt_mapping, input_plug):
        scale_attr = tgt_mapping.scale
        input_attr = tgt_mapping.input
        input_type_attr = getattr(tgt_mapping, "input_type", "")
        input_type_value = getattr(tgt_mapping, "input_type_value", None)

        if scale_attr and bn_info.get("scale") is not None:
            try:
                cmds.setAttr(f"{target_mat}.{scale_attr}", bn_info["scale"])
                self.log.debug(f"Set {target_mat}.{scale_attr} = {bn_info['scale']!r}", source=_SOURCE)
            except Exception as exc:
                self.log.warn(f"Failed to set scale [{scale_attr}] on {target_mat}: {exc}", source=_SOURCE)

        if input_attr:
            if self.utils.smart_connect(input_plug, f"{target_mat}.{input_attr}", logger=self.log):
                self.log.debug(f"Connected bump/normal input {input_plug} -> {target_mat}.{input_attr}", source=_SOURCE)
            else:
                self.log.warn(f"Failed to connect {input_plug} -> {target_mat}.{input_attr}", source=_SOURCE)

        if input_type_attr and input_type_value is not None:
            try:
                cmds.setAttr(f"{target_mat}.{input_type_attr}", input_type_value)
                self.log.debug(f"Set {target_mat}.{input_type_attr} = {input_type_value!r}", source=_SOURCE)
            except Exception as exc:
                self.log.warn(f"Failed to set [{input_type_attr}] on {target_mat}: {exc}", source=_SOURCE)
        elif tgt_mapping.is_normal:
            try:
                cmds.setAttr(f"{target_mat}.{tgt_mapping.is_normal}", tgt_mapping.is_normal_value)
                self.log.debug(
                    f"Set {target_mat}.{tgt_mapping.is_normal} = {tgt_mapping.is_normal_value!r}",
                    source=_SOURCE,
                )
            except Exception as exc:
                self.log.warn(f"Failed to set is_normal on {target_mat}: {exc}", source=_SOURCE)

        self.log.info("Bump/Normal: converted to material attributes", source=_SOURCE)

    def _convert_to_node(self, bn_info, target_mat, tgt_mapping,
                         target_renderer, is_normal, source_name, input_plug):
        renderer_short = RENDERER_SHORT.get(target_renderer, target_renderer)
        bn_suffix = "_" + renderer_short + ("Nrm" if is_normal else "Bump")
        bn_node = cmds.shadingNode(tgt_mapping.node_type, asUtility=True,
                                   name=source_name + bn_suffix)
        self.log.debug(f"Created bump/normal node {bn_node}", source=_SOURCE)

        if tgt_mapping.scale and bn_info.get("scale") is not None:
            try:
                cmds.setAttr(f"{bn_node}.{tgt_mapping.scale}", bn_info["scale"])
                self.log.debug(f"Set {bn_node}.{tgt_mapping.scale} = {bn_info['scale']!r}", source=_SOURCE)
            except Exception as exc:
                self.log.warn(f"Failed to set scale on {bn_node}: {exc}", source=_SOURCE)

        if tgt_mapping.source_connection:
            if self.utils.smart_connect(input_plug, f"{bn_node}.{tgt_mapping.source_connection}", logger=self.log):
                self.log.debug(
                    f"Connected bump/normal source {input_plug} -> {bn_node}.{tgt_mapping.source_connection}",
                    source=_SOURCE,
                )
            else:
                self.log.warn(
                    f"Failed to connect {input_plug} -> {bn_node}.{tgt_mapping.source_connection}",
                    source=_SOURCE,
                )

        if tgt_mapping.is_normal:
            try:
                cmds.setAttr(f"{bn_node}.{tgt_mapping.is_normal}", tgt_mapping.is_normal_value)
                self.log.debug(
                    f"Set {bn_node}.{tgt_mapping.is_normal} = {tgt_mapping.is_normal_value!r}",
                    source=_SOURCE,
                )
            except Exception as exc:
                self.log.warn(f"Failed to set is_normal on {bn_node}: {exc}", source=_SOURCE)

        try:
            target_type = cmds.nodeType(target_mat)
        except Exception as exc:
            self.log.warn(f"Failed to identify target material {target_mat}: {exc}", source=_SOURCE)
            return
        common_config = self.config.get_material_config(target_type)
        if common_config:
            bump_attr = common_config.attr_map.get("normal_bump", "")
            if bump_attr:
                try:
                    cmds.connectAttr(f"{bn_node}.{tgt_mapping.target_connection}",
                                     f"{target_mat}.{bump_attr}", force=True)
                    self.log.info(
                        f"Bump/Normal: connected {bn_node} -> {target_mat}.{bump_attr}",
                        source=_SOURCE,
                    )
                except Exception as exc:
                    self.log.warn(f"Failed to connect {bn_node} -> {target_mat}.{bump_attr}: {exc}", source=_SOURCE)

        self.log.info(f"Bump/Normal: converted to {tgt_mapping.node_type} node", source=_SOURCE)
