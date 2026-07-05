import pymel.core as pm
import maya.cmds as cmds


class CCConverter:

    def __init__(self, config, utils):
        self.config = config
        self.utils = utils
        self._converted = {}

    def reset(self):
        self._converted.clear()

    def collect_chains(self, attr_info):
        cc_cache = {}
        for attr_name, data in attr_info.items():
            conn = data.get("connection")
            if conn:
                node = conn.get("node")
                if node:
                    cc_node_type = pm.nodeType(node)
                    src_cc_renderer = self.config.identify_cc_renderer(cc_node_type)
                    if src_cc_renderer:
                        self._cache(cc_cache, attr_name, node, src_cc_renderer, conn)
                    else:
                        history = cmds.listHistory(node.name(), future=False, pdo=True) or []
                        for h_name in history:
                            if h_name == node.name():
                                continue
                            h_node = pm.PyNode(h_name)
                            cc_node_type = pm.nodeType(h_node)
                            src_cc_renderer = self.config.identify_cc_renderer(cc_node_type)
                            if src_cc_renderer:
                                self._cache(cc_cache, attr_name, h_node, src_cc_renderer, conn)
                                break
        return cc_cache

    def _cache(self, cc_cache, attr_name, h_node, src_cc_renderer, conn):
        cc_config = self.config.get_color_correction_config(src_cc_renderer)
        params, input_plug = self.utils.collect_cc_chain_params(h_node, cc_config)

        cc_out_dests = []
        try:
            cc_out_dests = h_node.attr(cc_config.target_connection).connections(plugs=True, source=False) or []
        except Exception:
            pass

        cc_cache[attr_name] = {
            "cc_node": h_node,
            "cc_node_name": h_node.name(),
            "cc_out_dests": cc_out_dests,
            "params": params,
            "input_plug": input_plug,
            "output_plug": conn.get("plug"),
        }

    def transfer(self, cc_entry, target_plug, target_renderer, log):
        cc_config = self.config.get_color_correction_config(target_renderer)
        if not cc_config or not cc_config.node_type:
            input_plug = cc_entry.get("input_plug")
            if input_plug:
                self.utils.smart_connect(input_plug, target_plug)
            return

        src_cc_name = cc_entry.get("cc_node_name", "")
        if src_cc_name and src_cc_name in self._converted:
            cc_node = self._converted[src_cc_name]
        else:
            renderer_map = {"arnold": "ai", "redshift": "rs", "vray": "vray"}
            renderer_short = renderer_map.get(target_renderer, target_renderer)
            base_name = src_cc_name + "_" + renderer_short if src_cc_name else None
            cc_node = self.utils.create_cc_node(cc_config, base_name)
            self.utils.set_cc_params(cc_node, cc_entry["params"], cc_config)

            input_plug = cc_entry.get("input_plug")
            if input_plug and cc_config.source_connection:
                self.utils.smart_connect(input_plug, cc_node.attr(cc_config.source_connection))

            if src_cc_name:
                self._converted[src_cc_name] = cc_node

        cc_out_dests = cc_entry.get("cc_out_dests", [])
        cc_out_dests = [d for d in cc_out_dests if not self.config.get_material_config(pm.nodeType(d.node()))]
        if cc_out_dests:
            for dest in cc_out_dests:
                try:
                    cc_node.attr(cc_config.target_connection) >> dest
                except Exception:
                    pm.warning(f"CCConverter: failed to connect {cc_node.name()} to {dest}")
        else:
            try:
                cc_node.attr(cc_config.target_connection) >> target_plug
            except Exception:
                pm.warning(f"CCConverter: failed to connect {cc_node.name()} to {target_plug}")

        log.append(f"  Color correction converted: {cc_node.name()}")
