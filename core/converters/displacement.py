import maya.cmds as cmds

from dataclasses import dataclass, field

from core.logger import get_logger
from core.node_utils import RENDERER_SHORT
from core.results import TransferOutcome

_SOURCE = "DisplacementConverter"

#: Generic output attributes tried after the configured one (Redshift
#: ``RedshiftDisplacement`` exposes ``out``, native nodes ``outDisplacement``).
_OUTPUT_FALLBACKS = ("outDisplacement", "out", "outColor")


@dataclass
class DisplacementPlan:
    """Nodes prepared for one material, not yet committed to any shading engine.

    Splitting preparation from commit is what makes the shading-engine part of a
    conversion transactional: nothing in the scene changes until every prepared
    node exists with a usable output and a valid texture input.  ``entries`` holds
    ``{"sg", "node", "output"}`` records for the commit pass.
    """

    ok: bool = True
    entries: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    critical: list = field(default_factory=list)
    skipped: int = 0

    def __bool__(self):
        return bool(self.ok)


class DisplacementConverter:

    def __init__(self, config, utils, logger=None):
        self.config = config
        self.utils = utils
        self.log = logger or get_logger()

    def convert(self, source_mat, target_mat, source_config, target_config,
                target_renderer, sgs=None):
        """Convert displacement for every shading engine fed by *source_mat*.

        Convenience entry point for tests / single-SG callers.  It does **not**
        participate in the shading-engine transaction (no snapshot/rollback);
        the production path uses :meth:`prepare` + :meth:`apply` through
        ``MaterialConverter`` so displacement commits with the surface as one
        transaction.

        Displacement lives on the shading engine, so a material bound to several
        SGs must be converted per SG.  SGs that share the same source
        displacement (same texture plug + scale) reuse a single target
        displacement node instead of duplicating networks.

        Returns a :class:`core.results.TransferOutcome`: ``ok`` False when a node
        could not be created/connected or a source plug could not be read;
        ``issues`` carries non-critical degradation (e.g. a scale value that
        could not be written).
        """
        plan = self.prepare(source_mat, target_mat, source_config, target_config,
                            target_renderer, sgs)
        if not plan.ok:
            return TransferOutcome(
                ok=False, issues=list(plan.issues), critical=list(plan.critical))

        failures = self.apply(plan)
        outcome = TransferOutcome(ok=not failures, issues=list(plan.issues))
        outcome.critical.extend(item["reason"] for item in failures)
        return outcome

    def prepare(self, source_mat, target_mat, source_config, target_config,
                target_renderer, sgs=None):
        """Create and validate displacement nodes without touching any SG."""
        plan = DisplacementPlan()
        sgs = list(sgs or [])
        if not sgs:
            self.log.skip(f"No shading engine found for {source_mat}; displacement skipped",
                          source=_SOURCE, nodes=(source_mat,))
            return plan

        disp_type = target_config.displacement_node_type
        disp_in = target_config.displacement_texture
        if not disp_type or not disp_in:
            self.log.skip("Target material has no displacement configuration", source=_SOURCE)
            return plan

        is_real_type = disp_type not in ("", "displacementShader")
        if not is_real_type and source_config.displacement_node_type == "displacementShader":
            self.log.skip("Source and target both use native displacementShader; nothing to convert",
                          source=_SOURCE)
            return plan

        renderer_short = RENDERER_SHORT.get(target_renderer, target_renderer)
        disp_by_source = {}
        converted = 0
        skipped = 0
        failed = 0

        for sg in sgs:
            data, read_ok = self._collect(source_mat, sg, source_config)
            if not read_ok:
                failed += 1
                plan.ok = False
                plan.critical.append(
                    f"{sg}: failed to read source displacement data; "
                    f"refusing to create a partial node")
                continue
            if not data:
                self.log.skip(f"No source displacement data for {source_mat} on {sg}",
                              source=_SOURCE, nodes=(source_mat, sg))
                skipped += 1
                continue

            plan.issues.extend(data.get("issues", []))

            if not data.get("texture_plug"):
                # A source displacement node without a texture has no faithful
                # target counterpart: creating an empty displacement node and
                # binding it to the SG would silently drop the original network.
                self.log.skip(
                    f"Source displacement on {sg} has no texture input; skipped",
                    source=_SOURCE, nodes=(source_mat, sg))
                skipped += 1
                continue

            key = (data.get("texture_plug"), data.get("scale"))
            entry = disp_by_source.get(key)
            if entry is None:
                base_name = f"{source_mat}_{renderer_short}Disp"
                node, node_issues, critical_reason = self._create_node(
                    disp_type, disp_in, target_config.displacement_scale,
                    base_name, data, source_mat,
                )
                plan.issues.extend(node_issues)
                if critical_reason:
                    failed += 1
                    plan.ok = False
                    plan.critical.append(f"{sg}: {critical_reason}")
                    continue

                output = self._pick_output(node, target_config.displacement_output)
                if not output:
                    failed += 1
                    plan.ok = False
                    plan.critical.append(
                        f"{sg}: no usable displacement output attribute found on {node}")
                    continue

                entry = {"node": node, "output": output}
                disp_by_source[key] = entry

            plan.entries.append({"sg": sg, "node": entry["node"], "output": entry["output"]})
            converted += 1

        plan.skipped = skipped
        self.log.info(
            f"Displacement prepared for {source_mat}: {converted} shading engine(s) "
            f"ready, {skipped} skipped, {failed} failed",
            source=_SOURCE,
            nodes=(source_mat,),
        )
        return plan

    def apply(self, plan):
        """Commit a prepared plan; returns a list of ``{"sg", "reason"}`` failures."""
        failures = []
        for entry in plan.entries:
            sg = entry["sg"]
            node = entry["node"]
            attr = entry["output"]
            try:
                cmds.connectAttr(f"{node}.{attr}", f"{sg}.displacementShader", force=True)
                self.log.info(
                    f"Connected displacement {node}.{attr} -> {sg}.displacementShader",
                    source=_SOURCE,
                    nodes=(node, sg),
                )
            except Exception as exc:
                reason = f"failed to connect {node}.{attr} -> {sg}.displacementShader: {exc}"
                self.log.error(reason, source=_SOURCE, nodes=(node, sg))
                failures.append({"sg": sg, "reason": reason})
        return failures

    def _create_node(self, disp_type, disp_in, disp_scale, base_name, src_disp_data, source_mat):
        """Create one displacement node.

        Returns ``(node | None, issues, critical_reason)``.  ``node`` is None when
        the node could not be created or its texture input could not be
        connected; created nodes are never deleted (project rule), the caller
        simply refuses to commit them.
        """
        try:
            disp_node = cmds.shadingNode(disp_type, asUtility=True, name=base_name)
        except Exception as exc:
            self.log.error(f"Failed to create {disp_type}: {exc}", source=_SOURCE, nodes=(source_mat,))
            return None, [], f"failed to create {disp_type}: {exc}"
        self.log.debug(f"Created displacement node {disp_node}", source=_SOURCE, nodes=(disp_node,))

        issues = []
        texture_plug = src_disp_data.get("texture_plug")
        if texture_plug and disp_in:
            if self.utils.smart_connect(texture_plug, f"{disp_node}.{disp_in}", logger=self.log):
                self.log.debug(
                    f"Connected displacement texture {texture_plug} -> {disp_node}.{disp_in}",
                    source=_SOURCE,
                    nodes=(self.utils.node_name_from_plug(texture_plug), disp_node),
                )
            else:
                reason = f"failed to connect displacement texture {texture_plug} -> {disp_node}.{disp_in}"
                self.log.error(
                    reason,
                    source=_SOURCE,
                    nodes=(self.utils.node_name_from_plug(texture_plug), disp_node),
                )
                return None, issues, reason

        scale_val = src_disp_data.get("scale")
        if disp_scale and scale_val is not None:
            try:
                cmds.setAttr(f"{disp_node}.{disp_scale}", scale_val)
                self.log.debug(f"Set {disp_node}.{disp_scale} = {scale_val!r}", source=_SOURCE, nodes=(disp_node,))
            except Exception as exc:
                # Non-critical: the node and its texture are valid, only the
                # strength falls back to the node default.
                issues.append(f"{disp_node}: displacement scale not set ({exc})")
                self.log.warn(f"Failed to set displacement scale on {disp_node}: {exc}", source=_SOURCE, nodes=(disp_node,))
        return disp_node, issues, ""

    def _pick_output(self, disp_node, configured_attr):
        """First existing output attribute of *disp_node*, configured one first."""
        attempts = []
        if configured_attr:
            attempts.append(configured_attr)
        for fallback in _OUTPUT_FALLBACKS:
            if fallback not in attempts:
                attempts.append(fallback)

        for attr in attempts:
            try:
                if cmds.objExists(f"{disp_node}.{attr}"):
                    return attr
            except Exception as exc:
                self.log.warn(
                    f"Failed to query output {disp_node}.{attr}: {exc}",
                    source=_SOURCE, nodes=(disp_node,),
                )
        self.log.warn(f"No usable displacement output attribute found on {disp_node}",
                      source=_SOURCE, nodes=(disp_node,))
        return None

    def _collect(self, source_mat, sg, source_config):
        """Source displacement for one SG as ``(data | None, ok)``.

        ``ok`` False means a read failed: that is reported as a critical failure
        instead of being collapsed into "no displacement here".
        """
        src_disp_node, read_ok = self._read_sg_displacement(sg)
        if not read_ok:
            return None, False
        if src_disp_node:
            return self._parse_disp_node(src_disp_node, source_config)

        disp_texture = source_config.displacement_texture
        disp_scale = source_config.displacement_scale
        if not disp_texture:
            self.log.debug(f"No displacement texture mapping for {source_mat}", source=_SOURCE, nodes=(source_mat,))
            return None, True

        texture_plug = None
        scale_val = 1.0
        issues = []

        # ``displacement_texture`` names an attribute of the displacement *node*
        # in most configurations; material attributes of that name exist only for
        # some renderers.  A missing plug means "no displacement here", not a
        # read failure - only an existing plug that cannot be queried is critical.
        plug = f"{source_mat}.{disp_texture}"
        try:
            plug_exists = bool(cmds.objExists(plug))
        except Exception as exc:
            self.log.warn(f"Failed to query {plug}: {exc}", source=_SOURCE, nodes=(source_mat,))
            plug_exists = False

        if not plug_exists:
            self.log.debug(f"{source_mat} has no '{disp_texture}' attribute; no direct displacement",
                           source=_SOURCE, nodes=(source_mat,))
            return None, True

        try:
            conns = cmds.listConnections(plug, plugs=True, source=True) or []
            if conns:
                texture_plug = conns[0]
                self.log.debug(f"Source displacement texture plug: {texture_plug}", source=_SOURCE, nodes=(self.utils.node_name_from_plug(texture_plug), source_mat))
            else:
                self.log.debug(f"No displacement texture connected to {plug}", source=_SOURCE, nodes=(source_mat,))
        except Exception as exc:
            self.log.error(f"Failed to read displacement texture on {plug}: {exc}",
                           source=_SOURCE, nodes=(source_mat,))
            return None, False

        if disp_scale:
            scale_plug = f"{source_mat}.{disp_scale}"
            try:
                if cmds.objExists(scale_plug):
                    scale_val = cmds.getAttr(scale_plug)
                    self.log.debug(f"Source displacement scale: {scale_val!r}", source=_SOURCE, nodes=(source_mat,))
                else:
                    self.log.debug(f"{source_mat} has no '{disp_scale}' attribute; using 1.0",
                                   source=_SOURCE, nodes=(source_mat,))
            except Exception as exc:
                issues.append(f"{source_mat}: displacement scale not readable ({exc})")
                self.log.warn(f"Failed to read displacement scale {scale_plug}: {exc}", source=_SOURCE, nodes=(source_mat,))

        if not texture_plug:
            return None, True

        return {
            "texture_plug": texture_plug,
            "scale": scale_val,
            "src_node": None,
            "issues": issues,
        }, True

    def _parse_disp_node(self, disp_node, source_config):
        texture_plug = None
        scale_val = 1.0
        issues = []

        if source_config.displacement_texture:
            plug = f"{disp_node}.{source_config.displacement_texture}"
            try:
                plug_exists = bool(cmds.objExists(plug))
            except Exception as exc:
                self.log.warn(f"Failed to query {plug}: {exc}", source=_SOURCE, nodes=(disp_node,))
                plug_exists = False

            if plug_exists:
                try:
                    conns = cmds.listConnections(plug, plugs=True, source=True) or []
                    if conns:
                        texture_plug = conns[0]
                        self.log.debug(f"Displacement node {disp_node} texture plug: {texture_plug}", source=_SOURCE, nodes=(disp_node, self.utils.node_name_from_plug(texture_plug)))
                    else:
                        self.log.debug(f"No texture connected to {plug}", source=_SOURCE, nodes=(disp_node,))
                except Exception as exc:
                    self.log.error(f"Failed to read texture on {plug}: {exc}",
                                   source=_SOURCE, nodes=(disp_node,))
                    return None, False
            else:
                self.log.debug(
                    f"{disp_node} has no '{source_config.displacement_texture}' attribute; "
                    f"treated as no texture input", source=_SOURCE, nodes=(disp_node,))

        if source_config.displacement_scale:
            scale_plug = f"{disp_node}.{source_config.displacement_scale}"
            try:
                if cmds.objExists(scale_plug):
                    scale_val = cmds.getAttr(scale_plug)
                    self.log.debug(f"Displacement node {disp_node} scale: {scale_val!r}", source=_SOURCE, nodes=(disp_node,))
                else:
                    self.log.debug(f"{disp_node} has no '{source_config.displacement_scale}' attribute; using 1.0",
                                   source=_SOURCE, nodes=(disp_node,))
            except Exception as exc:
                issues.append(f"{disp_node}: displacement scale not readable ({exc})")
                self.log.warn(f"Failed to read scale on {scale_plug}: {exc}", source=_SOURCE, nodes=(disp_node,))

        return {
            "texture_plug": texture_plug,
            "scale": scale_val,
            "issues": issues,
        }, True

    def _read_sg_displacement(self, sg):
        """``(node | None, ok)`` for the SG's displacement input."""
        try:
            conns = cmds.listConnections(f"{sg}.displacementShader",
                                         source=True, destination=False) or []
        except Exception as exc:
            self.log.error(f"Failed to query displacement input on {sg}: {exc}",
                           source=_SOURCE, nodes=(sg,))
            return None, False
        if conns:
            self.log.debug(f"Displacement node for {sg}: {conns[0]}", source=_SOURCE, nodes=(sg, conns[0]))
            return conns[0], True
        self.log.debug(f"No displacementShader connected to {sg}", source=_SOURCE, nodes=(sg,))
        return None, True
