import pymel.core as pm
import maya.cmds as cmds


class BumpConverter:

    def __init__(self, config, utils):
        self.config = config
        self.utils = utils

    def convert(self, source_mat, target_mat, source_renderer, target_renderer, log):
        src_bn_config = self.config.get_bump_normal_config(source_renderer)
        tgt_bn_config = self.config.get_bump_normal_config(target_renderer)

        if not src_bn_config or not tgt_bn_config:
            return

        tgt_bump = tgt_bn_config.bump
        tgt_normal = tgt_bn_config.normal

        src_bn_info = self._collect(source_mat, src_bn_config)
        if not src_bn_info:
            return

        bump_info = src_bn_info.get("bump")
        normal_info = src_bn_info.get("normal")

        # bump_info and normal_info are mutually exclusive for a given source:
        # separate-type nodes (aiBump2d/aiNormalMap) produce only one entry;
        # shared-type nodes (bump2d/RedshiftBumpMap) produce only one via
        # should_skip logic in _collect based on isNormal / input_type value.
        info = bump_info or normal_info
        if not info:
            return

        node = info.pop("bn_node", None)
        base_name = node.name() if node else source_mat.name()
        is_normal_mode = info.get("is_normal", False)
        tgt_mapping = tgt_normal if is_normal_mode else tgt_bump

        self._do_convert(
            info, target_mat, tgt_mapping,
            target_renderer, is_normal=is_normal_mode, source_name=base_name, log=log
        )

    def reuse_existing(self, source_mat, new_mat, source_renderer, log):
        src_bn_config = self.config.get_bump_normal_config(source_renderer)
        if not src_bn_config:
            return

        src_mat_config = self.config.get_material_config(self.utils.identify_node_type(source_mat))
        if not src_mat_config:
            return
        src_bump_attr = src_mat_config.attr_map.get("normal_bump", "")
        if not src_bump_attr:
            return

        new_mat_config = self.config.get_material_config(self.utils.identify_node_type(new_mat))
        if not new_mat_config:
            return
        new_bump_attr = new_mat_config.attr_map.get("normal_bump", "")
        if not new_bump_attr:
            return

        try:
            conns = source_mat.attr(src_bump_attr).connections(plugs=False, source=True)
            if conns:
                src_node = conns[0]
                src_node.attr(src_bn_config.bump.target_connection) >> new_mat.attr(new_bump_attr)
                log.append("  Bump/Normal: reconnected existing node")
        except Exception:
            pass

    # ── Collect ─────────────────────────────────────────────

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
                result["bump"] = self._collect_node(source_mat, src_bn_config.bump, "bump")

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
                result["normal"] = self._collect_node(source_mat, src_bn_config.normal, "normal")

        return result

    def _read_material_bn(self, source_mat, bn_mapping):
        scale_attr = bn_mapping.scale
        input_attr = bn_mapping.input
        input_type_attr = bn_mapping.input_type
        input_type_value = bn_mapping.input_type_value

        scale_val = None
        if scale_attr:
            try:
                scale_val = source_mat.attr(scale_attr).get()
            except Exception:
                pm.warning(f"BumpConverter: failed to read scale [{scale_attr}] on {source_mat.name()}")

        input_plug = None
        if input_attr:
            try:
                conns = source_mat.attr(input_attr).connections(plugs=True, source=True)
                if conns:
                    input_plug = conns[0]
            except Exception:
                pass

        should_skip = False
        if input_type_attr and input_type_value is not None:
            try:
                actual = source_mat.attr(input_type_attr).get()
                if actual != input_type_value:
                    should_skip = True
            except Exception:
                pass
        elif bn_mapping.isNormal:
            try:
                actual = source_mat.attr(bn_mapping.isNormal).get()
                if actual != bn_mapping.isNormal_value:
                    should_skip = True
            except Exception:
                pass

        return {
            "scale_val": scale_val,
            "input_plug": input_plug,
            "should_skip": should_skip,
        }

    # ── Collect Node (4-step) ───────────────────────────────

    def _collect_node(self, material, bn_mapping, mode):
        bn_node = self._find_bn_node(material, bn_mapping)
        if bn_node is None:
            return None

        node_actual_type = pm.nodeType(bn_node)
        bn_renderer, bn_cfg = self.config.find_bn_renderer(node_actual_type)

        is_normal = self._detect_bn_mode(bn_node, node_actual_type, bn_renderer, mode)
        scale_val = self._read_bn_attrs(bn_node, bn_cfg, "scale")
        input_plug = self._read_bn_attrs(bn_node, bn_cfg, "source_connection", is_connection=True)

        common_config = self.config.get_material_config(self.utils.identify_node_type(material))
        bump_attr_name = common_config.attr_map.get("normal_bump", "") if common_config else ""

        return {
            "bn_node": bn_node,
            "target_attr": bump_attr_name,
            "scale": scale_val,
            "input_plug": input_plug,
            "is_normal": is_normal,
        }

    def _find_bn_node(self, material, bn_mapping):
        common_config = self.config.get_material_config(self.utils.identify_node_type(material))
        if common_config:
            bump_attr_name = common_config.attr_map.get("normal_bump", "")
            if bump_attr_name:
                try:
                    bump_plug = material.attr(bump_attr_name)
                    conns = bump_plug.connections(plugs=False, source=True)
                    if conns:
                        for conn in conns:
                            if pm.nodeType(conn) in self.config.get_all_bn_types():
                                return conn
                except Exception:
                    pass

        all_nodes = []
        for nt in self.config.get_all_bn_types():
            all_nodes.extend(pm.ls(type=nt))
        for node in all_nodes:
            try:
                out_conns = node.attr(bn_mapping.target_connection).connections(plugs=False)
            except Exception:
                continue
            for conn in out_conns:
                if conn == material:
                    return node

        return None

    def _detect_bn_mode(self, bn_node, node_actual_type, bn_renderer, default_mode):
        if bn_renderer is None:
            return default_mode == "normal"

        r_config = self.config.get_bump_normal_config(bn_renderer)
        bump_type = r_config.bump.node_type if r_config.bump else ""
        normal_type = r_config.normal.node_type if r_config.normal else ""

        if normal_type and normal_type == node_actual_type and normal_type != bump_type:
            return True
        if bump_type and bump_type == node_actual_type and bump_type != normal_type:
            return False
        if r_config.bump and r_config.bump.isNormal:
            try:
                actual = bn_node.attr(r_config.bump.isNormal).get()
                if r_config.normal and r_config.normal.isNormal_value is not None:
                    return actual == r_config.normal.isNormal_value
            except Exception:
                pm.warning(f"BumpConverter: failed to read {r_config.bump.isNormal} on {bn_node.name()}")
        return default_mode == "normal"

    def _read_bn_attrs(self, bn_node, bn_cfg, attr_name, is_connection=False):
        if bn_cfg is None:
            return None
        attr_val = getattr(bn_cfg, attr_name, None)
        if not attr_val:
            return None
        try:
            if is_connection:
                conns = bn_node.attr(attr_val).connections(plugs=True, source=True)
                return conns[0] if conns else None
            else:
                return bn_node.attr(attr_val).get()
        except Exception:
            pm.warning(f"BumpConverter: failed to read {attr_val} on {bn_node.name()}")
        return None

    # ── Do Convert ──────────────────────────────────────────

    def _do_convert(self, bn_info, target_mat, tgt_mapping,
                    target_renderer, is_normal, source_name, log):
        if not tgt_mapping:
            return

        input_plug = bn_info.get("input_plug")
        if not input_plug:
            return

        if tgt_mapping.is_material_attribute:
            self._convert_to_material(bn_info, target_mat, tgt_mapping, input_plug, log)
        else:
            self._convert_to_node(bn_info, target_mat, tgt_mapping,
                                  target_renderer, is_normal, source_name, input_plug, log)

    def _convert_to_material(self, bn_info, target_mat, tgt_mapping, input_plug, log):
        scale_attr = tgt_mapping.scale
        input_attr = tgt_mapping.input
        input_type_attr = getattr(tgt_mapping, "input_type", "")
        input_type_value = getattr(tgt_mapping, "input_type_value", None)

        if scale_attr and bn_info.get("scale") is not None:
            try:
                target_mat.attr(scale_attr).set(bn_info["scale"])
            except Exception:
                pm.warning(f"BumpConverter: failed to set scale [{scale_attr}] on {target_mat.name()}")

        if input_attr:
            self.utils.smart_connect(input_plug, target_mat.attr(input_attr))

        if input_type_attr and input_type_value is not None:
            try:
                target_mat.attr(input_type_attr).set(input_type_value)
            except Exception:
                pm.warning(f"BumpConverter: failed to set [{input_type_attr}] on {target_mat.name()}")
        elif tgt_mapping.isNormal:
            try:
                val = tgt_mapping.isNormal_value
                target_mat.attr(tgt_mapping.isNormal).set(val)
            except Exception:
                pm.warning(f"BumpConverter: failed to set isNormal on {target_mat.name()}")

        log.append("  Bump/Normal: converted to material attributes")

    def _convert_to_node(self, bn_info, target_mat, tgt_mapping,
                         target_renderer, is_normal, source_name, input_plug, log):
        renderer_map = {"arnold": "ai", "redshift": "rs", "vray": "vray"}
        renderer_short = renderer_map.get(target_renderer, target_renderer)
        bn_suffix = "_" + renderer_short + ("Nrm" if is_normal else "Bump")
        node_name = cmds.shadingNode(tgt_mapping.node_type, asUtility=True,
                                      name=source_name + bn_suffix)
        bn_node = pm.PyNode(node_name)

        if tgt_mapping.scale and bn_info.get("scale") is not None:
            try:
                bn_node.attr(tgt_mapping.scale).set(bn_info["scale"])
            except Exception:
                pm.warning(f"BumpConverter: failed to set scale on {bn_node.name()}")

        if tgt_mapping.source_connection:
            self.utils.smart_connect(input_plug, bn_node.attr(tgt_mapping.source_connection))

        if tgt_mapping.isNormal:
            try:
                bn_node.attr(tgt_mapping.isNormal).set(tgt_mapping.isNormal_value)
            except Exception:
                pm.warning(f"BumpConverter: failed to set isNormal on {bn_node.name()}")

        common_config = self.config.get_material_config(pm.nodeType(target_mat))
        if common_config:
            bump_attr = common_config.attr_map.get("normal_bump", "")
            if bump_attr:
                try:
                    bn_node.attr(tgt_mapping.target_connection) >> target_mat.attr(bump_attr)
                except Exception:
                    pm.warning(f"BumpConverter: failed to connect {bn_node.name()} to {target_mat.name()}.{bump_attr}")

        log.append(f"  Bump/Normal: converted to {tgt_mapping.node_type} node")
