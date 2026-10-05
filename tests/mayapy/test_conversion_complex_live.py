"""Live conversion of complex, Builder-built texture architectures.

Each available source renderer is built with the full Builder pipeline
(``file -> CC -> layeredTexture`` for colour, ``file -> ramp`` for roughness) and
converted to every other renderer; the target chains must be wired and the source
networks must survive untouched.
"""

from __future__ import annotations

import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class ComplexConversionLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()
        cls.configs = support.available_material_configs(cls.loader)

    def test_builder_built_chains_convert_across_renderers(self):
        checked = 0
        for src in self.configs:
            for tgt in self.configs:
                if src.node_type == tgt.node_type:
                    continue
                with self.subTest(src=src.node_type, tgt=tgt.node_type):
                    if self._check(src, tgt):
                        checked += 1
        self.assertGreater(checked, 0)

    def _check(self, src, tgt):
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        mat = support.build_material(
            self.loader, src.node_type, "cx",
            {"baseColor": "C:/tex/cx_base.png",
             "specularRoughness": "C:/tex/cx_rough.png"},
            use_full_chain=True,
        )
        src_base = "%s.%s" % (mat, src.get_maya_attr("baseColor"))
        src_rough = "%s.%s" % (mat, src.get_maya_attr("specularRoughness"))
        self.assertIsNotNone(support.upstream_plug(src_base))
        self.assertIsNotNone(support.upstream_plug(src_rough))

        result = MaterialConverter(config=self.loader).convert(mat, tgt.node_type)
        self.assertTrue(result.converted, result.reason)
        target = result.new_material

        self.assertIsNotNone(support.upstream_plug("%s.%s" % (target, tgt.get_maya_attr("baseColor"))),
                             "target baseColor chain not connected")
        self.assertIsNotNone(support.upstream_plug("%s.%s" % (target, tgt.get_maya_attr("specularRoughness"))),
                             "target roughness chain not connected")

        # source chains preserved
        self.assertIsNotNone(support.upstream_plug(src_base))
        self.assertIsNotNone(support.upstream_plug(src_rough))
        return True

    def test_vray_complex_roughness_chain_inverted_at_target_edge(self):
        vray = self.loader.get_material_config("VRayMtl")
        arnold = self.loader.get_material_config("aiStandardSurface")
        if vray is None or arnold is None:
            self.skipTest("VRayMtl / aiStandardSurface config missing")

        cmds.file(new=True, force=True)
        mat = support.build_material(
            self.loader, "VRayMtl", "cxg",
            {"specularRoughness": "C:/tex/cxg_rough.png"},
            use_full_chain=True,
        )
        cmds.setAttr(mat + ".useRoughness", 0)

        from core.converter import MaterialConverter
        result = MaterialConverter(config=self.loader).convert(mat, "aiStandardSurface")
        self.assertTrue(result.converted, result.reason)
        target = result.new_material

        up = support.upstream_plug("%s.specularRoughness" % target)
        self.assertIsNotNone(up)
        rev = up.split(".")[0]
        self.assertEqual(cmds.nodeType(rev), "reverse")
        # the ramp (source chain) is reused behind the reverse node
        rev_in = support.upstream_plug(rev + ".inputX")
        self.assertEqual(cmds.nodeType(rev_in.split(".")[0]), "ramp")
        # source chain untouched
        self.assertIsNotNone(support.upstream_plug("%s.reflectionGlossiness" % mat))
