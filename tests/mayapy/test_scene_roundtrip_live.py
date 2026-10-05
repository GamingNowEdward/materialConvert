"""Live scene round-trip: build a material, save the scene, reopen it, and convert
the persisted material."""

from __future__ import annotations

import os
import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class SceneRoundTripLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()

    def test_build_save_reopen_convert(self):
        if self.loader.get_material_config("VRayMtl") is None:
            self.skipTest("VRayMtl missing")

        cmds.file(new=True, force=True)
        mat = support.build_material(
            self.loader, "aiStandardSurface", "rt", 
            {"baseColor": "C:/tex/rt_base.png",
             "specularRoughness": "C:/tex/rt_rough.png"},
            use_full_chain=True,
        )

        path = os.path.join(self.temp_dir(), "roundtrip.ma")
        cmds.file(rename=path)
        cmds.file(save=True, type="mayaAscii")

        cmds.file(new=True, force=True)
        self.assertFalse(cmds.objExists(mat))

        cmds.file(path, open=True, force=True)
        self.assertTrue(cmds.objExists(mat))
        self.assertEqual(cmds.nodeType(mat), "aiStandardSurface")
        self.assertIsNotNone(support.upstream_plug(mat + ".baseColor"))

        from core.converter import MaterialConverter
        result = MaterialConverter(config=self.loader).convert(mat, "VRayMtl")
        self.assertTrue(result.converted, result.reason)
