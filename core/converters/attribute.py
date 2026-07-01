import pymel.core as pm

from core.prerequisites import apply_attr_prerequisites


class AttributeConverter:

    def __init__(self, config, utils, cc_converter):
        self.config = config
        self.utils = utils
        self.cc_converter = cc_converter

    def collect_attrs(self, mat, source_config):
        attrs_to_collect = set()
        for common_attr in self.config.get_common_attrs():
            maya_attr = source_config.get_maya_attr(common_attr)
            if maya_attr:
                attrs_to_collect.add(maya_attr)

        bump_attrs = source_config.attr_map.get("normal_bump", "")
        if bump_attrs:
            attrs_to_collect.add(bump_attrs)

        return self.utils.collect_attribute_info(mat, list(attrs_to_collect))

    def _zero_black_colors(self, attr_info, source_config):
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

    def _fix_alpha_luminance(self, target_mat, target_renderer, log):
        if target_renderer == "redshift":
            return

        for common_attr in self.config.get_common_attrs():
            try:
                plug = target_mat.attr(common_attr)
                conns = plug.connections(plugs=True, source=True)
                for conn in conns:
                    if conn.attrName(longName=True) == "outAlpha":
                        tex_node = conn.node()
                        if (tex_node.hasAttr("alphaIsLuminance")
                                and not tex_node.alphaIsLuminance.get()):
                            tex_node.alphaIsLuminance.set(True)
                            log.append(f"  Enabled Alpha Is Luminance on {tex_node}")
            except Exception:
                pass

    def _fix_vray_emission(self, attr_info, source_config, target_mat, target_config):
        if source_config.get_maya_attr("emissionWeight"):
            return

        color_attr = source_config.get_maya_attr("emissionColor")
        color_data = attr_info.get(color_attr) if color_attr else None
        if not color_data:
            return

        has_connection = color_data.get("connection") is not None
        val = color_data.get("value")
        is_non_black = isinstance(val, (tuple, list)) and tuple(val) != (0, 0, 0)
        if not (has_connection or is_non_black):
            return

        if weight_attr := target_config.get_maya_attr("emissionWeight"):
            try:
                target_mat.attr(weight_attr).set(1)
            except Exception:
                pm.warning(f"AttributeConverter: failed to set emission weight on {target_mat.name()}")

    def transfer_all(self, target_mat, source_config, target_config, target_renderer,
                     attr_info, cc_cache, log):
        self._zero_black_colors(attr_info, source_config)
        self._fix_vray_emission(attr_info, source_config, target_mat, target_config)
        skip_attrs = {"normal_bump", "displacementScale", "displacementTexture"}
        for common_attr in self.config.get_common_attrs():
            if common_attr in skip_attrs:
                continue
            src_maya_attr = source_config.get_maya_attr(common_attr)
            tgt_maya_attr = target_config.get_maya_attr(common_attr)

            if not src_maya_attr or not tgt_maya_attr:
                continue

            src_data = attr_info.get(src_maya_attr)
            if not src_data:
                continue

            apply_attr_prerequisites(target_mat, target_config, common_attr)
            self._transfer_one(target_mat, tgt_maya_attr, src_maya_attr,
                               src_data, cc_cache, target_renderer, log)

        self._fix_alpha_luminance(target_mat, target_renderer, log)

    def _transfer_one(self, target_mat, target_attr, src_attr_name,
                       src_data, cc_cache, target_renderer, log):
        try:
            target_plug = target_mat.attr(target_attr)
        except Exception:
            return

        connection = src_data.get("connection")
        value = src_data.get("value")

        if connection:
            cc_entry = cc_cache.get(src_attr_name)

            if cc_entry:
                self.cc_converter.transfer(cc_entry, target_plug, target_renderer, log)
                chain_plug = cc_entry.get("output_plug")
                if chain_plug and not self.utils.is_cc_node(chain_plug.node()):
                    self.utils.smart_connect(chain_plug, target_plug)
            else:
                src_conn_plug = connection.get("plug")
                if src_conn_plug:
                    self.utils.smart_connect(src_conn_plug, target_plug)
        elif isinstance(value, (int, float)):
            try:
                target_plug.set(value)
            except Exception:
                pm.warning(f"AttributeConverter: failed to set float value on {target_mat.name()}.{target_attr}")
        elif isinstance(value, (tuple, list)) and len(value) >= 3:
            try:
                target_plug.set(value)
            except Exception:
                try:
                    target_plug.set(value[0])
                except Exception:
                    pm.warning(f"AttributeConverter: failed to set color value on {target_mat.name()}.{target_attr}")
