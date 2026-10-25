import maya.cmds as cmds

from core.logger import get_logger
from core.node_utils import RENDERER_SHORT
from core.results import TransferOutcome

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
                self.log.warn(f"Failed to identify node type for {node}: {exc}", source=_SOURCE, nodes=(node,))
                continue

            src_cc_renderer = self.config.identify_cc_renderer(cc_node_type)
            if src_cc_renderer:
                self.log.debug(f"{attr_name}: direct CC node {node} ({src_cc_renderer})", source=_SOURCE, nodes=(node,))
                self._cache(cc_cache, attr_name, node, src_cc_renderer, conn)
                continue

            try:
                history = cmds.listHistory(node, future=False, pdo=True) or []
            except Exception as exc:
                self.log.warn(f"Failed to query history for {node}: {exc}", source=_SOURCE, nodes=(node,))
                continue

            for h_name in history:
                if h_name == node:
                    continue
                try:
                    h_type = cmds.nodeType(h_name)
                except Exception as exc:
                    self.log.warn(f"Failed to identify history node {h_name}: {exc}", source=_SOURCE, nodes=(h_name,))
                    continue
                src_cc_renderer = self.config.identify_cc_renderer(h_type)
                if src_cc_renderer:
                    self.log.debug(
                        f"{attr_name}: found CC node {h_name} in history of {node}",
                        source=_SOURCE,
                        nodes=(h_name, node),
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

        output_plug = conn.get("plug")
        # The material attribute may be driven by a non-default CC output slot
        # (e.g. ``outAlpha`` for a scalar channel).  Remember it so the target
        # chain is wired to the same slot instead of always using the configured
        # one, which cannot connect to a float attribute.
        source_output_attr = None
        if output_plug:
            holder, _, attr = output_plug.partition(".")
            if holder == h_node and attr:
                source_output_attr = attr

        cc_out_dests = self._list_cc_destinations(h_node, cc_config.output, source_output_attr)

        cc_cache[attr_name] = {
            "cc_node": h_node,
            "cc_node_name": h_node,
            "cc_out_dests": cc_out_dests,
            "params": params,
            "input_plug": input_plug,
            "output_plug": output_plug,
            "source_output_attr": source_output_attr,
        }

    def _list_cc_destinations(self, h_node, output_attr, source_output_attr):
        """Downstream plugs of the CC.

        Covers both the configured output attribute and the slot the material
        actually read: they can differ (``outColor`` vs ``outAlpha``), and the
        real downstream lives on the latter for scalar channels.
        """
        attrs = []
        for attr in (output_attr, source_output_attr):
            if attr and attr not in attrs:
                attrs.append(attr)

        dests = []
        for attr in attrs:
            try:
                found = cmds.listConnections(f"{h_node}.{attr}", plugs=True, source=False) or []
            except Exception as exc:
                self.log.warn(
                    f"Failed to list CC destinations on {h_node}.{attr}: {exc}",
                    source=_SOURCE,
                    nodes=(h_node,),
                )
                continue
            for plug in found:
                if plug not in dests:
                    dests.append(plug)
        return dests

    def transfer(self, cc_entry, target_plug, target_renderer):
        """Convert one CC chain without mutating the source network.

        Returns a :class:`core.results.TransferOutcome`.  Three topologies are
        distinguished:

        * ``direct``      -- the source CC feeds the material attribute itself;
          the original "shared CC" handling applies (the source material gets its
          old CC back, other downstream nodes follow the new CC).
        * ``single_hop``  -- the source CC feeds an intermediate node
          (layeredTexture / ramp / ...) which feeds the material attribute.  The
          intermediate node is **copied**, the copy is fed by the new CC and the
          material attribute is connected to the copy.  The source sub-graph is
          never rewritten.
        * ``unsupported`` -- deeper or ambiguous chains.  Reported as an explicit
          limitation (``unsupported``) instead of silently bypassing the lost
          intermediate processing or polluting the source material.
        """
        outcome = TransferOutcome()
        cc_config = self.config.get_color_correction_config(target_renderer)
        if not cc_config or not cc_config.node_type:
            input_plug = cc_entry.get("input_plug")
            self.log.info(
                f"Target renderer {target_renderer} has no CC node config; "
                f"connecting raw input {input_plug} -> {target_plug}",
                source=_SOURCE,
            )
            if input_plug:
                outcome.ok = bool(self.utils.smart_connect(input_plug, target_plug, logger=self.log))
            else:
                outcome.ok = False
                outcome.critical.append(
                    f"no CC input to fall back to for {target_plug}")
            return outcome

        topology, plan = self._plan_topology(cc_entry)
        if topology == "unsupported":
            reason = plan.get("reason", "unsupported CC chain")
            self.log.warn(
                f"Color correction not converted for {cc_entry.get('cc_node', '')}: {reason}; "
                f"the source network is left untouched",
                source=_SOURCE,
                nodes=tuple(n for n in (cc_entry.get("cc_node"),) if n),
            )
            outcome.unsupported.append(reason)
            return outcome

        src_cc_name = cc_entry.get("cc_node_name", "")
        if src_cc_name and src_cc_name in self._converted:
            cc_node = self._converted[src_cc_name]
            self.log.debug(f"Reusing converted CC node {cc_node} for {src_cc_name}", source=_SOURCE, nodes=(cc_node,))
        else:
            renderer_short = RENDERER_SHORT.get(target_renderer, target_renderer)
            base_name = src_cc_name + "_" + renderer_short if src_cc_name else None
            cc_node = self.utils.create_cc_node(cc_config, base_name, logger=self.log)
            self.utils.set_cc_params(cc_node, cc_entry["params"], cc_config, logger=self.log)

            input_plug = cc_entry.get("input_plug")
            if input_plug and cc_config.input:
                if not self.utils.smart_connect(input_plug, f"{cc_node}.{cc_config.input}", logger=self.log):
                    outcome.ok = False
                    outcome.critical.append(
                        f"failed to connect CC input {input_plug} -> {cc_node}.{cc_config.input}")
                    self.log.warn(
                        f"Failed to connect CC input {input_plug} -> {cc_node}.{cc_config.input}",
                        source=_SOURCE,
                        nodes=(cc_node, self.utils.node_name_from_plug(input_plug)),
                    )

            if src_cc_name:
                self._converted[src_cc_name] = cc_node
            self.log.debug(f"Created target CC node {cc_node}", source=_SOURCE, nodes=(cc_node,))

        if not outcome.ok:
            return outcome

        if topology == "single_hop":
            if not self._transfer_via_clone(cc_node, cc_config, target_plug, plan, outcome):
                return outcome
            self.log.info(
                f"Color correction converted through copied intermediate node: {cc_node}",
                source=_SOURCE, nodes=(cc_node, plan.get("mid")),
            )
            return outcome

        cc_out_dests = self._external_cc_destinations(cc_entry)
        if cc_out_dests:
            self._restore_shared_source_chain(cc_entry)
            for dest in cc_out_dests:
                if dest == target_plug:
                    # The material channel is wired explicitly below; never let
                    # the external downstream list decide it.
                    continue
                if self._connect_output(cc_node, dest, cc_config, cc_entry, outcome):
                    self.log.debug(f"Connected CC {cc_node} -> {dest}", source=_SOURCE, nodes=(cc_node, dest))

        # The target material channel is always wired on its own: it belongs to
        # the newly created material and is never part of the source CC's
        # downstream list, so no other branch can reach it.
        if self._connect_output(cc_node, target_plug, cc_config, cc_entry, outcome):
            self.log.debug(f"Connected CC {cc_node} -> {target_plug}", source=_SOURCE, nodes=(cc_node, self.utils.node_name_from_plug(target_plug)))

        if outcome.ok:
            self.log.info(f"Color correction converted: {cc_node}", source=_SOURCE, nodes=(cc_node,))
        else:
            self.log.warn(f"Color correction conversion incomplete: {cc_node}", source=_SOURCE, nodes=(cc_node,))
        return outcome

    def _connect_output(self, cc_node, dest_plug, cc_config, cc_entry, outcome):
        """Connect the new CC output to *dest_plug*.

        Prefers the output slot the source chain actually used (e.g. ``outAlpha``
        for a scalar channel) and falls back through :func:`smart_connect`
        (``outColor`` -> ``outAlpha``), so a CC driving a float attribute no
        longer fails on the float3 ``outColor``.
        """
        source_attr = cc_entry.get("source_output_attr")
        src_plug = f"{cc_node}.{source_attr}" if source_attr else f"{cc_node}.{cc_config.output}"
        if self.utils.smart_connect(src_plug, dest_plug, logger=self.log):
            return True
        message = f"failed to connect CC {cc_node} -> {dest_plug}"
        outcome.ok = False
        outcome.critical.append(message)
        self.log.warn(message, source=_SOURCE,
                      nodes=(cc_node, self.utils.node_name_from_plug(dest_plug)))
        return False

    def _plan_topology(self, cc_entry):
        """``(topology, plan)`` for the chain between the source CC and its consumer.

        ``direct`` has no plan; ``single_hop`` carries the intermediate node, the
        CC input slots on it and the output attribute the material reads;
        ``unsupported`` carries a human-readable reason.
        """
        output_plug = cc_entry.get("output_plug")
        src_cc_name = cc_entry.get("cc_node_name")
        if not output_plug or not src_cc_name:
            return "direct", {}

        holder = output_plug.split(".", 1)[0]
        if holder == src_cc_name:
            return "direct", {}

        # The intermediate node must be fed *directly* by the source CC: check the
        # CC output slots recorded when the chain was collected (the material
        # attribute's upstream plug itself has no upstream of its own).
        mid_dests = [d for d in cc_entry.get("cc_out_dests", [])
                     if d.split(".", 1)[0] == holder]
        if not mid_dests:
            return "unsupported", {
                "reason": f"multi-hop CC chain through {holder}",
            }

        for dest in mid_dests:
            try:
                upstream = cmds.listConnections(
                    dest, source=True, destination=False, plugs=True) or []
            except Exception as exc:
                self.log.warn(
                    f"Failed to trace upstream of {dest}: {exc}",
                    source=_SOURCE, nodes=(holder,),
                )
                return "unsupported", {"reason": f"could not trace upstream of {dest}"}
            if len(upstream) != 1 or upstream[0].split(".", 1)[0] != src_cc_name:
                return "unsupported", {
                    "reason": f"multi-hop CC chain through {holder}",
                }

        return "single_hop", {
            "mid": holder,
            "dests": mid_dests,
            "attr": output_plug.split(".", 1)[1],
        }

    def _transfer_via_clone(self, cc_node, cc_config, target_plug, plan, outcome):
        """Copy the intermediate node and split the new CC into the copy."""
        mid = plan["mid"]
        try:
            clones = cmds.duplicate(mid, upstreamNodes=False, name=mid + "_conv") or []
        except Exception as exc:
            outcome.ok = False
            outcome.critical.append(f"failed to copy intermediate node {mid}: {exc}")
            self.log.warn(f"Failed to copy {mid}: {exc}", source=_SOURCE, nodes=(mid,))
            return False
        if not clones:
            outcome.ok = False
            outcome.critical.append(f"failed to copy intermediate node {mid}: no node created")
            self.log.warn(f"Duplicating {mid} returned no node", source=_SOURCE, nodes=(mid,))
            return False

        clone = clones[0]
        self._disconnect_upstream(clone)

        for dest in plan["dests"]:
            suffix = dest.split(".", 1)[1]
            try:
                cmds.connectAttr(f"{cc_node}.{cc_config.output}", f"{clone}.{suffix}", force=True)
                self.log.debug(f"Connected CC {cc_node} -> {clone}.{suffix}", source=_SOURCE, nodes=(cc_node, clone))
            except Exception as exc:
                outcome.ok = False
                outcome.critical.append(
                    f"failed to connect CC {cc_node} -> {clone}.{suffix}: {exc}")
                self.log.warn(
                    f"Failed to connect CC {cc_node} -> {clone}.{suffix}: {exc}",
                    source=_SOURCE, nodes=(cc_node, clone),
                )

        try:
            cmds.connectAttr(f"{clone}.{plan['attr']}", target_plug, force=True)
            self.log.debug(f"Connected copied chain {clone}.{plan['attr']} -> {target_plug}",
                           source=_SOURCE, nodes=(clone, self.utils.node_name_from_plug(target_plug)))
        except Exception as exc:
            outcome.ok = False
            outcome.critical.append(f"failed to connect {clone}.{plan['attr']} -> {target_plug}: {exc}")
            self.log.warn(
                f"Failed to connect {clone}.{plan['attr']} -> {target_plug}: {exc}",
                source=_SOURCE, nodes=(clone, self.utils.node_name_from_plug(target_plug)),
            )
        return outcome.ok

    def _disconnect_upstream(self, node):
        """Drop the connections a duplicated node inherited from the source graph."""
        try:
            pairs = cmds.listConnections(
                node, source=True, destination=False, plugs=True,
                connections=True) or []
        except Exception as exc:
            self.log.warn(f"Failed to inspect {node} inputs: {exc}",
                          source=_SOURCE, nodes=(node,))
            return
        for index in range(0, len(pairs) - 1, 2):
            first, second = pairs[index], pairs[index + 1]
            # ``listConnections -connections`` returns pairs whose order is not
            # documented as stable; pick the plug that belongs to the copy.
            if first.split(".", 1)[0] == node:
                dest_plug, src_plug = first, second
            elif second.split(".", 1)[0] == node:
                dest_plug, src_plug = second, first
            else:
                continue
            try:
                # disconnectAttr takes (source, destination): the plug that
                # belongs to the copy is the *destination*.
                cmds.disconnectAttr(src_plug, dest_plug)
                self.log.debug(f"Detached copied node input {dest_plug} <- {src_plug}",
                               source=_SOURCE, nodes=(node,))
            except Exception as exc:
                self.log.warn(
                    f"Failed to detach {dest_plug} <- {src_plug}: {exc}",
                    source=_SOURCE, nodes=(node,),
                )

    def _external_cc_destinations(self, cc_entry):
        """Source CC outputs that belong to non-material nodes (direct topology)."""
        filtered = []
        for dest in cc_entry.get("cc_out_dests", []):
            try:
                dest_node = dest.split(".")[0]
                dest_type = cmds.nodeType(dest_node)
            except Exception as exc:
                self.log.warn(f"Failed to identify CC destination {dest}: {exc}",
                              source=_SOURCE, nodes=(dest.split(".")[0],))
                filtered.append(dest)
                continue
            if self.config.get_material_config(dest_type):
                self.log.debug(f"Excluding material CC destination {dest}", source=_SOURCE, nodes=(dest_node,))
            else:
                filtered.append(dest)
        return filtered

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
            self.log.warn(f"Failed to identify source CC node {src_cc_name}: {exc}", source=_SOURCE, nodes=(src_cc_name,))
            return

        src_renderer = self.config.identify_cc_renderer(src_node_type)
        if not src_renderer:
            self.log.warn(f"Source CC node {src_cc_name} is not a known CC type", source=_SOURCE, nodes=(src_cc_name,))
            return
        src_cfg = self.config.get_color_correction_config(src_renderer)
        if not src_cfg or not src_cfg.output:
            self.log.warn(f"No source CC config for {src_cc_name}", source=_SOURCE, nodes=(src_cc_name,))
            return

        cc_out_nodes = {d.split(".")[0] for d in cc_entry.get("cc_out_dests", [])}
        try:
            # ``output_plug`` is the source CC's output slot, so only its
            # destinations are relevant; ``source=False`` states that intent
            # explicitly (the slot has no upstream, so this changes nothing
            # today but removes a latent trap).
            dest_plugs = cmds.listConnections(output_plug, plugs=True,
                                              destination=True, source=False) or []
        except Exception as exc:
            self.log.warn(f"Failed to list destinations for {output_plug}: {exc}", source=_SOURCE, nodes=(self.utils.node_name_from_plug(output_plug),))
            return

        for dest_plug in dest_plugs:
            dest_node = dest_plug.split(".")[0]
            if dest_node in cc_out_nodes:
                continue
            try:
                dest_type = cmds.nodeType(dest_node)
            except Exception as exc:
                self.log.warn(f"Failed to identify destination node {dest_node}: {exc}", source=_SOURCE, nodes=(dest_node,))
                continue
            if self.config.get_material_config(dest_type):
                try:
                    cmds.connectAttr(f"{src_cc_name}.{src_cfg.output}", dest_plug, force=True)
                    self.log.info(f"Restored source CC chain to {dest_plug}", source=_SOURCE, nodes=(src_cc_name, dest_node))
                except Exception as exc:
                    self.log.warn(f"Failed to restore source chain to {dest_plug}: {exc}", source=_SOURCE, nodes=(src_cc_name, dest_node))
