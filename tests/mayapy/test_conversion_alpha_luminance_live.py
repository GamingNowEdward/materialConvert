"""Live alphaIsLuminance behaviour, including the regression where the recursive
trace used to wander across material networks."""

from __future__ import annotations

import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class AlphaLuminanceLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()

    def _convert(self, mat, target):
        from core.converter import MaterialConverter
        result = MaterialConverter(config=self.loader).convert(mat, target)
        self.assertTrue(result.converted, result.reason)
        return result.new_material

    def test_enabled_for_roughness_alpha_through_invert(self):
        if self.loader.get_material_config("VRayMtl") is None:
            self.skipTest("VRayMtl missing")
        cmds.file(new=True, force=True)
        mat = support.create_material("VRayMtl", "alpha_src")
        cmds.setAttr(mat + ".useRoughness", 0)
        tex = cmds.shadingNode("file", asTexture=True, name="alpha_tex")
        cmds.setAttr(tex + ".fileTextureName", "C:/tex/alpha.png", type="string")
        cmds.connectAttr(tex + ".outAlpha", mat + ".reflectionGlossiness", force=True)

        self._convert(mat, "aiStandardSurface")
        self.assertTrue(cmds.getAttr(tex + ".alphaIsLuminance"))

    def test_opacity_channel_is_exempt(self):
        if self.loader.get_material_config("aiOpenPBRSurface") is None:
            self.skipTest("aiOpenPBRSurface missing")
        cmds.file(new=True, force=True)
        mat = support.create_material("aiStandardSurface", "opac_src")
        tex = cmds.shadingNode("file", asTexture=True, name="opac_tex")
        cmds.setAttr(tex + ".fileTextureName", "C:/tex/opac.png", type="string")
        # float3 opacity source -> the float target opacity is wired through outAlpha
        cmds.connectAttr(tex + ".outColor", mat + ".opacity", force=True)

        self._convert(mat, "aiOpenPBRSurface")
        # opacity is exempt from the luminance fix even though outAlpha is used
        self.assertFalse(cmds.getAttr(tex + ".alphaIsLuminance"))

    def test_two_materials_do_not_cross_contaminate(self):
        if self.loader.get_material_config("VRayMtl") is None:
            self.skipTest("VRayMtl missing")
        cmds.file(new=True, force=True)

        materials = []
        textures = []
        for index in (1, 2):
            mat = support.create_material("VRayMtl", "xmat%d" % index)
            cmds.setAttr(mat + ".useRoughness", 0)
            tex = cmds.shadingNode("file", asTexture=True, name="xtex%d" % index)
            cmds.setAttr(tex + ".fileTextureName", "C:/tex/x%d.png" % index, type="string")
            cmds.connectAttr(tex + ".outAlpha", mat + ".reflectionGlossiness", force=True)
            materials.append(mat)
            textures.append(tex)

        from core.converter import MaterialConverter
        converter = MaterialConverter(config=self.loader)
        targets = [converter.convert(mat, "aiStandardSurface").new_material for mat in materials]

        for target, tex in zip(targets, textures):
            up = support.upstream_plug(target + ".specularRoughness")
            self.assertEqual(cmds.nodeType(up.split(".")[0]), "reverse")
            self.assertEqual(support.upstream_plug(up.split(".")[0] + ".inputX"),
                             tex + ".outAlpha")
            self.assertTrue(cmds.getAttr(tex + ".alphaIsLuminance"),
                            "%s alphaIsLuminance not enabled" % tex)

    def test_redshift_target_skips_luminance(self):
        if not support.is_plugin_loaded("redshift4maya"):
            self.skipTest("redshift4maya not installed")
        cmds.file(new=True, force=True)
        mat = support.create_material("VRayMtl", "rsalpha_src")
        cmds.setAttr(mat + ".useRoughness", 0)
        tex = cmds.shadingNode("file", asTexture=True, name="rsalpha_tex")
        cmds.connectAttr(tex + ".outAlpha", mat + ".reflectionGlossiness", force=True)
        self._convert(mat, "RedshiftMaterial")
        self.assertFalse(cmds.getAttr(tex + ".alphaIsLuminance"))
