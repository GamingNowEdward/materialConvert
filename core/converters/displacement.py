import pymel.core as pm
import maya.cmds as cmds


class DisplacementConverter:

    def __init__(self, config, utils):
        self.config = config
        self.utils = utils

    def convert(self, source_mat, target_mat, source_config, target_config,
                target_renderer, log):
        sg = self.utils.get_shading_engine(source_mat)
        if not sg:
            return

        src_disp_data = self._collect(source_mat, sg, source_config)
        if not src_disp_data:
            return

        if not target_config.displacement_node_type and not target_config.displacement_texture:
            return

        is_real_type = target_config.displacement_node_type and target_config.displacement_node_type not in ("displacementShader", "")
        if not is_real_type and source_config.displacement_node_type == "displacementShader":
            return

        texture_plug = src_disp_data.get("texture_plug")
        scale_val = src_disp_data.get("scale", 1.0)

        renderer_short = {"arnold": "ai", "redshift": "rs", "vray": "vray"}.get(target_renderer, target_renderer)

        if is_real_type:
            base_name = source_mat.name() + "_" + renderer_short + "Disp"
            node_name = cmds.shadingNode(target_config.displacement_node_type, asUtility=True, name=base_name)
            disp_node = pm.PyNode(node_name)

            if texture_plug and target_config.displacement_texture:
                self.utils.smart_connect(texture_plug, disp_node.attr(target_config.displacement_texture))

            if target_config.displacement_scale and scale_val is not None:
                try:
                    disp_node.attr(target_config.displacement_scale).set(scale_val)
                except Exception:
                    pm.warning(f"DisplacementConverter: failed to set scale on {disp_node.name()}")

            try:
                for out_attr in ["outDisplacement", "out", "outColor"]:
                    if pm.objExists(f"{disp_node.name()}.{out_attr}"):
                        disp_node.attr(out_attr) >> sg.displacementShader
                        break
            except Exception:
                pm.warning(f"DisplacementConverter: failed to connect {disp_node.name()} to SG")

            log.append(f"  Displacement: converted to {target_config.displacement_node_type}")
        else:
            base_name = source_mat.name() + "_" + renderer_short + "Disp"
            disp_node = pm.PyNode(cmds.shadingNode("displacementShader", asUtility=True, name=base_name))

            if texture_plug:
                self.utils.smart_connect(texture_plug, disp_node.displacement)

            if scale_val is not None:
                try:
                    disp_node.scale.set(scale_val)
                except Exception:
                    pm.warning(f"DisplacementConverter: failed to set scale on {disp_node.name()}")

            disp_node.displacement >> sg.displacementShader
            log.append("  Displacement: converted to displacementShader")

    def _collect(self, source_mat, sg, source_config):
        src_disp_node = self.utils.get_displacement_node_from_sg(sg)
        if src_disp_node:
            return self._parse_disp_node(src_disp_node, source_config)

        disp_texture = source_config.displacement_texture
        disp_scale = source_config.displacement_scale
        if not disp_texture:
            return None

        texture_plug = None
        scale_val = 1.0

        try:
            conns = source_mat.attr(disp_texture).connections(plugs=True, source=True)
            if conns:
                texture_plug = conns[0]
        except Exception:
            pass

        try:
            scale_val = source_mat.attr(disp_scale).get()
        except Exception:
            pass

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
                conns = disp_node.attr(source_config.displacement_texture).connections(plugs=True, source=True)
                if conns:
                    texture_plug = conns[0]
            except Exception:
                pass

        if source_config.displacement_scale:
            try:
                scale_val = disp_node.attr(source_config.displacement_scale).get()
            except Exception:
                pass

        return {
            "texture_plug": texture_plug,
            "scale": scale_val,
        }
