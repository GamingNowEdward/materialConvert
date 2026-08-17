import maya.cmds as cmds

from core.builder_context import BuilderContext
from core.config_loader import ConfigLoader


class MaterialBuilder:

    P2D_ATTRS = ['coverage', 'translateFrame', 'rotateFrame', 'mirrorU', 'mirrorV',
                 'stagger', 'wrapU', 'wrapV', 'repeatUV', 'offset', 'rotateUV', 'noiseUV']

    CHANNEL_COMMON_ATTRS = {
        "color": "baseColor",
        "rough": "specularRoughness",
        "sss": "subsurfaceColor",
        "nrm": "normal_bump",
        "bump": "normal_bump",
    }

    def __init__(self, ctx: BuilderContext):
        self.ctx = ctx
        self.config = ConfigLoader()

    def build(self, node_type, base_name, input_paths, use_nrm=True, use_sss=False, use_disp=False,
              use_qss=True):
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

        def make_tex(key, is_alpha=False):
            f = self.ctx.create_node('file', 'file', base_name, key, 'texture')
            if is_alpha:
                cmds.setAttr(f"{f}.alphaIsLuminance", 1)
            path = input_paths.get(key, "")
            if path:
                cmds.setAttr(f"{f}.fileTextureName", path, type="string")
            for attr in self.P2D_ATTRS:
                self.ctx.connect(p2d, attr, f, attr)
            self.ctx.connect(p2d, "outUV", f, "uvCoord")
            self.ctx.connect(p2d, "outUvFilterSize", f, "uvFilterSize")
            return f

        self._build_color_chain(m_node, renderer, base_name, make_tex, mat_config, use_sss)
        self._build_rough_chain(m_node, base_name, make_tex, mat_config)
        self._build_bump_normal(m_node, renderer, base_name, make_tex, mat_config, use_nrm)
        if use_disp:
            self._build_displacement(m_node, sg_node, base_name, make_tex, mat_config)

        qss_nodes = list(self.ctx._current_build_nodes)
        if use_qss and qss_nodes:
            cmds.sets(qss_nodes, name=f"{self.ctx.get_naming()['qss_prefix']}{base_name}")

        cmds.select(m_node)
        return m_node

    def _apply_material_prereqs(self, m_node, mat_config):
        for prereq_info in mat_config.get_prerequisites().values():
            attr = prereq_info.get("attribute", "")
            value = prereq_info.get("value", None)
            if attr and value is not None and cmds.attributeQuery(attr, node=m_node, exists=True):
                cmds.setAttr(f"{m_node}.{attr}", value)

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
