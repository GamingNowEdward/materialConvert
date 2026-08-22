import maya.cmds as cmds

from core.logger import get_logger
from core.node_utils import RENDERER_SHORT

_SOURCE = "CCConverter"


class CCConverter:

    def __init__(self, config, utils, logger=None):
        self.config = config
        self.utils = utils
        self.log = logger or get_logger()
        self._converted = {}

    def reset(self):
        self.log.debug("CC conversion cache reset", source=_SOURCE)
        self._converted.clear()

    def collect_chains(self, attr_info):
        cc_cache = {}
        for attr_name, data in attr_info.items():
            conn = data.get("connection")
            if not conn:
                continue
            node = conn.get("node")
            if not node:
                continue

            try:
                cc_node_type = cmds.nodeType(node)
            except Exception as exc:
                self.log.warn(f"Failed to identify node type for {node}: {exc}", source=_SOURCE)
                continue

            src_cc_renderer = self.config.identify_cc_renderer(cc_node_type)
            if src_cc_renderer:
                self.log.debug(f"{attr_name}: direct CC node {node} ({src_cc_renderer})", source=_SOURCE)
                self._cache(cc_cache, attr_name, node, src_cc_renderer, conn)
                continue

            try:
                history = cmds.listHistory(node, future=False, pdo=True) or []
            except Exception as exc:
                self.log.warn(f"Failed to query history for {node}: {exc}", source=_SOURCE)
                continue

            for h_name in history:
                if h_name == node:
                    continue
                try:
                    h_type = cmds.nodeType(h_name)
                except Exception as exc:
                    self.log.warn(f"Failed to identify history node {h_name}: {exc}", source=_SOURCE)
                    continue
                src_cc_renderer = self.config.identify_cc_renderer(h_type)
                if src_cc_renderer:
                    self.log.debug(
                        f"{attr_name}: found CC node {h_name} in history of {node}",
                        source=_SOURCE,
                    )
                    self._cache(cc_cache, attr_name, h_name, src_cc_renderer, conn)
                    break

        self.log.info(f"CC chain collection found {len(cc_cache)} convertible chain(s)", source=_SOURCE)
        return cc_cache

    def _cache(self, cc_cache, attr_name, h_node, src_cc_renderer, conn):
        cc_config = self.config.get_color_correction_config(src_cc_renderer)
        if not cc_config:
            self.log.warn(f"No CC config for renderer {src_cc_renderer}", source=_SOURCE)
            return

        params, input_plug = self.utils.collect_cc_chain_params(h_node, cc_config, logger=self.log)

        cc_out_dests = []
        try:
            cc_out_dests = cmds.listConnections(f"{h_node}.{cc_config.target_connection}",
                                                plugs=True, source=False) or []
        except Exception as exc:
            self.log.warn(
                f"Failed to list CC destinations on {h_node}.{cc_config.target_connection}: {exc}",
                source=_SOURCE,
            )

        cc_cache[attr_name] = {
            "cc_node": h_node,
            "cc_node_name": h_node,
            "cc_out_dests": cc_out_dests,
            "params": params,
            "input_plug": input_plug,
            "output_plug": conn.get("plug"),
        }

    def transfer(self, cc_entry, target_plug, target_renderer):
        cc_config = self.config.get_color_correction_config(target_renderer)
        if not cc_config or not cc_config.node_type:
            input_plug = cc_entry.get("input_plug")
            self.log.info(
                f"Target renderer {target_renderer} has no CC node config; "
                f"connecting raw input {input_plug} -> {target_plug}",
                source=_SOURCE,
            )
            if input_plug:
                self.utils.smart_connect(input_plug, target_plug, logger=self.log)
            return

        src_cc_name = cc_entry.get("cc_node_name", "")
        if src_cc_name and src_cc_name in self._converted:
            cc_node = self._converted[src_cc_name]
            self.log.debug(f"Reusing converted CC node {cc_node} for {src_cc_name}", source=_SOURCE)
        else:
            renderer_short = RENDERER_SHORT.get(target_renderer, target_renderer)
            base_name = src_cc_name + "_" + renderer_short if src_cc_name else None
            cc_node = self.utils.create_cc_node(cc_config, base_name)
            self.utils.set_cc_params(cc_node, cc_entry["params"], cc_config, logger=self.log)

            input_plug = cc_entry.get("input_plug")
            if input_plug and cc_config.source_connection:
                if not self.utils.smart_connect(input_plug, f"{cc_node}.{cc_config.source_connection}", logger=self.log):
                    self.log.warn(
                        f"Failed to connect CC input {input_plug} -> {cc_node}.{cc_config.source_connection}",
                        source=_SOURCE,
                    )

            if src_cc_name:
                self._converted[src_cc_name] = cc_node
            self.log.debug(f"Created target CC node {cc_node}", source=_SOURCE)

        cc_out_dests = cc_entry.get("cc_out_dests", [])
        filtered = []
        for dest in cc_out_dests:
            try:
                dest_node = dest.split(".")[0]
                dest_type = cmds.nodeType(dest_node)
            except Exception as exc:
                self.log.warn(f"Failed to identify CC destination {dest}: {exc}", source=_SOURCE)
                filtered.append(dest)
                continue
            if self.config.get_material_config(dest_type):
                self.log.debug(f"Excluding material CC destination {dest}", source=_SOURCE)
            else:
                filtered.append(dest)
        cc_out_dests = filtered

        if cc_out_dests:
            self._restore_shared_source_chain(cc_entry)
            for dest in cc_out_dests:
                try:
                    cmds.connectAttr(f"{cc_node}.{cc_config.target_connection}", dest, force=True)
                    self.log.debug(f"Connected CC {cc_node} -> {dest}", source=_SOURCE)
                except Exception as exc:
                    self.log.warn(f"Failed to connect CC {cc_node} -> {dest}: {exc}", source=_SOURCE)
        else:
            try:
                cmds.connectAttr(f"{cc_node}.{cc_config.target_connection}", target_plug, force=True)
                self.log.debug(f"Connected CC {cc_node} -> {target_plug}", source=_SOURCE)
            except Exception as exc:
                self.log.warn(f"Failed to connect CC {cc_node} -> {target_plug}: {exc}", source=_SOURCE)

        self.log.info(f"Color correction converted: {cc_node}", source=_SOURCE)

    def _restore_shared_source_chain(self, cc_entry):
        """After the original CC is displaced by a new CC, if the intermediate node is
        shared with the source material, re-route the source material attribute back to
        the original CC to avoid polluting the source chain."""
        src_cc_name = cc_entry.get("cc_node_name", "")
        output_plug = cc_entry.get("output_plug")
        if not src_cc_name or not output_plug:
            return

        try:
            src_node_type = cmds.nodeType(src_cc_name)
        except Exception as exc:
            self.log.warn(f"Failed to identify source CC node {src_cc_name}: {exc}", source=_SOURCE)
            return

        src_renderer = self.config.identify_cc_renderer(src_node_type)
        if not src_renderer:
            self.log.warn(f"Source CC node {src_cc_name} is not a known CC type", source=_SOURCE)
            return
        src_cfg = self.config.get_color_correction_config(src_renderer)
        if not src_cfg or not src_cfg.target_connection:
            self.log.warn(f"No source CC config for {src_cc_name}", source=_SOURCE)
            return

        cc_out_nodes = {d.split(".")[0] for d in cc_entry.get("cc_out_dests", [])}
        try:
            dest_plugs = cmds.listConnections(output_plug, plugs=True, destination=True) or []
        except Exception as exc:
            self.log.warn(f"Failed to list destinations for {output_plug}: {exc}", source=_SOURCE)
            return

        for dest_plug in dest_plugs:
            dest_node = dest_plug.split(".")[0]
            if dest_node in cc_out_nodes:
                continue
            try:
                dest_type = cmds.nodeType(dest_node)
            except Exception as exc:
                self.log.warn(f"Failed to identify destination node {dest_node}: {exc}", source=_SOURCE)
                continue
            if self.config.get_material_config(dest_type):
                try:
                    cmds.connectAttr(f"{src_cc_name}.{src_cfg.target_connection}", dest_plug, force=True)
                    self.log.info(f"Restored source CC chain to {dest_plug}", source=_SOURCE)
                except Exception as exc:
                    self.log.warn(f"Failed to restore source chain to {dest_plug}: {exc}", source=_SOURCE)
