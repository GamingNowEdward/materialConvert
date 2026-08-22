import maya.cmds as cmds

from core.logger import get_logger
from core.node_utils import RENDERER_SHORT

_SOURCE = "DisplacementConverter"


class DisplacementConverter:

    def __init__(self, config, utils, logger=None):
        self.config = config
        self.utils = utils
        self.log = logger or get_logger()

    def convert(self, source_mat, target_mat, source_config, target_config, target_renderer):
        sg = self.utils.get_shading_engine(source_mat, logger=self.log)
        if not sg:
            self.log.skip(f"No shading engine found for {source_mat}; displacement skipped", source=_SOURCE)
            return

        src_disp_data = self._collect(source_mat, sg, source_config)
        if not src_disp_data:
            self.log.skip(f"No source displacement data found for {source_mat}", source=_SOURCE)
            return

        if not target_config.displacement_node_type and not target_config.displacement_texture:
            self.log.skip("Target material has no displacement configuration", source=_SOURCE)
            return

        is_real_type = target_config.displacement_node_type and target_config.displacement_node_type not in ("displacementShader", "")
        if not is_real_type and source_config.displacement_node_type == "displacementShader":
            self.log.skip("Source and target both use native displacementShader; nothing to convert", source=_SOURCE)
            return

        texture_plug = src_disp_data.get("texture_plug")
        scale_val = src_disp_data.get("scale", 1.0)

        renderer_short = RENDERER_SHORT.get(target_renderer, target_renderer)

        if is_real_type:
            base_name = source_mat + "_" + renderer_short + "Disp"
            try:
                disp_node = cmds.shadingNode(target_config.displacement_node_type, asUtility=True, name=base_name)
            except Exception as exc:
                self.log.error(f"Failed to create {target_config.displacement_node_type}: {exc}", source=_SOURCE)
                return
            self.log.debug(f"Created displacement node {disp_node}", source=_SOURCE)

            if texture_plug and target_config.displacement_texture:
                if self.utils.smart_connect(texture_plug, f"{disp_node}.{target_config.displacement_texture}", logger=self.log):
                    self.log.debug(f"Connected displacement texture {texture_plug} -> {disp_node}", source=_SOURCE)
                else:
                    self.log.warn(f"Failed to connect displacement texture {texture_plug} -> {disp_node}", source=_SOURCE)

            if target_config.displacement_scale and scale_val is not None:
                try:
                    cmds.setAttr(f"{disp_node}.{target_config.displacement_scale}", scale_val)
                    self.log.debug(f"Set {disp_node}.{target_config.displacement_scale} = {scale_val!r}", source=_SOURCE)
                except Exception as exc:
                    self.log.warn(f"Failed to set displacement scale on {disp_node}: {exc}", source=_SOURCE)

            try:
                for out_attr in ["outDisplacement", "out", "outColor"]:
                    if cmds.objExists(f"{disp_node}.{out_attr}"):
                        cmds.connectAttr(f"{disp_node}.{out_attr}", f"{sg}.displacementShader", force=True)
                        self.log.info(f"Connected displacement {disp_node}.{out_attr} -> {sg}.displacementShader", source=_SOURCE)
                        break
                else:
                    self.log.warn(f"No valid displacement output attribute found on {disp_node}", source=_SOURCE)
            except Exception as exc:
                self.log.error(f"Failed to connect displacement {disp_node} -> {sg}: {exc}", source=_SOURCE)

            self.log.info(f"Displacement: converted to {target_config.displacement_node_type}", source=_SOURCE)
        else:
            base_name = source_mat + "_" + renderer_short + "Disp"
            try:
                disp_node = cmds.shadingNode("displacementShader", asUtility=True, name=base_name)
            except Exception as exc:
                self.log.error(f"Failed to create displacementShader: {exc}", source=_SOURCE)
                return
            self.log.debug(f"Created displacementShader node {disp_node}", source=_SOURCE)

            if texture_plug:
                if self.utils.smart_connect(texture_plug, f"{disp_node}.displacement", logger=self.log):
                    self.log.debug(f"Connected displacement texture {texture_plug} -> {disp_node}.displacement", source=_SOURCE)
                else:
                    self.log.warn(f"Failed to connect displacement texture {texture_plug} -> {disp_node}.displacement", source=_SOURCE)

            if scale_val is not None:
                try:
                    cmds.setAttr(f"{disp_node}.scale", scale_val)
                    self.log.debug(f"Set {disp_node}.scale = {scale_val!r}", source=_SOURCE)
                except Exception as exc:
                    self.log.warn(f"Failed to set scale on {disp_node}: {exc}", source=_SOURCE)

            try:
                cmds.connectAttr(f"{disp_node}.displacement", f"{sg}.displacementShader", force=True)
                self.log.info(f"Connected displacementShader {disp_node} -> {sg}.displacementShader", source=_SOURCE)
            except Exception as exc:
                self.log.error(f"Failed to connect {disp_node} -> {sg}.displacementShader: {exc}", source=_SOURCE)

            self.log.info("Displacement: converted to displacementShader", source=_SOURCE)

    def _collect(self, source_mat, sg, source_config):
        src_disp_node = self.utils.get_displacement_node_from_sg(sg, logger=self.log)
        if src_disp_node:
            return self._parse_disp_node(src_disp_node, source_config)

        disp_texture = source_config.displacement_texture
        disp_scale = source_config.displacement_scale
        if not disp_texture:
            self.log.debug(f"No displacement texture mapping for {source_mat}", source=_SOURCE)
            return None

        texture_plug = None
        scale_val = 1.0

        try:
            conns = cmds.listConnections(f"{source_mat}.{disp_texture}", plugs=True, source=True) or []
            if conns:
                texture_plug = conns[0]
                self.log.debug(f"Source displacement texture plug: {texture_plug}", source=_SOURCE)
            else:
                self.log.debug(f"No displacement texture connected to {source_mat}.{disp_texture}", source=_SOURCE)
        except Exception as exc:
            self.log.warn(f"Failed to read displacement texture on {source_mat}.{disp_texture}: {exc}", source=_SOURCE)

        if disp_scale:
            try:
                scale_val = cmds.getAttr(f"{source_mat}.{disp_scale}")
                self.log.debug(f"Source displacement scale: {scale_val!r}", source=_SOURCE)
            except Exception as exc:
                self.log.warn(f"Failed to read displacement scale {source_mat}.{disp_scale}: {exc}", source=_SOURCE)

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
                    self.log.debug(f"Displacement node {disp_node} texture plug: {texture_plug}", source=_SOURCE)
                else:
                    self.log.debug(f"No texture connected to {disp_node}.{source_config.displacement_texture}", source=_SOURCE)
            except Exception as exc:
                self.log.warn(
                    f"Failed to read texture on {disp_node}.{source_config.displacement_texture}: {exc}",
                    source=_SOURCE,
                )

        if source_config.displacement_scale:
            try:
                scale_val = cmds.getAttr(f"{disp_node}.{source_config.displacement_scale}")
                self.log.debug(f"Displacement node {disp_node} scale: {scale_val!r}", source=_SOURCE)
            except Exception as exc:
                self.log.warn(f"Failed to read scale on {disp_node}.{source_config.displacement_scale}: {exc}", source=_SOURCE)

        return {
            "texture_plug": texture_plug,
            "scale": scale_val,
        }
