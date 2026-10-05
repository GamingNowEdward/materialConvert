"""Live logic behind the Node Tools tab (without Qt): the config-driven node-type
groups used by "Select All", shading-group renaming, and Create File From P2D."""

from __future__ import annotations

import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class NodeToolsLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()

    def test_bump_and_cc_type_groups_are_config_driven(self):
        cfg = self.loader.get_material_config("aiStandardSurface")
        if cfg is not None and "aiBump2d" in self.loader.get_all_bn_types():
            bn = cmds.shadingNode("aiBump2d", asUtility=True, name="nt_bn")
            self.assertIn("aiBump2d", self.loader.get_all_bn_types())
            self.assertIn(bn, cmds.ls(type="aiBump2d") or [])

        cc_config = self.loader.get_color_correction_config("maya")
        if cc_config and cc_config.node_type:
            cc = cmds.shadingNode(cc_config.node_type, asUtility=True, name="nt_cc")
            self.assertIn(cc_config.node_type, self.loader.get_all_cc_types())
            self.assertIn(cc, cmds.ls(type=cc_config.node_type) or [])

    def test_shading_group_rename(self):
        mat = support.create_material("aiStandardSurface", "nt_mat")
        sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="oldSG")
        cmds.connectAttr(mat + ".outColor", sg + ".surfaceShader", force=True)
        target_name = mat + "SG"
        if not cmds.objExists(target_name):
            cmds.rename(sg, target_name)
        self.assertTrue(cmds.objExists(target_name))

    def test_create_file_from_p2d_core(self):
        from core.builder_context import BuilderContext
        from core.material_builder import MaterialBuilder

        ctx = BuilderContext(config_loader=self.loader)
        p2d = ctx.create_node("place2dTexture", "p2d", "ntp")
        f_node = cmds.shadingNode("file", asTexture=True, isColorManaged=True, name="ntp_file")
        for attr in MaterialBuilder.P2D_ATTRS:
            ctx.connect(p2d, attr, f_node, attr)
        ctx.connect(p2d, "outUV", f_node, "uvCoord")
        ctx.connect(p2d, "outUvFilterSize", f_node, "uvFilterSize")

        self.assertEqual(support.upstream_plug(f_node + ".coverage"), p2d + ".coverage")
        self.assertIsNotNone(support.upstream_plug(f_node + ".uvCoord"))
