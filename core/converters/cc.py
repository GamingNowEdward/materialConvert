import maya.cmds as cmds

from core.node_utils import RENDERER_SHORT


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
                    cc_node_type = cmds.nodeType(node)
                    src_cc_renderer = self.config.identify_cc_renderer(cc_node_type)
                    if src_cc_renderer:
                        self._cache(cc_cache, attr_name, node, src_cc_renderer, conn)
                    else:
                        history = cmds.listHistory(node, future=False, pdo=True) or []
                        for h_name in history:
                            if h_name == node:
                                continue
                            cc_node_type = cmds.nodeType(h_name)
                            src_cc_renderer = self.config.identify_cc_renderer(cc_node_type)
                            if src_cc_renderer:
                                self._cache(cc_cache, attr_name, h_name, src_cc_renderer, conn)
                                break
        return cc_cache

    def _cache(self, cc_cache, attr_name, h_node, src_cc_renderer, conn):
        cc_config = self.config.get_color_correction_config(src_cc_renderer)
        params, input_plug = self.utils.collect_cc_chain_params(h_node, cc_config)

        cc_out_dests = []
        try:
            cc_out_dests = cmds.listConnections(f"{h_node}.{cc_config.target_connection}",
                                                plugs=True, source=False) or []
        except Exception:
            pass

        cc_cache[attr_name] = {
            "cc_node": h_node,
            "cc_node_name": h_node,
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
            renderer_short = RENDERER_SHORT.get(target_renderer, target_renderer)
            base_name = src_cc_name + "_" + renderer_short if src_cc_name else None
            cc_node = self.utils.create_cc_node(cc_config, base_name)
            self.utils.set_cc_params(cc_node, cc_entry["params"], cc_config)

            input_plug = cc_entry.get("input_plug")
            if input_plug and cc_config.source_connection:
                self.utils.smart_connect(input_plug, f"{cc_node}.{cc_config.source_connection}")

            if src_cc_name:
                self._converted[src_cc_name] = cc_node

        cc_out_dests = cc_entry.get("cc_out_dests", [])
        cc_out_dests = [d for d in cc_out_dests if not self.config.get_material_config(cmds.nodeType(d.split(".")[0]))]
        if cc_out_dests:
            for dest in cc_out_dests:
                try:
                    cmds.connectAttr(f"{cc_node}.{cc_config.target_connection}", dest, force=True)
                except Exception:
                    cmds.warning(f"CCConverter: failed to connect {cc_node} to {dest}")
        else:
            try:
                cmds.connectAttr(f"{cc_node}.{cc_config.target_connection}", target_plug, force=True)
            except Exception:
                cmds.warning(f"CCConverter: failed to connect {cc_node} to {target_plug}")

        log.append(f"  Color correction converted: {cc_node}")
