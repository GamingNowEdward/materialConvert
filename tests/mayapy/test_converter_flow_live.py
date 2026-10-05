"""Live converter flow: shading-engine rewiring, result semantics, batch
conversion (undo chunk, progress callback, failure isolation)."""

from __future__ import annotations

import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class ConverterFlowLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()

    def _require(self, node_type):
        if self.loader.get_material_config(node_type) is None:
            self.skipTest("%s config missing" % node_type)

    def test_reconnects_shading_engine(self):
        self._require("aiStandardSurface")
        self._require("VRayMtl")

        cmds.file(new=True, force=True)
        mat = support.create_material("aiStandardSurface", "flow_src")
        sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="flow_srcSG")
        cmds.connectAttr(mat + ".outColor", sg + ".surfaceShader", force=True)

        from core.converter import MaterialConverter
        result = MaterialConverter(config=self.loader).convert(mat, "VRayMtl")

        self.assertTrue(result.created)
        self.assertTrue(result.converted)
        self.assertEqual(result.wired, 1)
        self.assertEqual(result.total_sgs, 1)
        self.assertEqual(support.upstream_plug(sg + ".surfaceShader"), result.new_material + ".outColor")

    def test_material_without_shading_engine_still_converts(self):
        self._require("aiStandardSurface")
        self._require("VRayMtl")

        cmds.file(new=True, force=True)
        mat = support.create_material("aiStandardSurface", "free_src")
        from core.converter import MaterialConverter
        result = MaterialConverter(config=self.loader).convert(mat, "VRayMtl")
        self.assertTrue(result.converted)
        self.assertEqual(result.total_sgs, 0)
        self.assertEqual(result.wired, 0)

    def test_convert_all_progress_and_order(self):
        self._require("aiStandardSurface")
        self._require("VRayMtl")

        cmds.file(new=True, force=True)
        mats = [support.create_material("aiStandardSurface", "batch%d" % i) for i in (1, 2)]
        progress = []
        from core.converter import MaterialConverter
        results = MaterialConverter(config=self.loader).convert_all(
            mats, "VRayMtl", on_progress=lambda done, total, res: progress.append((done, total)))

        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.converted for r in results))
        self.assertEqual(progress, [(1, 2), (2, 2)])

    def test_convert_all_isolates_missing_material(self):
        self._require("aiStandardSurface")
        self._require("VRayMtl")

        cmds.file(new=True, force=True)
        good = support.create_material("aiStandardSurface", "good_src")
        from core.converter import MaterialConverter
        results = MaterialConverter(config=self.loader).convert_all([good, "does_not_exist"], "VRayMtl")

        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].converted)
        self.assertFalse(results[1].converted)
        self.assertTrue(results[1].reason)
