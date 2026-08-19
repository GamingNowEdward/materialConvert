import maya.cmds as cmds

from core.builder_context import BuilderContext
from core.config_loader import ConfigLoader
import core.node_utils as node_utils


class MaterialBuilder:

    P2D_ATTRS = ['coverage', 'translateFrame', 'rotateFrame', 'mirrorU', 'mirrorV',
                 'stagger', 'wrapU', 'wrapV', 'repeatUV', 'offset', 'rotateUV', 'noiseUV']

    def __init__(self, ctx: BuilderContext):
        self.ctx = ctx
        self.config = ConfigLoader()

    def _resolve_weight_attr(self, common_attr):
        if not common_attr:
            return ""
        return self.config.get_weight_attr_for_common_attr(common_attr)

    def build(self, node_type, base_name, input_paths, use_nrm=True, use_disp=False,
              use_qss=True, use_full_chain=True, channel_options=None):
        mat_config = self.config.get_material_config(node_type)
        if not mat_config:
            raise RuntimeError(f"Missing material config: {node_type}")
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

        channel_options = channel_options or {}

        def make_tex(common_attr, name_key=None, is_alpha=False, invert=False):
            f = self.ctx.create_node(
                'file', 'file', base_name, name_key or common_attr, 'texture'
            )
            path = input_paths.get(common_attr, "")
            if path:
                cmds.setAttr(f"{f}.fileTextureName", path, type="string")
            if is_alpha:
                cmds.setAttr(f"{f}.alphaIsLuminance", 1)
            if invert and cmds.attributeQuery("invert", node=f, exists=True):
                cmds.setAttr(f"{f}.invert", 1)
            for attr in self.P2D_ATTRS:
                self.ctx.connect(p2d, attr, f, attr)
            self.ctx.connect(p2d, "outUV", f, "uvCoord")
            self.ctx.connect(p2d, "outUvFilterSize", f, "uvFilterSize")
            return f

        for common_attr, name_key in (('baseColor', 'color'), ('subsurfaceColor', 'sss')):
            self._build_color_chain(m_node, renderer, base_name, make_tex, mat_config,
                                    use_full_chain, input_paths, common_attr, name_key)

        self._build_scalar_chain(m_node, base_name, make_tex, mat_config, 'specularRoughness',
                                 'rough', input_paths, use_full_chain,
                                 channel_options.get('specularRoughness', {}).get('invert', False))
        self._build_scalar_chain(m_node, base_name, make_tex, mat_config, 'metallic', 'metallic',
                                 input_paths)
        self._build_scalar_chain(m_node, base_name, make_tex, mat_config, 'opacity', 'opacity',
                                 input_paths)

        for common_attr, name_key in (('emissionColor', 'emission'),
                                      ('transmissionColor', 'transmission'),
                                      ('fuzzColor', 'sheen'),
                                      ('specularColor', 'reflection')):
            self._build_color_chain(m_node, renderer, base_name, make_tex, mat_config,
                                    use_full_chain, input_paths, common_attr, name_key)

        self._build_bump_normal(m_node, renderer, base_name, make_tex, mat_config,
                                use_nrm, channel_options, input_paths)
        if use_disp or "displacementTexture" in input_paths:
            self._build_displacement(m_node, sg_node, base_name, make_tex, mat_config,
                                     use_full_chain)

        qss_nodes = list(self.ctx._current_build_nodes)
        if use_qss and qss_nodes:
            cmds.sets(qss_nodes, name=f"{self.ctx.get_naming()['qss_prefix']}{base_name}")

        cmds.select(m_node)
        return m_node

    def _apply_material_prereqs(self, m_node, mat_config):
        from core.prerequisites import apply_prerequisites
        apply_prerequisites(m_node, mat_config)

    def _connect_color_channel(self, m_node, renderer, base_name, name_key, common_attr,
                               attr_name, tex,
                               use_full_chain, cc_config, mat_config):
        if use_full_chain and cc_config and cc_config.node_type:
            cc = self.ctx.create_node(cc_config.node_type, 'cc', base_name, name_key)
            lyr = self.ctx.build_layered_node(base_name, name_key)
            self.ctx.connect(tex, "outColor", cc, cc_config.source_connection)
            self.ctx.connect(cc, cc_config.target_connection, lyr, "inputs[1].color")
            self.ctx.connect(lyr, "outColor", m_node, attr_name)
        else:
            self.ctx.connect(tex, "outColor", m_node, attr_name)

        if common_attr == 'subsurfaceColor' and cmds.attributeQuery('ssOn', node=m_node, exists=True):
            cmds.setAttr(f"{m_node}.ssOn", 1)

        weight_common = self._resolve_weight_attr(common_attr)
        if weight_common:
            weight_attr = mat_config.get_maya_attr(weight_common)
            if weight_attr and cmds.attributeQuery(weight_attr, node=m_node, exists=True):
                cmds.setAttr(f"{m_node}.{weight_attr}", 1)

    def _build_color_chain(self, m_node, renderer, base_name, make_tex, mat_config,
                           use_full_chain, input_paths, common_attr, name_key):
        if common_attr not in input_paths:
            return
        attr_name = mat_config.get_maya_attr(common_attr)
        if not attr_name:
            return
        tex = make_tex(common_attr, name_key)
        cc_config = self.config.get_color_correction_config(renderer)
        self._connect_color_channel(
            m_node, renderer, base_name, name_key, common_attr, attr_name, tex,
            use_full_chain, cc_config, mat_config,
        )

    def _build_scalar_chain(self, m_node, base_name, make_tex, mat_config, common_attr,
                            name_key, input_paths, use_full_chain=False, invert=False):
        if common_attr not in input_paths:
            return
        attr_name = mat_config.get_maya_attr(common_attr)
        if not attr_name:
            return

        tex = make_tex(common_attr, name_key, is_alpha=True, invert=invert)

        if use_full_chain:
            ramp = self.ctx.create_node('ramp', 'ramp', base_name, name_key, 'texture')
            self.ctx.connect(tex, "outAlpha", ramp, "vCoord")
            self.ctx.connect(ramp, "outAlpha", m_node, attr_name)
        else:
            node_utils.smart_connect(f"{tex}.outAlpha", f"{m_node}.{attr_name}")

    def _build_bump_normal(self, m_node, renderer, base_name, make_tex, mat_config,
                           use_nrm, channel_options, input_paths):
        bn_config = self.config.get_bump_normal_config(renderer)
        if not bn_config:
            return

        mode = (
            channel_options.get('normal_bump', {}).get('mode')
            or ('normal' if use_nrm else 'bump')
        )
        is_normal = mode == 'normal'
        nb_key = 'nrm' if is_normal else 'bump'
        mapping = bn_config.normal if is_normal else bn_config.bump
        if not mapping:
            return

        target_attr = mat_config.get_maya_attr('normal_bump')
        if not target_attr:
            return

        if 'normal_bump' not in input_paths:
            return

        tex_nb = make_tex('normal_bump', nb_key, is_alpha=not is_normal)

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
        if mapping.is_normal and mapping.is_normal_value is not None:
            cmds.setAttr(f"{bn_node}.{mapping.is_normal}", mapping.is_normal_value)
        if mapping.source_connection:
            self.ctx.connect(tex_nb, mapping.file_source, bn_node, mapping.source_connection)
        if mapping.target_connection:
            self.ctx.connect(bn_node, mapping.target_connection, m_node, target_attr)

    def _build_displacement(self, m_node, sg_node, base_name, make_tex, mat_config,
                            use_full_chain):
        disp_type = mat_config.displacement_node_type
        disp_in = mat_config.displacement_texture
        if not disp_type or not disp_in:
            return

        tex_disp = make_tex('displacementTexture', 'disp', is_alpha=True)
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
