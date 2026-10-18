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

        # Verify the persisted result, not just that "some node exists": the
        # target material must keep its own full chain after a save/reopen.
        target = result.new_material
        vray = self.loader.get_material_config("VRayMtl")
        for common_attr in ("baseColor", "specularRoughness"):
            plug = "%s.%s" % (target, vray.get_maya_attr(common_attr))
            self.assertIsNotNone(support.upstream_plug(plug),
                                 "%s must stay connected" % common_attr)

        done_path = os.path.join(self.temp_dir(), "roundtrip_done.ma")
        cmds.file(rename=done_path)
        cmds.file(save=True, type="mayaAscii")
        cmds.file(new=True, force=True)
        cmds.file(done_path, open=True, force=True)

        self.assertTrue(cmds.objExists(target))
        sgs = cmds.listConnections("%s.outColor" % target, type="shadingEngine") or []
        self.assertTrue(sgs, "target material must stay wired to its shading engine")
        for common_attr in ("baseColor", "specularRoughness"):
            plug = "%s.%s" % (target, vray.get_maya_attr(common_attr))
            self.assertIsNotNone(support.upstream_plug(plug),
                                 "%s must survive save/reopen" % common_attr)
