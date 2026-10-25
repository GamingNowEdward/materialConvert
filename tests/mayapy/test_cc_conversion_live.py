"""Live colour-correction chain conversion.

Builds a source material whose mapped colour attribute is driven by
``file -> source CC -> material`` (and, for the restore case, a non-material
downstream sink), converts it, and asserts the target renderer's CC node is
created and wired while the source chain stays intact.
"""

from __future__ import annotations

import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class CCConversionLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()
        cls.configs = support.available_material_configs(cls.loader)

    def _pairs(self):
        for src in self.configs:
            if not self.loader.get_color_correction_config(src.renderer).node_type:
                continue
            for tgt in self.configs:
                if tgt.node_type != src.node_type:
                    yield src, tgt

    def _setup(self, src, tgt, common_attr, name):
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        cc_cfg = self.loader.get_color_correction_config(src.renderer)
        attr = src.get_maya_attr(common_attr)
        mat = support.create_material(src.node_type, name + "_src")
        tex = cmds.shadingNode("file", asTexture=True, name=name + "_tex")
        cc = cmds.shadingNode(cc_cfg.node_type, asUtility=True, name=name + "_cc")
        cmds.connectAttr(tex + ".outColor", "%s.%s" % (cc, cc_cfg.input), force=True)
        cmds.connectAttr("%s.%s" % (cc, cc_cfg.output), "%s.%s" % (mat, attr), force=True)
        result = MaterialConverter(config=self.loader).convert(mat, tgt.node_type)
        return mat, cc, result

    def test_cc_chain_converted_and_source_kept(self):
        checked = 0
        for src, tgt in self._pairs():
            with self.subTest(src=src.node_type, tgt=tgt.node_type):
                mat, cc, result = self._setup(src, tgt, "baseColor", "ccBasic")
                self.assertTrue(result.converted, result.reason)
                target = result.new_material
                tgt_attr = tgt.get_maya_attr("baseColor")
                tgt_cc_type = self.loader.get_color_correction_config(tgt.renderer).node_type

                upstream = support.upstream_plug("%s.%s" % (target, tgt_attr))
                self.assertIsNotNone(upstream, "target baseColor not connected")
                self.assertEqual(cmds.nodeType(upstream.split(".")[0]), tgt_cc_type)

                # source material keeps its original CC chain
                src_cfg = self.loader.get_color_correction_config(src.renderer)
                src_attr = src.get_maya_attr("baseColor")
                src_up = support.upstream_plug("%s.%s" % (mat, src_attr))
                self.assertEqual(src_up, "%s.%s" % (cc, src_cfg.output))
                checked += 1
        self.assertGreater(checked, 0)

    def test_shared_source_cc_reused_for_two_channels(self):
        # Only cross-renderer pairs convert (and cache) CC nodes.
        checked = 0
        for src, tgt in self._pairs():
            if src.renderer == tgt.renderer:
                continue
            with self.subTest(src=src.node_type, tgt=tgt.node_type):
                cmds.file(new=True, force=True)
                cc_cfg = self.loader.get_color_correction_config(src.renderer)
                mat = support.create_material(src.node_type, "ccReuse_src")
                tex = cmds.shadingNode("file", asTexture=True, name="ccReuse_tex")
                cc = cmds.shadingNode(cc_cfg.node_type, asUtility=True, name="ccReuse_cc")
                cmds.connectAttr(tex + ".outColor", "%s.%s" % (cc, cc_cfg.input), force=True)
                for common in ("baseColor", "specularColor"):
                    attr = src.get_maya_attr(common)
                    cmds.connectAttr("%s.%s" % (cc, cc_cfg.output), "%s.%s" % (mat, attr), force=True)

                from core.converter import MaterialConverter
                result = MaterialConverter(config=self.loader).convert(mat, tgt.node_type)
                self.assertTrue(result.converted, result.reason)
                target = result.new_material
                tgt_cc_type = self.loader.get_color_correction_config(tgt.renderer).node_type

                created = cmds.ls(type=tgt_cc_type) or []
                self.assertEqual(len(created), 1,
                                 "shared source CC should convert once, got %r" % created)
                for common in ("baseColor", "specularColor"):
                    up = support.upstream_plug("%s.%s" % (target, tgt.get_maya_attr(common)))
                    self.assertEqual(up.split(".")[0], created[0])
                checked += 1
        self.assertGreater(checked, 0)

    def test_non_material_downstream_restores_source_chain(self):
        checked = 0
        for src, tgt in self._pairs():
            if src.renderer == tgt.renderer:
                continue
            with self.subTest(src=src.node_type, tgt=tgt.node_type):
                cmds.file(new=True, force=True)
                cc_cfg = self.loader.get_color_correction_config(src.renderer)
                mat = support.create_material(src.node_type, "ccSink_src")
                tex = cmds.shadingNode("file", asTexture=True, name="ccSink_tex")
                cc = cmds.shadingNode(cc_cfg.node_type, asUtility=True, name="ccSink_cc")
                sink = cmds.shadingNode("layeredTexture", asTexture=True, name="ccSink_lyr")
                cmds.connectAttr(tex + ".outColor", "%s.%s" % (cc, cc_cfg.input), force=True)
                cmds.connectAttr("%s.%s" % (cc, cc_cfg.output), sink + ".inputs[0].color", force=True)
                attr = src.get_maya_attr("baseColor")
                cmds.connectAttr("%s.%s" % (cc, cc_cfg.output), "%s.%s" % (mat, attr), force=True)

                from core.converter import MaterialConverter
                result = MaterialConverter(config=self.loader).convert(mat, tgt.node_type)
                self.assertTrue(result.converted, result.reason)

                # source material attribute must be re-pointed at its own CC
                src_up = support.upstream_plug("%s.%s" % (mat, attr))
                self.assertEqual(src_up, "%s.%s" % (cc, cc_cfg.output))

                # the target material channel must be wired as well, not
                # just the source chain restored.
                tgt_up = support.upstream_plug(
                    "%s.%s" % (result.new_material, tgt.get_maya_attr("baseColor")))
                self.assertIsNotNone(tgt_up, "target baseColor not connected")
                checked += 1
        self.assertGreater(checked, 0)

    def _cc_has_out_alpha(self, renderer):
        """Whether the renderer's CC node exposes ``outAlpha`` (float output)."""
        cc_cfg = self.loader.get_color_correction_config(renderer)
        if not cc_cfg or not cc_cfg.node_type:
            return False
        node = cmds.shadingNode(cc_cfg.node_type, asUtility=True)
        try:
            return cmds.attributeQuery("outAlpha", node=node, exists=True)
        finally:
            cmds.delete(node)

    def test_cc_out_alpha_drives_scalar_channel(self):
        """A CC driving a float channel must connect through outAlpha."""
        checked = 0
        for src, tgt in self._pairs():
            if src.renderer == tgt.renderer:
                continue
            # The scenario only exists when both CC nodes expose a float output.
            if not self._cc_has_out_alpha(src.renderer):
                continue
            if not self._cc_has_out_alpha(tgt.renderer):
                continue
            src_attr = src.get_maya_attr("metallic")
            tgt_attr = tgt.get_maya_attr("metallic")
            if not src_attr or not tgt_attr:
                continue
            with self.subTest(src=src.node_type, tgt=tgt.node_type):
                cmds.file(new=True, force=True)
                cc_cfg = self.loader.get_color_correction_config(src.renderer)
                mat = support.create_material(src.node_type, "ccAlpha_src")
                tex = cmds.shadingNode("file", asTexture=True, name="ccAlpha_tex")
                cc = cmds.shadingNode(cc_cfg.node_type, asUtility=True, name="ccAlpha_cc")
                cmds.connectAttr(tex + ".outColor", "%s.%s" % (cc, cc_cfg.input), force=True)
                # outColor (float3) cannot drive a float attribute: outAlpha is
                # the only viable slot, exactly as in the reported bug.
                cmds.connectAttr("%s.outAlpha" % cc, "%s.%s" % (mat, src_attr), force=True)

                from core.converter import MaterialConverter
                result = MaterialConverter(config=self.loader).convert(mat, tgt.node_type)
                self.assertTrue(result.converted, result.reason)

                up = support.upstream_plug("%s.%s" % (result.new_material, tgt_attr))
                self.assertIsNotNone(up, "target metallic not connected")
                self.assertTrue(up.endswith(".outAlpha"),
                                "scalar channel must be driven by outAlpha, got %r" % up)
                checked += 1
        self.assertGreater(checked, 0)

    # ------------------------------------------------------------------ #
    # Shared intermediate node between the source CC and the material
    # ------------------------------------------------------------------ #

    def _layer_snapshot(self, node):
        """Topology + non-default parameters of a layeredTexture."""
        inputs = {}
        for index in range(2):
            color = "%s.inputs[%d].color" % (node, index)
            inputs[index] = (
                support.upstream_plug(color),
                tuple(round(v, 5) for v in cmds.getAttr(color)[0]),
                cmds.getAttr("%s.inputs[%d].blendMode" % (node, index)),
            )
        return {
            "inputs": inputs,
            "out": support.upstream_plug("%s.outColor" % node),
        }

    def test_shared_layered_chain_is_copied_not_rewritten(self):
        """Source CC driving the material through a layeredTexture: source graph untouched."""
        checked = 0
        for src, tgt in self._pairs():
            if src.renderer == tgt.renderer:
                continue
            with self.subTest(src=src.node_type, tgt=tgt.node_type):
                cmds.file(new=True, force=True)
                cc_cfg = self.loader.get_color_correction_config(src.renderer)
                mat = support.create_material(src.node_type, "ccLyr_src")
                tex = cmds.shadingNode("file", asTexture=True, name="ccLyr_tex")
                cc = cmds.shadingNode(cc_cfg.node_type, asUtility=True, name="ccLyr_cc")
                lyr = cmds.shadingNode("layeredTexture", asTexture=True, name="ccLyr_lyr")
                cmds.setAttr(lyr + ".inputs[0].color", 0.25, 0.5, 0.75, type="double3")
                cmds.setAttr(lyr + ".inputs[1].color", 0.1, 0.2, 0.3, type="double3")
                cmds.setAttr(lyr + ".inputs[1].blendMode", 4)
                cmds.connectAttr(tex + ".outColor", "%s.%s" % (cc, cc_cfg.input), force=True)
                cmds.connectAttr("%s.%s" % (cc, cc_cfg.output), lyr + ".inputs[0].color", force=True)
                attr = src.get_maya_attr("baseColor")
                cmds.connectAttr("%s.outColor" % lyr, "%s.%s" % (mat, attr), force=True)
                before = self._layer_snapshot(lyr)

                from core.converter import MaterialConverter
                result = MaterialConverter(config=self.loader).convert(mat, tgt.node_type)
                self.assertTrue(result.converted, result.reason)

                # 1. the source sub-graph is byte-for-byte identical
                self.assertEqual(support.upstream_plug("%s.%s" % (mat, attr)), "%s.outColor" % lyr)
                self.assertEqual(
                    support.upstream_plug(lyr + ".inputs[0].color"),
                    "%s.%s" % (cc, cc_cfg.output))
                self.assertEqual(self._layer_snapshot(lyr), before)

                # 2. the target reads a copy, not the shared source node
                tgt_up = support.upstream_plug(
                    "%s.%s" % (result.new_material, tgt.get_maya_attr("baseColor")))
                self.assertIsNotNone(tgt_up, "target baseColor not connected")
                copy = tgt_up.split(".")[0]
                self.assertNotEqual(copy, lyr, "target must not share the source layeredTexture")
                self.assertEqual(cmds.nodeType(copy), "layeredTexture")

                # 3. the copy is driven by the new CC and keeps the layer parameters
                copy_in = support.upstream_plug(copy + ".inputs[0].color")
                self.assertIsNotNone(copy_in)
                tgt_cc_type = self.loader.get_color_correction_config(tgt.renderer).node_type
                self.assertEqual(cmds.nodeType(copy_in.split(".")[0]), tgt_cc_type)
                self.assertEqual(tuple(round(v, 5) for v in cmds.getAttr(copy + ".inputs[1].color")[0]),
                                 (0.1, 0.2, 0.3))
                self.assertEqual(cmds.getAttr(copy + ".inputs[1].blendMode"), 4)
                checked += 1
        self.assertGreater(checked, 0)

    def test_multi_hop_chain_is_reported_and_source_kept(self):
        """A two-level intermediate chain must be reported explicitly, source untouched."""
        checked = 0
        for src, tgt in self._pairs():
            if src.renderer == tgt.renderer:
                continue
            with self.subTest(src=src.node_type, tgt=tgt.node_type):
                cmds.file(new=True, force=True)
                cc_cfg = self.loader.get_color_correction_config(src.renderer)
                mat = support.create_material(src.node_type, "ccHop_src")
                tex = cmds.shadingNode("file", asTexture=True, name="ccHop_tex")
                cc = cmds.shadingNode(cc_cfg.node_type, asUtility=True, name="ccHop_cc")
                mid1 = cmds.shadingNode("layeredTexture", asTexture=True, name="ccHop_lyr")
                mid2 = cmds.shadingNode("multiplyDivide", asUtility=True, name="ccHop_md")
                cmds.connectAttr(tex + ".outColor", "%s.%s" % (cc, cc_cfg.input), force=True)
                cmds.connectAttr("%s.%s" % (cc, cc_cfg.output), mid1 + ".inputs[0].color", force=True)
                cmds.connectAttr(mid1 + ".outColor", mid2 + ".input1", force=True)
                attr = src.get_maya_attr("baseColor")
                cmds.connectAttr(mid2 + ".output", "%s.%s" % (mat, attr), force=True)
                src_before = support.upstream_plug("%s.%s" % (mat, attr))

                from core.converter import MaterialConverter
                result = MaterialConverter(config=self.loader).convert(mat, tgt.node_type)
                self.assertTrue(result.converted, result.reason)
                self.assertTrue(
                    any("multi-hop" in issue for issue in result.issues),
                    "unsupported CC chain must be reported: %r" % (result.issues,))
                # source untouched
                self.assertEqual(support.upstream_plug("%s.%s" % (mat, attr)), src_before)
                self.assertEqual(
                    support.upstream_plug(mid1 + ".inputs[0].color"),
                    "%s.%s" % (cc, cc_cfg.output))
                checked += 1
        self.assertGreater(checked, 0)
