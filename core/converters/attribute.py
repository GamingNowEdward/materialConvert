import maya.cmds as cmds

from core.logger import get_logger
from core.prerequisites import apply_attr_prerequisites

_SOURCE = "AttributeConverter"


class AttributeConverter:

    def __init__(self, config, utils, cc_converter, logger=None):
        self.config = config
        self.utils = utils
        self.cc_converter = cc_converter
        self.log = logger or get_logger()

    def collect_attrs(self, mat, source_config):
        attrs_to_collect = set()
        for common_attr in self.config.get_common_attrs():
            maya_attr = source_config.get_maya_attr(common_attr)
            if maya_attr:
                attrs_to_collect.add(maya_attr)

        bump_attrs = source_config.attr_map.get("normal_bump", "")
        if bump_attrs:
            attrs_to_collect.add(bump_attrs)

        self.log.debug(
            f"Collecting {len(attrs_to_collect)} source attribute(s): {sorted(attrs_to_collect)}",
            source=_SOURCE,
        )
        return self.utils.collect_attribute_info(mat, list(attrs_to_collect), logger=self.log)

    def _zero_black_colors(self, attr_info, source_config):
        changed = []
        for color_ca, weight_ca in self.config.get_color_weight_pairs():
            color_attr = source_config.get_maya_attr(color_ca)
            weight_attr = source_config.get_maya_attr(weight_ca)
            if not (color_attr and weight_attr):
                continue

            color_data = attr_info.get(color_attr)
            weight_data = attr_info.get(weight_attr)
            if (not color_data or not weight_data
                    or color_data.get("connection")
                    or weight_data.get("connection")):
                continue

            color_val = color_data.get("value")
            weight_val = weight_data.get("value")
            if (isinstance(color_val, (tuple, list)) and tuple(color_val) == (0, 0, 0)
                    and isinstance(weight_val, (int, float)) and weight_val > 0):
                weight_data["value"] = 0
                changed.append(f"{color_attr}/{weight_attr}")

        if changed:
            self.log.info(
                f"Zeroed weight for black source color(s): {', '.join(changed)}",
                source=_SOURCE,
            )
        else:
            self.log.debug("No black-color weight pairs required zeroing", source=_SOURCE)

    _FIX_ALPHA_SKIP = {"opacity", "displacementScale", "displacementTexture"}

    def _fix_alpha_luminance(self, target_mat, target_renderer, target_config):
        if target_renderer == "redshift":
            self.log.debug("Alpha Is Luminance fix skipped for Redshift target", source=_SOURCE)
            return

        fixed = []
        for common_attr, maya_attr in target_config.attr_map.items():
            if common_attr in self._FIX_ALPHA_SKIP or not maya_attr:
                continue

            plug = f"{target_mat}.{maya_attr}"
            try:
                plug_exists = cmds.objExists(plug)
            except Exception as exc:
                self.log.warn(f"Failed to query {plug}: {exc}", source=_SOURCE)
                continue

            if not plug_exists:
                continue

            alpha_plug = self._trace_alpha_plug(plug)
            if not alpha_plug:
                self.log.debug(f"No alpha source traced for {plug}", source=_SOURCE)
                continue

            tex_node = alpha_plug.split(".")[0]
            try:
                if (cmds.attributeQuery("alphaIsLuminance", node=tex_node, exists=True)
                        and not cmds.getAttr(f"{tex_node}.alphaIsLuminance")):
                    cmds.setAttr(f"{tex_node}.alphaIsLuminance", True)
                    fixed.append(tex_node)
                    self.log.debug(f"Enabled Alpha Is Luminance on {tex_node}", source=_SOURCE)
            except Exception as exc:
                self.log.warn(f"Failed to enable alphaIsLuminance on {tex_node}: {exc}", source=_SOURCE)

        if fixed:
            self.log.info(f"Enabled Alpha Is Luminance on {len(fixed)} texture node(s)", source=_SOURCE)

    def _trace_alpha_plug(self, start, visited=None, depth=0):
        """Recursively trace upstream from an attribute/node to find the bitmap texture
        source plug feeding *.outAlpha.
        """
        if depth > 10 or not start:
            self.log.debug(f"Alpha trace stopped at {start!r} (depth={depth})", source=_SOURCE)
            return None
        if visited is None:
            visited = set()

        try:
            conns = cmds.listConnections(start, plugs=True, source=True) or []
        except Exception as exc:
            self.log.warn(f"Failed to trace alpha upstream from {start}: {exc}", source=_SOURCE)
            return None

        for conn in conns:
            if conn.endswith(".outAlpha"):
                node = conn.split(".")[0]
                try:
                    has_file = cmds.attributeQuery("fileTextureName", node=node, exists=True)
                except Exception as exc:
                    self.log.warn(f"Failed to query fileTextureName on {node}: {exc}", source=_SOURCE)
                    has_file = False
                if has_file:
                    self.log.debug(f"Alpha source found: {conn}", source=_SOURCE)
                    return conn
                if node in visited:
                    continue
                visited.add(node)
                result = self._trace_alpha_plug(node, visited, depth + 1)
                if result:
                    return result

        for conn in conns:
            src_node = conn.split(".")[0]
            if src_node in visited:
                continue
            visited.add(src_node)
            result = self._trace_alpha_plug(src_node, visited, depth + 1)
            if result:
                return result
        return None

    def _fix_vray_emission(self, attr_info, source_config, target_mat, target_config):
        if source_config.get_maya_attr("emissionWeight"):
            self.log.debug("Source already has emissionWeight mapping; V-Ray emission fix skipped", source=_SOURCE)
            return

        color_attr = source_config.get_maya_attr("emissionColor")
        color_data = attr_info.get(color_attr) if color_attr else None
        if not color_data:
            self.log.debug("No emissionColor source data; V-Ray emission fix skipped", source=_SOURCE)
            return

        has_connection = color_data.get("connection") is not None
        val = color_data.get("value")
        is_non_black = isinstance(val, (tuple, list)) and tuple(val) != (0, 0, 0)
        if not (has_connection or is_non_black):
            return

        weight_attr = target_config.get_maya_attr("emissionWeight")
        if not weight_attr:
            return

        try:
            cmds.setAttr(f"{target_mat}.{weight_attr}", 1)
            self.log.debug(f"Enabled emission weight on {target_mat}.{weight_attr}", source=_SOURCE)
        except Exception as exc:
            self.log.warn(f"Failed to set emission weight on {target_mat}.{weight_attr}: {exc}", source=_SOURCE)

    def transfer_all(self, target_mat, source_config, target_config, target_renderer,
                     attr_info, cc_cache):
        self._zero_black_colors(attr_info, source_config)
        self._fix_vray_emission(attr_info, source_config, target_mat, target_config)

        transferred = 0
        skipped = 0
        skip_attrs = {"normal_bump", "displacementScale", "displacementTexture"}
        for common_attr in self.config.get_common_attrs():
            if common_attr in skip_attrs:
                self.log.debug(f"Skipping specialized attribute {common_attr}", source=_SOURCE)
                continue

            src_maya_attr = source_config.get_maya_attr(common_attr)
            tgt_maya_attr = target_config.get_maya_attr(common_attr)

            if not src_maya_attr or not tgt_maya_attr:
                self.log.debug(
                    f"{common_attr}: unmapped (src={src_maya_attr!r}, tgt={tgt_maya_attr!r})",
                    source=_SOURCE,
                )
                skipped += 1
                continue

            src_data = attr_info.get(src_maya_attr)
            if not src_data:
                self.log.debug(f"{common_attr}: no source data for {src_maya_attr}", source=_SOURCE)
                skipped += 1
                continue

            apply_attr_prerequisites(target_mat, target_config, common_attr, logger=self.log)
            if self._transfer_one(target_mat, tgt_maya_attr, src_maya_attr,
                                  src_data, cc_cache, target_renderer):
                transferred += 1
            else:
                skipped += 1

        self._fix_alpha_luminance(target_mat, target_renderer, target_config)
        self.log.info(
            f"Attribute transfer finished: {transferred} transferred, {skipped} skipped",
            source=_SOURCE,
        )

    def _transfer_one(self, target_mat, target_attr, src_attr_name,
                      src_data, cc_cache, target_renderer):
        target_plug = f"{target_mat}.{target_attr}"
        try:
            plug_exists = cmds.objExists(target_plug)
        except Exception as exc:
            self.log.warn(f"Failed to query {target_plug}: {exc}", source=_SOURCE)
            return False

        if not plug_exists:
            self.log.skip(f"{src_attr_name}: target plug {target_plug} does not exist", source=_SOURCE)
            return False

        connection = src_data.get("connection")
        value = src_data.get("value")

        if connection:
            cc_entry = cc_cache.get(src_attr_name)

            if cc_entry:
                self.cc_converter.transfer(cc_entry, target_plug, target_renderer)
                chain_plug = cc_entry.get("output_plug")
                if chain_plug and not self.utils.is_cc_node(
                        chain_plug.split(".")[0], self.config, logger=self.log):
                    self.utils.smart_connect(chain_plug, target_plug, logger=self.log)
                self.log.debug(f"{src_attr_name}: transferred CC chain to {target_plug}", source=_SOURCE)
                return True

            src_conn_plug = connection.get("plug")
            if not src_conn_plug:
                self.log.warn(
                    f"{src_attr_name}: source connection has no plug for {target_plug}",
                    source=_SOURCE,
                )
                return False

            if self.utils.smart_connect(src_conn_plug, target_plug, logger=self.log):
                self.log.debug(f"{src_attr_name}: connected {src_conn_plug} -> {target_plug}", source=_SOURCE)
                return True
            self.log.warn(f"{src_attr_name}: failed to connect {src_conn_plug} -> {target_plug}", source=_SOURCE)
            return False

        if isinstance(value, (int, float)):
            try:
                attr_type = cmds.getAttr(target_plug, type=True)
                if attr_type in ("float3", "double3"):
                    cmds.setAttr(target_plug, value, value, value)
                    self.log.debug(f"{src_attr_name}: broadcast float {value} -> {target_plug}", source=_SOURCE)
                else:
                    cmds.setAttr(target_plug, value)
                    self.log.debug(f"{src_attr_name}: set {target_plug} = {value}", source=_SOURCE)
                return True
            except Exception as exc:
                self.log.warn(f"{src_attr_name}: failed to set float value on {target_plug}: {exc}", source=_SOURCE)
                return False

        if isinstance(value, (tuple, list)) and len(value) >= 3:
            try:
                cmds.setAttr(target_plug, *value)
                self.log.debug(f"{src_attr_name}: set color {target_plug} = {tuple(value)}", source=_SOURCE)
                return True
            except Exception as first_exc:
                self.log.debug(
                    f"{src_attr_name}: color set failed on {target_plug}, trying first channel: {first_exc}",
                    source=_SOURCE,
                )
                try:
                    cmds.setAttr(target_plug, value[0])
                    self.log.info(
                        f"{src_attr_name}: color fell back to first channel on {target_plug}",
                        source=_SOURCE,
                    )
                    return True
                except Exception as second_exc:
                    self.log.warn(
                        f"{src_attr_name}: failed to set color value on {target_plug}: "
                        f"first={first_exc}, second={second_exc}",
                        source=_SOURCE,
                    )
                    return False

        self.log.skip(f"{src_attr_name}: unsupported value type {type(value).__name__}", source=_SOURCE)
        return False
