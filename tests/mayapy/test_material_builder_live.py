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

    def test_full_chain_ramp_responds_to_vcoord(self):
        """A full-chain scalar ramp must not output a constant value."""
        cfg = self.loader.get_material_config("aiStandardSurface")
        if cfg is None:
            self.skipTest("arnold config missing")
        cmds.file(new=True, force=True)
        mat = support.build_material(self.loader, "aiStandardSurface", "rampchk",
                                     {"specularRoughness": "C:/tex/r.png"},
                                     use_full_chain=True)
        attr = cfg.get_maya_attr("specularRoughness")
        ramp = None
        for node in cmds.ls(type="ramp") or []:
            if cmds.isConnected(node + ".outAlpha", "%s.%s" % (mat, attr)):
                ramp = node
                break
        self.assertIsNotNone(ramp, "no ramp drives the roughness channel")
        self.assertGreaterEqual(cmds.getAttr(ramp + ".colorEntryList", size=True), 2)

        # Drive vCoord directly (drop the texture feed) and read the ramp output.
        src = support.upstream_plug(ramp + ".vCoord")
        if src:
            cmds.disconnectAttr(src, ramp + ".vCoord")
        samples = {}
        for v in (0.0, 0.5, 1.0):
            cmds.setAttr(ramp + ".vCoord", v)
            samples[v] = round(cmds.getAttr(ramp + ".outAlpha"), 5)
        self.assertEqual(samples[0.0], 0.0)
        self.assertEqual(samples[1.0], 1.0)
        self.assertAlmostEqual(samples[0.5], 0.5, places=4)

    def test_full_chain_only_applies_to_roughness(self):
        """The Full chain toggle applies to specularRoughness only;
        metallic / opacity stay direct passthroughs (no ramp node)."""
        cfg = self.loader.get_material_config("aiStandardSurface")
        if cfg is None:
            self.skipTest("arnold config missing")
        cmds.file(new=True, force=True)
        paths = {"specularRoughness": "C:/tex/r.png",
                 "metallic": "C:/tex/m.png", "opacity": "C:/tex/o.png"}
        mat = support.build_material(self.loader, "aiStandardSurface", "fullsc",
                                     paths, use_full_chain=True)

        rough_up = support.upstream_plug("%s.%s" % (mat, cfg.get_maya_attr("specularRoughness")))
        self.assertIsNotNone(rough_up, "specularRoughness not connected")
        self.assertEqual(cmds.nodeType(rough_up.split(".")[0]), "ramp",
                         "specularRoughness should go through the ramp")

        for common in ("metallic", "opacity"):
            up = support.upstream_plug("%s.%s" % (mat, cfg.get_maya_attr(common)))
            self.assertIsNotNone(up, "%s not connected" % common)
            self.assertNotEqual(cmds.nodeType(up.split(".")[0]), "ramp",
                                "%s must stay a direct passthrough" % common)

    def test_material_level_prerequisites_applied(self):
        cfg = self.loader.get_material_config("VRayMtl")
        if cfg is None:
            self.skipTest("VRayMtl missing")
        cmds.file(new=True, force=True)
        mat = support.build_material(self.loader, "VRayMtl", "prq",
                                     {"baseColor": "C:/tex/prq.png"}, use_full_chain=False)
        self.assertEqual(cmds.getAttr(mat + ".useRoughness"), 1)

    def test_build_is_a_single_undo_step(self):
        if self.loader.get_material_config("aiStandardSurface") is None:
            self.skipTest("arnold config missing")
        cmds.file(new=True, force=True)
        from core.builder_context import BuilderContext
        from core.material_builder import MaterialBuilder

        ctx = BuilderContext(config_loader=self.loader)
        mat = MaterialBuilder(ctx, config=self.loader).build(
            "aiStandardSurface", "undo_b",
            {"baseColor": "C:/tex/undo.png", "specularRoughness": "C:/tex/undo_r.png"},
            use_qss=True, use_full_chain=False)
        self.assertTrue(cmds.objExists(mat))
        cmds.undo()  # a single build wraps everything in one undo chunk
        self.assertFalse(cmds.objExists(mat))
