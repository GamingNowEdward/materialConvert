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
                checked += 1
        self.assertGreater(checked, 0)
