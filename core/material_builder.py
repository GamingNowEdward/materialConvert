import maya.cmds as cmds

from core.builder_context import BuilderContext
from core.config_loader import ConfigLoader
import core.node_utils as node_utils


class MaterialBuilder:

    P2D_ATTRS = ['coverage', 'translateFrame', 'rotateFrame', 'mirrorU', 'mirrorV',
                 'stagger', 'wrapU', 'wrapV', 'repeatUV', 'offset', 'rotateUV', 'noiseUV']

    CHANNEL_COMMON_ATTRS = {
        "color": "baseColor",
        "rough": "specularRoughness",
        "sss": "subsurfaceColor",
        "metallic": "metallic",
        "opacity": "opacity",
        "emission": "emissionColor",
        "transmission": "transmissionColor",
        "sheen": "fuzzColor",
        "translucency": "subsurfaceColor",
        "scattering": "subsurfaceColor",
        "reflection": "specularColor",
        "nrm": "normal_bump",
        "bump": "normal_bump",
    }

    WEIGHT_ATTRS = {
        "emission": "emissionWeight",
        "transmission": "transmissionWeight",
        "sheen": "fuzzWeight",
        "sss": "subsurfaceWeight",
        "reflection": "specularWeight",
    }


    def __init__(self, ctx: BuilderContext):
        self.ctx = ctx
        self.config = ConfigLoader()

    def build(self, node_type, base_name, input_paths, use_nrm=True, use_sss=False, use_disp=False,
              use_qss=True, use_full_chain=True, channel_options=None):
        mat_config = self.config.get_material_config(node_type)
        if not mat_config:
            raise RuntimeError(f"缺少材质配置: {node_type}")
        renderer = mat_config.renderer

        if mat_config.plugin and not cmds.pluginInfo(mat_config.plugin, query=True, loaded=True):
            cmds.loadPlugin(mat_config.plugin)

        self.ctx._current_build_nodes = []
        m_node = self.ctx.create_node(node_type, 'material', base_name, as_type='shader')
        sg_node = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=f"{m_node}SG")
        self.ctx._current_build_nodes.append(sg_node)
        self.ctx.connect(m_node, "outColor", sg_node, "surfaceShader")

        self._apply_material_prereqs(m_node, mat_config)

        p2d = self.ctx.create_node('place2dTexture', 'p2d', base_name)

        def make_tex(key, is_alpha=False, invert=False):
            f = self.ctx.create_node('file', 'file', base_name, key, 'texture')
            if is_alpha:
                cmds.setAttr(f"{f}.alphaIsLuminance", 1)
            path = input_paths.get(key, "")
            if path:
                cmds.setAttr(f"{f}.fileTextureName", path, type="string")
            if invert and cmds.attributeQuery("invert", node=f, exists=True):
                cmds.setAttr(f"{f}.invert", 1)
            for attr in self.P2D_ATTRS:
                self.ctx.connect(p2d, attr, f, attr)
            self.ctx.connect(p2d, "outUV", f, "uvCoord")
            self.ctx.connect(p2d, "outUvFilterSize", f, "uvFilterSize")
            return f

        channel_options = channel_options or {}
        self._build_color_chain_new(m_node, renderer, base_name, make_tex, mat_config,
                                    use_sss, use_full_chain, input_paths)
        self._build_rough_chain_new(m_node, base_name, make_tex, mat_config,
                                    use_full_chain, channel_options, input_paths)
        self._build_metallic_chain(m_node, base_name, make_tex, mat_config, input_paths)
        self._build_opacity_chain(m_node, base_name, make_tex, mat_config, input_paths)
        self._build_emission_chain(m_node, renderer, base_name, make_tex, mat_config,
                                   use_full_chain, input_paths)
        self._build_transmission_chain(m_node, renderer, base_name, make_tex, mat_config,
                                       use_full_chain, input_paths)
        self._build_sheen_chain(m_node, renderer, base_name, make_tex, mat_config,
                                use_full_chain, input_paths)
        self._build_reflection_chain(m_node, renderer, base_name, make_tex, mat_config,
                                     use_full_chain, input_paths)
        self._build_bump_normal_new(m_node, renderer, base_name, make_tex, mat_config,
                                    use_nrm, channel_options, input_paths)
        if use_disp or input_paths.get("disp"):
            self._build_displacement_new(m_node, sg_node, base_name, make_tex, mat_config,
                                         use_full_chain)

        qss_nodes = list(self.ctx._current_build_nodes)
        if use_qss and qss_nodes:
            cmds.sets(qss_nodes, name=f"{self.ctx.get_naming()['qss_prefix']}{base_name}")

        cmds.select(m_node)
        return m_node

    def _apply_material_prereqs(self, m_node, mat_config):
        from core.prerequisites import apply_prerequisites
        apply_prerequisites(m_node, mat_config)

    def _build_color_chain(self, m_node, renderer, base_name, make_tex, mat_config, use_sss):
        cc_config = self.config.get_color_correction_config(renderer)
        if not cc_config or not cc_config.node_type:
            return

        tex_color = make_tex('color')
        for ch in (['color', 'sss'] if use_sss else ['color']):
            attr_name = mat_config.get_maya_attr(self.CHANNEL_COMMON_ATTRS[ch])
            if not attr_name:
                continue
            cc = self.ctx.create_node(cc_config.node_type, 'cc', base_name, ch)
            lyr = self.ctx.build_layered_node(base_name, ch)
            self.ctx.connect(tex_color, "outColor", cc, cc_config.source_connection)
            self.ctx.connect(cc, cc_config.target_connection, lyr, "inputs[1].color")
            self.ctx.connect(lyr, "outColor", m_node, attr_name)
            if ch == 'sss' and cmds.attributeQuery('ssOn', node=m_node, exists=True):
                cmds.setAttr(f"{m_node}.ssOn", 1)

    def _build_rough_chain(self, m_node, base_name, make_tex, mat_config):
        rough_attr = mat_config.get_maya_attr(self.CHANNEL_COMMON_ATTRS['rough'])
        if not rough_attr:
            return
        tex_rough = make_tex('rough', True)
        ramp = self.ctx.create_node('ramp', 'ramp', base_name, 'rough', 'texture')
        self.ctx.connect(tex_rough, "outAlpha", ramp, "vCoord")
        self.ctx.connect(ramp, "outAlpha", m_node, rough_attr)

    def _build_bump_normal(self, m_node, renderer, base_name, make_tex, mat_config, use_nrm):
        bn_config = self.config.get_bump_normal_config(renderer)
        if not bn_config:
            return

        nb_key = 'nrm' if use_nrm else 'bump'
        mapping = bn_config.normal if use_nrm else bn_config.bump
        if not mapping:
            return

        target_attr = mat_config.get_maya_attr(self.CHANNEL_COMMON_ATTRS[nb_key])
        if not target_attr:
            return

        tex_nb = make_tex(nb_key, not use_nrm)

        if mapping.is_material_attribute:
            if mapping.input:
                self.ctx.connect(tex_nb, mapping.file_source, m_node, mapping.input)
            if mapping.scale and mapping.default_scale is not None:
                if cmds.attributeQuery(mapping.scale, node=m_node, exists=True):
                    cmds.setAttr(f"{m_node}.{mapping.scale}", mapping.default_scale)
            if mapping.input_type and mapping.input_type_value is not None:
                if cmds.attributeQuery(mapping.input_type, node=m_node, exists=True):
                    cmds.setAttr(f"{m_node}.{mapping.input_type}", mapping.input_type_value)
            return

        bn_node = self.ctx.create_node(mapping.node_type, nb_key, base_name)
        if mapping.scale and mapping.default_scale is not None:
            cmds.setAttr(f"{bn_node}.{mapping.scale}", mapping.default_scale)
        if mapping.isNormal and mapping.isNormal_value is not None:
            cmds.setAttr(f"{bn_node}.{mapping.isNormal}", mapping.isNormal_value)
        if mapping.source_connection:
            self.ctx.connect(tex_nb, mapping.file_source, bn_node, mapping.source_connection)
        if mapping.target_connection:
            self.ctx.connect(bn_node, mapping.target_connection, m_node, target_attr)

    def _build_displacement(self, m_node, sg_node, base_name, make_tex, mat_config):
        disp_type = mat_config.displacement_node_type
        disp_in = mat_config.displacement_texture
        if not disp_type or not disp_in:
            return

        tex_disp = make_tex('disp', True)
        lyr_disp = self.ctx.build_layered_node(base_name, 'disp', layers=2)
        for rgb in 'RGB':
            self.ctx.connect(tex_disp, mat_config.displacement_file_source, lyr_disp, f"inputs[1].color{rgb}")
        d_node = self.ctx.create_node(disp_type, 'disp', base_name, as_type='shader')
        self.ctx.connect(lyr_disp, mat_config.displacement_lyr_src, d_node, disp_in)
        self.ctx.connect(d_node, mat_config.displacement_output, sg_node, "displacementShader")


    # ── New Batch/Extended Builder Methods ─────────────────────────

    def _connect_color_channel(self, m_node, renderer, base_name, ch, attr_name, tex,
                               use_full_chain, cc_config, mat_config):
        if use_full_chain and cc_config and cc_config.node_type:
            cc = self.ctx.create_node(cc_config.node_type, 'cc', base_name, ch)
            lyr = self.ctx.build_layered_node(base_name, ch)
            self.ctx.connect(tex, "outColor", cc, cc_config.source_connection)
            self.ctx.connect(cc, cc_config.target_connection, lyr, "inputs[1].color")
            self.ctx.connect(lyr, "outColor", m_node, attr_name)
        else:
            self.ctx.connect(tex, "outColor", m_node, attr_name)

        if ch == 'sss' and cmds.attributeQuery('ssOn', node=m_node, exists=True):
            cmds.setAttr(f"{m_node}.ssOn", 1)

        weight_common = self.WEIGHT_ATTRS.get(ch)
        if weight_common:
            weight_attr = mat_config.get_maya_attr(weight_common)
            if weight_attr and cmds.attributeQuery(weight_attr, node=m_node, exists=True):
                cmds.setAttr(f"{m_node}.{weight_attr}", 1)

    def _build_color_chain_new(self, m_node, renderer, base_name, make_tex, mat_config,
                               use_sss, use_full_chain, input_paths):
        cc_config = self.config.get_color_correction_config(renderer)

        tex_color = None
        # Builder Tab always includes a 'color' key, so this keeps old behavior.
        # Batch Builder omits it when there is no BaseColor texture.
        if 'color' in input_paths:
            tex_color = make_tex('color')
            color_attr = mat_config.get_maya_attr(self.CHANNEL_COMMON_ATTRS['color'])
            if color_attr:
                self._connect_color_channel(
                    m_node, renderer, base_name, 'color', color_attr, tex_color,
                    use_full_chain, cc_config, mat_config,
                )

        # SSS: either the legacy use_sss flag or a dedicated sss path.
        if use_sss or 'sss' in input_paths:
            sss_attr = mat_config.get_maya_attr(self.CHANNEL_COMMON_ATTRS['sss'])
            if sss_attr:
                if 'sss' in input_paths:
                    tex_sss = make_tex('sss')
                elif tex_color is not None:
                    tex_sss = tex_color
                else:
                    tex_sss = None
                if tex_sss is not None:
                    self._connect_color_channel(
                        m_node, renderer, base_name, 'sss', sss_attr, tex_sss,
                        use_full_chain, cc_config, mat_config,
                    )

    def _build_rough_chain_new(self, m_node, base_name, make_tex, mat_config,
                               use_full_chain, channel_options, input_paths):
        if 'rough' not in input_paths:
            return
        rough_attr = mat_config.get_maya_attr(self.CHANNEL_COMMON_ATTRS['rough'])
        if not rough_attr:
            return

        invert = channel_options.get('rough', {}).get('invert', False)
        tex_rough = make_tex('rough', True, invert=invert)

        if use_full_chain:
            ramp = self.ctx.create_node('ramp', 'ramp', base_name, 'rough', 'texture')
            self.ctx.connect(tex_rough, "outAlpha", ramp, "vCoord")
            self.ctx.connect(ramp, "outAlpha", m_node, rough_attr)
        else:
            node_utils.smart_connect(f"{tex_rough}.outAlpha", f"{m_node}.{rough_attr}")

    def _build_metallic_chain(self, m_node, base_name, make_tex, mat_config, input_paths):
        if 'metallic' not in input_paths:
            return
        attr_name = mat_config.get_maya_attr(self.CHANNEL_COMMON_ATTRS['metallic'])
        if not attr_name:
            return
        tex = make_tex('metallic', True)
        node_utils.smart_connect(f"{tex}.outAlpha", f"{m_node}.{attr_name}")

    def _build_opacity_chain(self, m_node, base_name, make_tex, mat_config, input_paths):
        if 'opacity' not in input_paths:
            return
        attr_name = mat_config.get_maya_attr(self.CHANNEL_COMMON_ATTRS['opacity'])
        if not attr_name:
            return
        tex = make_tex('opacity', True)
        node_utils.smart_connect(f"{tex}.outAlpha", f"{m_node}.{attr_name}")

    def _build_emission_chain(self, m_node, renderer, base_name, make_tex, mat_config,
                              use_full_chain, input_paths):
        if 'emission' not in input_paths:
            return
        attr_name = mat_config.get_maya_attr(self.CHANNEL_COMMON_ATTRS['emission'])
        if not attr_name:
            return
        tex = make_tex('emission')
        cc_config = self.config.get_color_correction_config(renderer)
        self._connect_color_channel(
            m_node, renderer, base_name, 'emission', attr_name, tex,
            use_full_chain, cc_config, mat_config,
        )

    def _build_transmission_chain(self, m_node, renderer, base_name, make_tex, mat_config,
                                  use_full_chain, input_paths):
        if 'transmission' not in input_paths:
            return
        attr_name = mat_config.get_maya_attr(self.CHANNEL_COMMON_ATTRS['transmission'])
        if not attr_name:
            return
        tex = make_tex('transmission')
        cc_config = self.config.get_color_correction_config(renderer)
        self._connect_color_channel(
            m_node, renderer, base_name, 'transmission', attr_name, tex,
            use_full_chain, cc_config, mat_config,
        )

    def _build_sheen_chain(self, m_node, renderer, base_name, make_tex, mat_config,
                           use_full_chain, input_paths):
        if 'sheen' not in input_paths:
            return
        attr_name = mat_config.get_maya_attr(self.CHANNEL_COMMON_ATTRS['sheen'])
        if not attr_name:
            return
        tex = make_tex('sheen')
        cc_config = self.config.get_color_correction_config(renderer)
        self._connect_color_channel(
            m_node, renderer, base_name, 'sheen', attr_name, tex,
            use_full_chain, cc_config, mat_config,
        )

    def _build_reflection_chain(self, m_node, renderer, base_name, make_tex, mat_config,
                                use_full_chain, input_paths):
        if 'reflection' not in input_paths:
            return
        attr_name = mat_config.get_maya_attr(self.CHANNEL_COMMON_ATTRS['reflection'])
        if not attr_name:
            return
        tex = make_tex('reflection')
        cc_config = self.config.get_color_correction_config(renderer)
        self._connect_color_channel(
            m_node, renderer, base_name, 'reflection', attr_name, tex,
            use_full_chain, cc_config, mat_config,
        )

    def _build_bump_normal_new(self, m_node, renderer, base_name, make_tex, mat_config,
                               use_nrm, channel_options, input_paths):
        bn_config = self.config.get_bump_normal_config(renderer)
        if not bn_config:
            return

        # Priority: per-channel option from scanner, then legacy use_nrm flag.
        mode = (
            channel_options.get('nrm', {}).get('mode')
            or channel_options.get('bump', {}).get('mode')
            or ('normal' if use_nrm else 'bump')
        )
        is_normal = mode == 'normal'
        nb_key = 'nrm' if is_normal else 'bump'
        mapping = bn_config.normal if is_normal else bn_config.bump
        if not mapping:
            return

        target_attr = mat_config.get_maya_attr(self.CHANNEL_COMMON_ATTRS[nb_key])
        if not target_attr:
            return

        # Use the key that actually has a path; fall back to the other key.
        tex_key = nb_key
        if tex_key not in input_paths:
            tex_key = 'bump' if is_normal else 'nrm'
        if tex_key not in input_paths:
            return

        tex_nb = make_tex(tex_key, not is_normal)

        if mapping.is_material_attribute:
            if mapping.input:
                self.ctx.connect(tex_nb, mapping.file_source, m_node, mapping.input)
            if mapping.scale and mapping.default_scale is not None:
                if cmds.attributeQuery(mapping.scale, node=m_node, exists=True):
                    cmds.setAttr(f"{m_node}.{mapping.scale}", mapping.default_scale)
            if mapping.input_type and mapping.input_type_value is not None:
                if cmds.attributeQuery(mapping.input_type, node=m_node, exists=True):
                    cmds.setAttr(f"{m_node}.{mapping.input_type}", mapping.input_type_value)
            return

        bn_node = self.ctx.create_node(mapping.node_type, nb_key, base_name)
        if mapping.scale and mapping.default_scale is not None:
            cmds.setAttr(f"{bn_node}.{mapping.scale}", mapping.default_scale)
        if mapping.isNormal and mapping.isNormal_value is not None:
            cmds.setAttr(f"{bn_node}.{mapping.isNormal}", mapping.isNormal_value)
        if mapping.source_connection:
            self.ctx.connect(tex_nb, mapping.file_source, bn_node, mapping.source_connection)
        if mapping.target_connection:
            self.ctx.connect(bn_node, mapping.target_connection, m_node, target_attr)

    def _build_displacement_new(self, m_node, sg_node, base_name, make_tex, mat_config,
                                use_full_chain):
        disp_type = mat_config.displacement_node_type
        disp_in = mat_config.displacement_texture
        if not disp_type or not disp_in:
            return

        tex_disp = make_tex('disp', True)
        d_node = self.ctx.create_node(disp_type, 'disp', base_name, as_type='shader')

        if use_full_chain:
            lyr_disp = self.ctx.build_layered_node(base_name, 'disp', layers=2)
            for rgb in 'RGB':
                self.ctx.connect(tex_disp, mat_config.displacement_file_source,
                                 lyr_disp, f"inputs[1].color{rgb}")
            self.ctx.connect(lyr_disp, mat_config.displacement_lyr_src, d_node, disp_in)
        else:
            node_utils.smart_connect(
                f"{tex_disp}.{mat_config.displacement_file_source}",
                f"{d_node}.{disp_in}",
            )

        self.ctx.connect(d_node, mat_config.displacement_output, sg_node, "displacementShader")
