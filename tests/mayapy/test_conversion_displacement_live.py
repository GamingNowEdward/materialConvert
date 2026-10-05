"""Live displacement conversion.

Native ``displacementShader`` (sentinel) <-> sentinel is a no-op; a renderer with
a real displacement node type (e.g. RedshiftDisplacement) gets a converted node.
The real-node case is skipped generically when no such renderer is installed.
"""

from __future__ import annotations

import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class DisplacementLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()
        cls.configs = support.available_material_configs(cls.loader)

    def test_sentinel_to_sentinel_is_noop(self):
        arnold = self.loader.get_material_config("aiStandardSurface")
        vray = self.loader.get_material_config("VRayMtl")
        if arnold is None or vray is None:
            self.skipTest("arnold / vray configs missing")

        cmds.file(new=True, force=True)
        mat = support.create_material("aiStandardSurface", "disp_src")
        sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="disp_srcSG")
        cmds.connectAttr(mat + ".outColor", sg + ".surfaceShader", force=True)
        disp = cmds.shadingNode("displacementShader", asShader=True, name="disp_native")
        cmds.connectAttr(disp + ".displacement", sg + ".displacementShader", force=True)

        from core.converter import MaterialConverter
        result = MaterialConverter(config=self.loader).convert(mat, "VRayMtl")
        self.assertTrue(result.converted, result.reason)
        # both sentinels -> native displacement node on the SG untouched
        self.assertEqual(support.upstream_plug(sg + ".displacementShader"), disp + ".displacement")

    def test_real_displacement_node_conversion(self):
        real_targets = [
            c for c in self.configs
            if c.displacement_node_type not in ("", "displacementShader")
        ]
        if not real_targets:
            self.skipTest("no available renderer with a real displacement node type")

        checked = 0
        for tgt in real_targets:
            for src in self.configs:
                if src.node_type == tgt.node_type:
                    continue
                if src.displacement_node_type in ("", "displacementShader"):
                    # sentinel sources cannot drive a real node on this target
                    continue
                with self.subTest(src=src.node_type, tgt=tgt.node_type):
                    cmds.file(new=True, force=True)
                    mat = support.build_material(
                        self.loader, src.node_type, "dispc",
                        {"displacementTexture": "C:/tex/disp.exr"},
                        use_full_chain=False,
                    )
                    from core.converter import MaterialConverter
                    result = MaterialConverter(config=self.loader).convert(mat, tgt.node_type)
                    self.assertTrue(result.converted, result.reason)
                    nodes = cmds.ls(type=tgt.displacement_node_type) or []
                    self.assertTrue(nodes, "no %s created" % tgt.displacement_node_type)
                    checked += 1
        self.assertGreater(checked, 0)
