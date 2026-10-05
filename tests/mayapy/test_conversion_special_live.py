"""Live special-case behaviour: V-Ray glossiness inversion (value + texture),
black-colour weight zeroing, V-Ray emission, and the same-renderer reuse path."""

from __future__ import annotations

import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class ConversionSpecialLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()

    def _require(self, node_type):
        cfg = self.loader.get_material_config(node_type)
        if cfg is None:
            self.skipTest("%s config missing" % node_type)
        return cfg

    def test_vray_glossiness_inverted_in_glossiness_mode(self):
        self._require("VRayMtl")
        self._require("aiStandardSurface")

        cmds.file(new=True, force=True)
        mat = support.create_material("VRayMtl", "ginv_src")
        cmds.setAttr(mat + ".useRoughness", 0)
        cmds.setAttr(mat + ".reflectionGlossiness", 0.2)
        cmds.setAttr(mat + ".coatGlossiness", 0.3)
        cmds.setAttr(mat + ".sheenGlossiness", 0.4)
        cmds.setAttr(mat + ".roughnessAmount", 0.5)

        from core.converter import MaterialConverter
        result = MaterialConverter(config=self.loader).convert(mat, "aiStandardSurface")
        self.assertTrue(result.converted, result.reason)
        target = result.new_material

        self.assertAlmostEqual(cmds.getAttr(target + ".specularRoughness"), 0.8, places=4)
        self.assertAlmostEqual(cmds.getAttr(target + ".coatRoughness"), 0.7, places=4)
        self.assertAlmostEqual(cmds.getAttr(target + ".sheenRoughness"), 0.6, places=4)
        self.assertAlmostEqual(cmds.getAttr(target + ".diffuseRoughness"), 0.5, places=4)

    def test_vray_glossiness_not_inverted_in_roughness_mode(self):
        self._require("VRayMtl")
        self._require("aiStandardSurface")

        cmds.file(new=True, force=True)
        mat = support.create_material("VRayMtl", "grgh_src")
        cmds.setAttr(mat + ".useRoughness", 1)
        cmds.setAttr(mat + ".reflectionGlossiness", 0.2)
        cmds.setAttr(mat + ".coatGlossiness", 0.3)
        cmds.setAttr(mat + ".sheenGlossiness", 0.4)

        from core.converter import MaterialConverter
        result = MaterialConverter(config=self.loader).convert(mat, "aiStandardSurface")
        self.assertTrue(result.converted, result.reason)
        target = result.new_material

        self.assertAlmostEqual(cmds.getAttr(target + ".specularRoughness"), 0.2, places=4)
        self.assertAlmostEqual(cmds.getAttr(target + ".coatRoughness"), 0.3, places=4)
        self.assertAlmostEqual(cmds.getAttr(target + ".sheenRoughness"), 0.4, places=4)

    def test_black_colour_weight_zeroed(self):
        self._require("VRayMtl")
        self._require("aiStandardSurface")

        cmds.file(new=True, force=True)
        mat = support.create_material("VRayMtl", "blk_src")
        cmds.setAttr(mat + ".sheenColor", 0.0, 0.0, 0.0)
        cmds.setAttr(mat + ".sheenColorAmount", 1.0)

        from core.converter import MaterialConverter
        result = MaterialConverter(config=self.loader).convert(mat, "aiStandardSurface")
        self.assertTrue(result.converted, result.reason)
        self.assertAlmostEqual(cmds.getAttr(result.new_material + ".sheen"), 0.0, places=5)

    def test_vray_emission_enables_target_weight(self):
        self._require("VRayMtl")
        self._require("aiStandardSurface")

        cmds.file(new=True, force=True)
        mat = support.create_material("VRayMtl", "emit_src")
        cmds.setAttr(mat + ".illumColor", 1.0, 0.5, 0.25)

        from core.converter import MaterialConverter
        result = MaterialConverter(config=self.loader).convert(mat, "aiStandardSurface")
        self.assertTrue(result.converted, result.reason)
        target = result.new_material
        self.assertAlmostEqual(cmds.getAttr(target + ".emission"), 1.0, places=5)
        color = support.read_plug_value(target + ".emissionColor")
        for got, want in zip(color, (1.0, 0.5, 0.25)):
            self.assertAlmostEqual(float(got), want, places=4)

    def test_same_renderer_reuses_existing_bump_node(self):
        arnold = self.loader.get_material_config("aiStandardSurface")
        arnold_pbr = self.loader.get_material_config("aiOpenPBRSurface")
        if arnold is None or arnold_pbr is None:
            self.skipTest("arnold configs missing")

        cmds.file(new=True, force=True)
        mat = support.build_material(
            self.loader, "aiStandardSurface", "reuse_src",
            {"baseColor": "C:/tex/reuse_base.png",
             "normal_bump": "C:/tex/reuse_nrm.png"},
            channel_options={"normal_bump": {"mode": "normal"}},
        )
        src_bump = support.upstream_plug(mat + ".normalCamera")
        self.assertIsNotNone(src_bump)

        from core.converter import MaterialConverter
        result = MaterialConverter(config=self.loader).convert(mat, "aiOpenPBRSurface")
        self.assertTrue(result.converted, result.reason)
        target = result.new_material

        # same renderer: the existing bump/normal node is reused, not duplicated
        self.assertEqual(support.upstream_plug(target + ".normalCamera"), src_bump)

    def test_vray_target_enables_translucency_mode(self):
        if self.loader.get_material_config("VRayMtl") is None:
            self.skipTest("VRayMtl missing")

        from core.converter import MaterialConverter
        checked = 0
        for cfg in support.available_material_configs(self.loader):
            if cfg.node_type == "VRayMtl":
                continue
            weight_attr = cfg.get_maya_attr("subsurfaceWeight")
            if not weight_attr:
                continue
            with self.subTest(src=cfg.node_type):
                cmds.file(new=True, force=True)
                mat = support.create_material(cfg.node_type, "sss_%s" % cfg.node_type)
                cmds.setAttr("%s.%s" % (mat, weight_attr), 1.0)
                color_attr = cfg.get_maya_attr("subsurfaceColor")
                if color_attr and cmds.objExists("%s.%s" % (mat, color_attr)):
                    cmds.setAttr("%s.%s" % (mat, color_attr), 0.9, 0.4, 0.3)

                result = MaterialConverter(config=self.loader).convert(mat, "VRayMtl")
                self.assertTrue(result.converted, result.reason)
                target = result.new_material
                self.assertEqual(cmds.getAttr(target + ".translucencyMode"), 6,
                                 "translucencyMode (SSS) not enabled")
                self.assertAlmostEqual(cmds.getAttr(target + ".translucencyAmount"), 1.0, places=4)
                checked += 1
        self.assertGreater(checked, 0)

    def test_vray_target_zero_subsurface_weight_stays_off(self):
        if self.loader.get_material_config("VRayMtl") is None:
            self.skipTest("VRayMtl missing")
        cfg = self.loader.get_material_config("aiStandardSurface")
        if cfg is None or not cfg.get_maya_attr("subsurfaceWeight"):
            self.skipTest("arnold subsurface missing")

        cmds.file(new=True, force=True)
        mat = support.create_material("aiStandardSurface", "sss_zero")
        cmds.setAttr(mat + "." + cfg.get_maya_attr("subsurfaceWeight"), 0.0)

        from core.converter import MaterialConverter
        result = MaterialConverter(config=self.loader).convert(mat, "VRayMtl")
        self.assertTrue(result.converted, result.reason)
        self.assertAlmostEqual(cmds.getAttr(result.new_material + ".translucencyAmount"), 0.0, places=4)
