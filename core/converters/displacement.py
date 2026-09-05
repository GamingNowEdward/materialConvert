import maya.cmds as cmds

from core.logger import get_logger
from core.node_utils import RENDERER_SHORT

_SOURCE = "DisplacementConverter"


class DisplacementConverter:

    def __init__(self, config, utils, logger=None):
        self.config = config
        self.utils = utils
        self.log = logger or get_logger()

    def convert(self, source_mat, target_mat, source_config, target_config, target_renderer, sgs=None):
        """Convert displacement for *every* shading engine fed by *source_mat*.

        Displacement lives on the shading engine, so a material bound to several
        SGs must be converted per SG.  SGs that share the same source
        displacement (same texture plug + scale) reuse a single target
        displacement node instead of duplicating networks.
        """
        sgs = list(sgs or [])
        if not sgs:
            self.log.skip(f"No shading engine found for {source_mat}; displacement skipped", source=_SOURCE, nodes=(source_mat,))
            return

        disp_type = target_config.displacement_node_type
        disp_in = target_config.displacement_texture
        if not disp_type or not disp_in:
            self.log.skip("Target material has no displacement configuration", source=_SOURCE)
            return

        is_real_type = disp_type not in ("", "displacementShader")
        if not is_real_type and source_config.displacement_node_type == "displacementShader":
            self.log.skip("Source and target both use native displacementShader; nothing to convert", source=_SOURCE)
            return

        renderer_short = RENDERER_SHORT.get(target_renderer, target_renderer)
        disp_by_source = {}
        converted = 0
        skipped = 0

        for sg in sgs:
            src_disp_data = self._collect(source_mat, sg, source_config)
            if not src_disp_data:
                self.log.skip(f"No source displacement data for {source_mat} on {sg}", source=_SOURCE, nodes=(source_mat, sg))
                skipped += 1
                continue

            key = (src_disp_data.get("texture_plug"), src_disp_data.get("scale"))
            disp_node = disp_by_source.get(key)
            if disp_node is None:
                base_name = f"{source_mat}_{renderer_short}Disp"
                disp_node = self._create_node(
                    disp_type, disp_in, target_config.displacement_scale,
                    base_name, src_disp_data, source_mat,
                )
                if disp_node is None:
                    skipped += 1
                    continue
                disp_by_source[key] = disp_node

            if self._connect_to_sg(disp_node, sg, target_config.displacement_output):
                converted += 1
            else:
                skipped += 1

        self.log.info(
            f"Displacement conversion finished for {source_mat}: {converted} shading engine(s) "
            f"converted, {skipped} skipped",
            source=_SOURCE,
            nodes=(source_mat,),
        )

    def _create_node(self, disp_type, disp_in, disp_scale, base_name, src_disp_data, source_mat):
        try:
            disp_node = cmds.shadingNode(disp_type, asUtility=True, name=base_name)
        except Exception as exc:
            self.log.error(f"Failed to create {disp_type}: {exc}", source=_SOURCE, nodes=(source_mat,))
            return None
        self.log.debug(f"Created displacement node {disp_node}", source=_SOURCE, nodes=(disp_node,))

        texture_plug = src_disp_data.get("texture_plug")
        if texture_plug and disp_in:
            if self.utils.smart_connect(texture_plug, f"{disp_node}.{disp_in}", logger=self.log):
                self.log.debug(
                    f"Connected displacement texture {texture_plug} -> {disp_node}.{disp_in}",
                    source=_SOURCE,
                    nodes=(self.utils.node_name_from_plug(texture_plug), disp_node),
                )
            else:
                self.log.warn(
                    f"Failed to connect displacement texture {texture_plug} -> {disp_node}.{disp_in}",
                    source=_SOURCE,
                    nodes=(self.utils.node_name_from_plug(texture_plug), disp_node),
                )

        scale_val = src_disp_data.get("scale")
        if disp_scale and scale_val is not None:
            try:
                cmds.setAttr(f"{disp_node}.{disp_scale}", scale_val)
                self.log.debug(f"Set {disp_node}.{disp_scale} = {scale_val!r}", source=_SOURCE, nodes=(disp_node,))
            except Exception as exc:
                self.log.warn(f"Failed to set displacement scale on {disp_node}: {exc}", source=_SOURCE, nodes=(disp_node,))
        return disp_node

    def _connect_to_sg(self, disp_node, sg, output_attr):
        """Bind *disp_node* to ``sg.displacementShader`` via a usable output plug.

        The configured ``output`` attribute (e.g. ``displacement`` for native
        displacementShader, ``out`` for RedshiftDisplacement) is tried first,
        then generic fallbacks for robustness.
        """
        attempts = []
        if output_attr:
            attempts.append(output_attr)
        for fallback in ("outDisplacement", "out", "outColor"):
            if fallback not in attempts:
                attempts.append(fallback)

        for attr in attempts:
            try:
                if not cmds.objExists(f"{disp_node}.{attr}"):
                    continue
                cmds.connectAttr(f"{disp_node}.{attr}", f"{sg}.displacementShader", force=True)
                self.log.info(
                    f"Connected displacement {disp_node}.{attr} -> {sg}.displacementShader",
                    source=_SOURCE,
                    nodes=(disp_node, sg),
                )
                return True
            except Exception as exc:
                self.log.warn(
                    f"Failed to connect {disp_node}.{attr} -> {sg}.displacementShader: {exc}",
                    source=_SOURCE,
                    nodes=(disp_node, sg),
                )

        self.log.warn(f"No usable displacement output attribute found on {disp_node}", source=_SOURCE, nodes=(disp_node,))
        return False

    def _collect(self, source_mat, sg, source_config):
        src_disp_node = self.utils.get_displacement_node_from_sg(sg, logger=self.log)
        if src_disp_node:
            return self._parse_disp_node(src_disp_node, source_config)

        disp_texture = source_config.displacement_texture
        disp_scale = source_config.displacement_scale
        if not disp_texture:
            self.log.debug(f"No displacement texture mapping for {source_mat}", source=_SOURCE, nodes=(source_mat,))
            return None

        texture_plug = None
        scale_val = 1.0

        try:
            conns = cmds.listConnections(f"{source_mat}.{disp_texture}", plugs=True, source=True) or []
            if conns:
                texture_plug = conns[0]
                self.log.debug(f"Source displacement texture plug: {texture_plug}", source=_SOURCE, nodes=(self.utils.node_name_from_plug(texture_plug), source_mat))
            else:
                self.log.debug(f"No displacement texture connected to {source_mat}.{disp_texture}", source=_SOURCE, nodes=(source_mat,))
        except Exception as exc:
            self.log.warn(f"Failed to read displacement texture on {source_mat}.{disp_texture}: {exc}", source=_SOURCE, nodes=(source_mat,))

        if disp_scale:
            try:
                scale_val = cmds.getAttr(f"{source_mat}.{disp_scale}")
                self.log.debug(f"Source displacement scale: {scale_val!r}", source=_SOURCE, nodes=(source_mat,))
            except Exception as exc:
                self.log.warn(f"Failed to read displacement scale {source_mat}.{disp_scale}: {exc}", source=_SOURCE, nodes=(source_mat,))

        if not texture_plug:
            return None

        return {
            "texture_plug": texture_plug,
            "scale": scale_val,
            "src_node": None,
        }

    def _parse_disp_node(self, disp_node, source_config):
        texture_plug = None
        scale_val = 1.0

        if source_config.displacement_texture:
            try:
                conns = cmds.listConnections(f"{disp_node}.{source_config.displacement_texture}",
                                             plugs=True, source=True) or []
                if conns:
                    texture_plug = conns[0]
                    self.log.debug(f"Displacement node {disp_node} texture plug: {texture_plug}", source=_SOURCE, nodes=(disp_node, self.utils.node_name_from_plug(texture_plug)))
                else:
                    self.log.debug(f"No texture connected to {disp_node}.{source_config.displacement_texture}", source=_SOURCE, nodes=(disp_node,))
            except Exception as exc:
                self.log.warn(
                    f"Failed to read texture on {disp_node}.{source_config.displacement_texture}: {exc}",
                    source=_SOURCE,
                    nodes=(disp_node,),
                )

        if source_config.displacement_scale:
            try:
                scale_val = cmds.getAttr(f"{disp_node}.{source_config.displacement_scale}")
                self.log.debug(f"Displacement node {disp_node} scale: {scale_val!r}", source=_SOURCE, nodes=(disp_node,))
            except Exception as exc:
                self.log.warn(f"Failed to read scale on {disp_node}.{source_config.displacement_scale}: {exc}", source=_SOURCE, nodes=(disp_node,))

        return {
            "texture_plug": texture_plug,
            "scale": scale_val,
        }
