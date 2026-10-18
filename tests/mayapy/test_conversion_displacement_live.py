"""Live displacement conversion.

Native ``displacementShader`` (sentinel) <-> sentinel is a no-op; a renderer with
a real displacement node type (e.g. RedshiftDisplacement) gets a converted node.
The real-node case is skipped generically when no such renderer is installed.
"""

from __future__ import annotations

import unittest

import support

cmds = support.cmds

from core.results import summarize_results


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

    # ------------------------------------------------------------------ #
    # Failure propagation (review finding B01)
    # ------------------------------------------------------------------ #

    def _real_displacement_pair(self):
        """One (source, target) pair crossing renderers where the target uses a real disp node."""
        for tgt in self.configs:
            if tgt.displacement_node_type in ("", "displacementShader"):
                continue
            for src in self.configs:
                if src.node_type == tgt.node_type or src.renderer == tgt.renderer:
                    continue
                if src.displacement_node_type in ("", "displacementShader"):
                    continue
                return src, tgt
        self.skipTest("no available cross-renderer pair with a real displacement node")

    def test_texture_connect_failure_fails_conversion(self):
        src, tgt = self._real_displacement_pair()
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        mat = support.build_material(
            self.loader, src.node_type, "disp_tfail",
            {"displacementTexture": "C:/tex/disp.exr"}, use_full_chain=False)

        original = cmds.connectAttr

        def _connect(s, d, *args, **kwargs):
            if d.endswith("." + tgt.displacement_texture):
                raise RuntimeError("simulated displacement texture failure")
            return original(s, d, *args, **kwargs)

        cmds.connectAttr = _connect
        try:
            result = MaterialConverter(config=self.loader).convert(mat, tgt.node_type)
        finally:
            cmds.connectAttr = original

        self.assertFalse(result.converted, "texture connect failure must fail conversion")
        self.assertIn("displacement", (result.reason or "").lower())

    def test_scale_write_failure_is_a_reported_issue(self):
        src, tgt = self._real_displacement_pair()
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        mat = support.build_material(
            self.loader, src.node_type, "disp_sfail",
            {"displacementTexture": "C:/tex/disp.exr"}, use_full_chain=False)

        original = cmds.setAttr

        def _set_attr(plug, *args, **kwargs):
            if (plug.startswith(mat + "_") and plug.endswith("." + tgt.displacement_scale)):
                raise RuntimeError("simulated locked scale")
            return original(plug, *args, **kwargs)

        cmds.setAttr = _set_attr
        try:
            result = MaterialConverter(config=self.loader).convert(mat, tgt.node_type)
        finally:
            cmds.setAttr = original

        self.assertTrue(result.converted, result.reason)
        self.assertTrue(
            any("displacement scale" in issue for issue in result.issues),
            "a lost scale value must surface as an issue: %r" % (result.issues,))
        self.assertEqual(
            summarize_results([result])["with_issues"], 1)

    def test_source_read_failure_fails_conversion(self):
        src, tgt = self._real_displacement_pair()
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        mat = support.build_material(
            self.loader, src.node_type, "disp_rfail",
            {"displacementTexture": "C:/tex/disp.exr"}, use_full_chain=False)

        original = cmds.listConnections

        def _list(plug, *args, **kwargs):
            if plug.endswith(".displacementShader"):
                raise RuntimeError("simulated scene read failure")
            return original(plug, *args, **kwargs)

        cmds.listConnections = _list
        try:
            result = MaterialConverter(config=self.loader).convert(mat, tgt.node_type)
        finally:
            cmds.listConnections = original

        # A read failure on one SG must not be silently reported as success.
        self.assertFalse(result.converted, "unreadable displacement must fail conversion")
        self.assertIn("displacement", (result.reason or "").lower())
