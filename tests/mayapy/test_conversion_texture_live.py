"""Live texture-driven connection conversion.

For every available material pair, a ``file`` node drives a representative
attribute of each kind (colour / scalar roughness / metallic / opacity); after
conversion the target attribute must be connected and the source chain must stay
intact. Inverted V-Ray glossiness channels are wired through a ``reverse`` node.
"""

from __future__ import annotations

import unittest

import support

cmds = support.cmds

# (common attr, file output plug) — colour uses outColor, scalars use outAlpha
CHANNELS = (
    ("baseColor", "outColor"),
    ("specularRoughness", "outAlpha"),
    ("metallic", "outAlpha"),
    ("opacity", "outAlpha"),
)


@unittest.skipIf(cmds is None, "mayapy required")
class TextureConversionLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()
        cls.configs = support.available_material_configs(cls.loader)

    def test_texture_connections_transfer_and_source_kept(self):
        checked = 0
        for src in self.configs:
            for tgt in self.configs:
                if src.node_type == tgt.node_type:
                    continue
                for common_attr, out in CHANNELS:
                    src_attr = src.get_maya_attr(common_attr)
                    tgt_attr = tgt.get_maya_attr(common_attr)
                    if not src_attr or not tgt_attr:
                        continue
                    with self.subTest(src=src.node_type, tgt=tgt.node_type, channel=common_attr):
                        if self._check_channel(src, tgt, common_attr, src_attr, tgt_attr, out):
                            checked += 1
        self.assertGreater(checked, 0)

    def _check_channel(self, src, tgt, common_attr, src_attr, tgt_attr, out):
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        mat = support.create_material(src.node_type, "tex_%s" % common_attr)
        tex = cmds.shadingNode("file", asTexture=True, name="texFile_%s" % common_attr)
        try:
            cmds.connectAttr("%s.%s" % (tex, out), "%s.%s" % (mat, src_attr), force=True)
        except RuntimeError:
            return False  # type mismatch for this renderer/channel, skip

        result = MaterialConverter(config=self.loader).convert(mat, tgt.node_type)
        self.assertTrue(result.converted, result.reason)
        target = result.new_material

        target_up = support.upstream_plug("%s.%s" % (target, tgt_attr))
        self.assertIsNotNone(target_up, "target %s not connected" % tgt_attr)

        # source chain must be preserved
        self.assertIsNotNone(support.upstream_plug("%s.%s" % (mat, src_attr)))
        return True

    def test_vray_texture_glossiness_inverted_on_target_edge(self):
        # V-Ray source in glossiness mode -> roughness channel goes through reverse
        vray = self.loader.get_material_config("VRayMtl")
        arnold = self.loader.get_material_config("aiStandardSurface")
        if vray is None or arnold is None:
            self.skipTest("VRayMtl / aiStandardSurface config missing")

        cmds.file(new=True, force=True)
        mat = support.create_material("VRayMtl", "vinv_src")
        cmds.setAttr(mat + ".useRoughness", 0)
        tex = cmds.shadingNode("file", asTexture=True, name="vinv_tex")
        cmds.connectAttr(tex + ".outAlpha", mat + ".reflectionGlossiness", force=True)

        from core.converter import MaterialConverter
        result = MaterialConverter(config=self.loader).convert(mat, "aiStandardSurface")
        self.assertTrue(result.converted, result.reason)
        target = result.new_material

        up = support.upstream_plug(target + ".specularRoughness")
        self.assertIsNotNone(up)
        node = up.split(".")[0]
        self.assertEqual(cmds.nodeType(node), "reverse")
        self.assertEqual(support.upstream_plug(node + ".inputX"), tex + ".outAlpha")
        # source chain intact
        self.assertEqual(support.upstream_plug(mat + ".reflectionGlossiness"), tex + ".outAlpha")
