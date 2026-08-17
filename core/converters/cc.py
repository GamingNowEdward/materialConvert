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
            self._restore_shared_source_chain(cc_entry)
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

    def _restore_shared_source_chain(self, cc_entry):
        """原 CC 被新 CC 挤出后,若中间节点与源材质共享,把源材质属性改接回原 CC,避免源链被污染。"""
        src_cc_name = cc_entry.get("cc_node_name", "")
        output_plug = cc_entry.get("output_plug")
        if not src_cc_name or not output_plug:
            return

        src_renderer = self.config.identify_cc_renderer(cmds.nodeType(src_cc_name))
        if not src_renderer:
            return
        src_cfg = self.config.get_color_correction_config(src_renderer)
        if not src_cfg or not src_cfg.target_connection:
            return

        cc_out_nodes = {d.split(".")[0] for d in cc_entry.get("cc_out_dests", [])}
        for dest_plug in (cmds.listConnections(output_plug, plugs=True, destination=True) or []):
            dest_node = dest_plug.split(".")[0]
            if dest_node in cc_out_nodes:
                continue
            if self.config.get_material_config(cmds.nodeType(dest_node)):
                try:
                    cmds.connectAttr(f"{src_cc_name}.{src_cfg.target_connection}", dest_plug, force=True)
                except Exception:
                    cmds.warning(f"CCConverter: failed to restore source chain to {dest_plug}")
