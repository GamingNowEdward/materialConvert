"""Live coverage for the core node_utils helpers that the mocked pure suite does
not exercise (identify / create / CC nodes / collect_attribute_info / selection)."""

from __future__ import annotations

import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class NodeUtilsLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()

    def test_identify_node_type(self):
        from core import node_utils

        mat = support.create_material("VRayMtl", "idMat")
        self.assertEqual(node_utils.identify_node_type(mat), "VRayMtl")

    def test_create_target_material_registers_type(self):
        from core import node_utils

        node = node_utils.create_target_material("aiStandardSurface", "madeMat")
        self.assertTrue(cmds.objExists(node))
        self.assertEqual(cmds.nodeType(node), "aiStandardSurface")

    def test_node_name_from_plug(self):
        from core import node_utils

        self.assertEqual(node_utils.node_name_from_plug("file1.outColor"), "file1")
        self.assertEqual(node_utils.node_name_from_plug(""), "")
        self.assertEqual(node_utils.node_name_from_plug(None), "")

    def test_create_cc_node_and_set_params_for_available_renderers(self):
        from core import node_utils

        renderers = {"maya"} | {c.renderer for c in support.available_material_configs(self.loader)}
        for renderer in sorted(renderers):
            cc = self.loader.get_color_correction_config(renderer)
            if not cc or not cc.node_type:
                continue
            with self.subTest(renderer=renderer):
                node = node_utils.create_cc_node(cc, base_name="cc_%s" % renderer)
                self.assertEqual(cmds.nodeType(node), cc.node_type)

                params = {"gamma": 0.5, "contrast": 0.6, "gain": 0.7, "saturation": 0.8}
                node_utils.set_cc_params(node, params, cc)
                for common_name, attr in (("gamma", cc.gamma), ("contrast", cc.contrast),
                                          ("gain", cc.gain), ("saturation", cc.saturation)):
                    if not attr or not cmds.objExists("%s.%s" % (node, attr)):
                        continue
                    if cmds.getAttr("%s.%s" % (node, attr), type=True) not in ("float", "double"):
                        continue
                    self.assertAlmostEqual(
                        float(cmds.getAttr("%s.%s" % (node, attr))),
                        params[common_name], places=5,
                        msg="%s.%s" % (node, attr))

    def test_is_cc_node(self):
        from core import node_utils

        cc_config = self.loader.get_color_correction_config("maya")
        cc = node_utils.create_cc_node(cc_config, base_name="isCcNode")
        self.assertTrue(node_utils.is_cc_node(cc, self.loader))
        mat = support.create_material("aiStandardSurface", "notCcMat")
        self.assertFalse(node_utils.is_cc_node(mat, self.loader))

    def test_collect_attribute_info_value_and_connection(self):
        from core import node_utils

        mat = support.create_material("aiStandardSurface", "collectMat")
        cmds.setAttr(mat + ".metalness", 0.42)
        tex = cmds.shadingNode("file", asTexture=True, name="collectFile")
        cmds.connectAttr(tex + ".outColor", mat + ".specularColor", force=True)

        info = node_utils.collect_attribute_info(mat, ["metalness", "specularColor", "missingAttr"])

        self.assertAlmostEqual(info["metalness"]["value"], 0.42, places=5)
        self.assertIsNone(info["metalness"]["connection"])
        self.assertEqual(info["metalness"]["plug"], mat + ".metalness")
        self.assertEqual(info["specularColor"]["connection"]["plug"], tex + ".outColor")
        self.assertEqual(info["specularColor"]["plug"], mat + ".specularColor")
        # a non-existent plug is reported as present-but-empty, never raises
        self.assertIsNone(info["missingAttr"]["plug"])

    def test_get_displacement_node_from_sg(self):
        from core import node_utils

        sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="dispSG")
        disp = cmds.shadingNode("displacementShader", asShader=True, name="dispNode")
        cmds.connectAttr(disp + ".displacement", sg + ".displacementShader", force=True)
        self.assertEqual(node_utils.get_displacement_node_from_sg(sg), disp)

    def test_get_materials_from_selection_direct(self):
        from core import node_utils

        mat = support.create_material("VRayMtl", "selMat")
        cmds.select(mat, replace=True)
        self.assertIn(mat, node_utils.get_materials_from_selection())

    def test_get_materials_from_selection_via_shape(self):
        from core import node_utils

        cube = cmds.polyCube(name="selCube")[0]
        mat = support.create_material("aiStandardSurface", "shapeMat")
        sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="shapeMatSG")
        cmds.connectAttr(mat + ".outColor", sg + ".surfaceShader", force=True)
        cmds.sets(cube, edit=True, forceElement=sg)
        cmds.select(cube, replace=True)
        self.assertIn(mat, node_utils.get_materials_from_selection())
