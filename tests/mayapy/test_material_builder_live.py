"""Live MaterialBuilder: every renderer builds every supported channel (full and
simple chain), quick-select set naming, and prerequisites."""

from __future__ import annotations

import unittest

import support

cmds = support.cmds

COLOR_OR_SCALAR = (
    "baseColor", "subsurfaceColor", "specularRoughness", "metallic", "opacity",
    "emissionColor", "transmissionColor", "fuzzColor", "specularColor",
)


@unittest.skipIf(cmds is None, "mayapy required")
class MaterialBuilderLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()
        cls.configs = support.available_material_configs(cls.loader)

    def _paths_for(self, cfg):
        paths = {c: "C:/tex/b_%s.png" % c for c in COLOR_OR_SCALAR if cfg.get_maya_attr(c)}
        if cfg.get_maya_attr("normal_bump"):
            paths["normal_bump"] = "C:/tex/b_nrm.png"
        return paths

    def test_build_all_channels_full_chain(self):
        for cfg in self.configs:
            with self.subTest(material=cfg.node_type):
                cmds.file(new=True, force=True)
                from core.builder_context import BuilderContext
                from core.material_builder import MaterialBuilder
                ctx = BuilderContext(config_loader=self.loader)
                mat = MaterialBuilder(ctx, config=self.loader).build(
                    cfg.node_type, "bld", self._paths_for(cfg),
                    use_qss=True, use_full_chain=True)

                self.assertEqual(cmds.nodeType(mat), cfg.node_type)
                for common in self._paths_for(cfg):
                    plug = "%s.%s" % (mat, cfg.get_maya_attr(common))
                    self.assertIsNotNone(support.upstream_plug(plug),
                                         "%s.%s not connected" % (mat, cfg.get_maya_attr(common)))
                self.assertTrue(cmds.objExists("QS_" + mat), "quick select set missing")

    def test_build_simple_chain(self):
        for cfg in self.configs:
            with self.subTest(material=cfg.node_type):
                cmds.file(new=True, force=True)
                paths = {c: "C:/tex/s_%s.png" % c
                         for c in ("baseColor", "specularRoughness") if cfg.get_maya_attr(c)}
                mat = support.build_material(self.loader, cfg.node_type, "smp", paths,
                                             use_full_chain=False)
                self.assertEqual(cmds.nodeType(mat), cfg.node_type)
                for common in paths:
                    self.assertIsNotNone(support.upstream_plug("%s.%s" % (mat, cfg.get_maya_attr(common))))

    def test_material_level_prerequisites_applied(self):
        cfg = self.loader.get_material_config("VRayMtl")
        if cfg is None:
            self.skipTest("VRayMtl missing")
        cmds.file(new=True, force=True)
        mat = support.build_material(self.loader, "VRayMtl", "prq",
                                     {"baseColor": "C:/tex/prq.png"}, use_full_chain=False)
        self.assertEqual(cmds.getAttr(mat + ".useRoughness"), 1)
