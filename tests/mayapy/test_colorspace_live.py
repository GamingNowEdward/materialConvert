"""Live Colorspace matcher: filename and channel drivers on real file nodes,
applying matched colours, ignore-file-rules. Assertions stay generic so they hold
for whatever OCIO config the machine has (the user's config may vary)."""

from __future__ import annotations

import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class ColorspaceLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()

    def _matcher(self):
        from core.colorspace import ColorSpaceMatcher
        return ColorSpaceMatcher(config_loader=self.loader)

    def test_name_driver_matches_filename_roles(self):
        cmds.file(new=True, force=True)
        albedo = cmds.shadingNode("file", asTexture=True, name="cs_albedo")
        cmds.setAttr(albedo + ".fileTextureName", "C:/tex/hero_albedo.png", type="string")
        rough = cmds.shadingNode("file", asTexture=True, name="cs_rough")
        cmds.setAttr(rough + ".fileTextureName", "C:/tex/hero_roughness.png", type="string")

        results = {r.file_node: r for r in self._matcher().scan()}
        self.assertIn("srgb", results[albedo].name_driver_result.roles)
        self.assertIn("raw", results[rough].name_driver_result.roles)

    def test_channel_driver_uses_real_connections(self):
        cmds.file(new=True, force=True)
        mat = support.create_material("aiStandardSurface", "cs_mat")
        tex = cmds.shadingNode("file", asTexture=True, name="cs_chan")
        cmds.connectAttr(tex + ".outColor", mat + ".baseColor", force=True)

        results = {r.file_node: r for r in self._matcher().scan()}
        self.assertIn("srgb", results[tex].channel_driver_result.roles)

    def test_apply_matched_only_sets_matched(self):
        from core.colorspace import MatchState
        cmds.file(new=True, force=True)
        tex = cmds.shadingNode("file", asTexture=True, name="cs_apply")
        cmds.setAttr(tex + ".fileTextureName", "C:/tex/body_albedo.png", type="string")

        matcher = self._matcher()
        results = matcher.scan()
        outcome = matcher.apply_matched(results)

        result = results[0]
        if result.state == MatchState.MATCHED and result.prematch_colorspace:
            self.assertEqual(cmds.getAttr(tex + ".colorSpace"), result.prematch_colorspace)
        else:
            self.assertEqual(outcome["applied"], [])

    def test_ignore_color_space_file_rules(self):
        cmds.file(new=True, force=True)
        a = cmds.shadingNode("file", asTexture=True, name="cs_ign_a")
        b = cmds.shadingNode("file", asTexture=True, name="cs_ign_b")
        outcome = self._matcher().ignore_color_space_file_rules()
        self.assertEqual(set(outcome["nodes"]), {a, b})
        self.assertFalse(outcome["failed"])
        for node in (a, b):
            self.assertEqual(cmds.getAttr(node + ".ignoreColorSpaceFileRules"), 1)
