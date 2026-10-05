"""Live prerequisite application (material-level and attribute-level)."""

from __future__ import annotations

import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class PrerequisitesLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()

    def test_material_level_prerequisites(self):
        cfg = self.loader.get_material_config("VRayMtl")
        if cfg is None:
            self.skipTest("VRayMtl missing")
        mat = support.create_material("VRayMtl", "pre_src")
        from core import prerequisites
        prerequisites.apply_prerequisites(mat, cfg)
        self.assertEqual(cmds.getAttr(mat + ".useRoughness"), 1)
        for value in cmds.getAttr(mat + ".reflectionColor")[0]:
            self.assertAlmostEqual(value, 1.0, places=5)

    def test_attribute_level_prerequisites(self):
        loader_renderers = {c.renderer for c in support.available_material_configs(self.loader)}
        if "redshift" not in loader_renderers:
            self.skipTest("redshift4maya not installed")
        cfg = self.loader.get_material_config("RedshiftMaterial")
        mat = support.create_material("RedshiftMaterial", "pre_rs")
        from core import prerequisites
        prerequisites.apply_attr_prerequisites(mat, cfg, "metallic")
        self.assertEqual(cmds.getAttr(mat + ".refl_fresnel_mode"), 2)

    def test_invalid_prerequisite_only_warns(self):
        cfg = self.loader.get_material_config("VRayMtl")
        if cfg is None:
            self.skipTest("VRayMtl missing")
        saved = dict(cfg.prerequisites)
        cfg.prerequisites = {"bad": {"attribute": "definitelyNotAnAttr", "value": 1}}
        try:
            mat = support.create_material("VRayMtl", "pre_bad")
            from core import prerequisites
            prerequisites.apply_prerequisites(mat, cfg)  # must not raise
        finally:
            cfg.prerequisites = saved
