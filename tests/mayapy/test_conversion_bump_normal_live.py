"""Live bump / normal conversion across renderers, in both bump and normal mode.

Source networks are built with the MaterialBuilder (bump mode and normal mode),
then converted; the target bump/normal must be wired and, where the renderer
encodes the mode on the material or node, the mode value must be set correctly.
"""

from __future__ import annotations

import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class BumpNormalConversionLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()
        cls.configs = support.available_material_configs(cls.loader)

    def test_bump_and_normal_convert_across_renderers(self):
        checked = 0
        for src in self.configs:
            for tgt in self.configs:
                if src.node_type == tgt.node_type:
                    continue
                for is_normal in (False, True):
                    mode = "normal" if is_normal else "bump"
                    with self.subTest(src=src.node_type, tgt=tgt.node_type, mode=mode):
                        if self._check(src, tgt, is_normal):
                            checked += 1
        self.assertGreater(checked, 0)

    def _check(self, src, tgt, is_normal):
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        mode = "normal" if is_normal else "bump"
        mat = support.build_material(
            self.loader, src.node_type, "bn_%s" % mode,
            {"baseColor": "C:/tex/bn_base.png",
             "normal_bump": "C:/tex/bn_%s.png" % mode},
            channel_options={"normal_bump": {"mode": mode}},
        )
        src_attr = src.get_maya_attr("normal_bump")
        src_plug = "%s.%s" % (mat, src_attr)
        self.assertTrue(cmds.objExists(src_plug), "source normal_bump attr missing")
        self.assertIsNotNone(support.upstream_plug(src_plug), "source bump/normal not built")

        result = MaterialConverter(config=self.loader).convert(mat, tgt.node_type)
        self.assertTrue(result.converted, result.reason)
        target = result.new_material
        tplug = "%s.%s" % (target, tgt.get_maya_attr("normal_bump"))
        self.assertIsNotNone(support.upstream_plug(tplug), "target bump/normal not connected")

        mapping = self.loader.get_bump_normal_config(tgt.renderer)
        tgt_map = mapping.normal if is_normal else mapping.bump
        if tgt_map.is_material_attribute:
            if tgt_map.is_normal:
                self.assertEqual(
                    cmds.getAttr("%s.%s" % (target, tgt_map.is_normal)),
                    tgt_map.effective_mode_value())
        else:
            upstream = support.upstream_plug(tplug)
            self.assertEqual(cmds.nodeType(upstream.split(".")[0]), tgt_map.node_type)

        # source chain preserved
        self.assertIsNotNone(support.upstream_plug(src_plug))
        return True

    def test_object_space_normal_is_detected_for_redshift_and_vray(self):
        if self.loader.get_material_config("aiStandardSurface") is None:
            self.skipTest("arnold config missing")

        from core.converter import MaterialConverter

        cases = (
            ("RedshiftMaterial", "inputType", "node"),
            ("VRayMtl", "bumpMapType", "material"),
        )
        for src_type, mode_attr, kind in cases:
            src_cfg = self.loader.get_material_config(src_type)
            if src_cfg is None:
                continue
            with self.subTest(src=src_type):
                cmds.file(new=True, force=True)
                mat = support.build_material(
                    self.loader, src_type, "osn_%s" % src_type,
                    {"normal_bump": "C:/tex/osn.png"},
                    channel_options={"normal_bump": {"mode": "normal"}},
                )
                nb_attr = src_cfg.get_maya_attr("normal_bump")
                if kind == "material":
                    cmds.setAttr("%s.%s" % (mat, mode_attr), 2)  # object-space normal
                else:
                    bn = support.upstream_plug("%s.%s" % (mat, nb_attr)).split(".")[0]
                    cmds.setAttr("%s.%s" % (bn, mode_attr), 2)  # object-space normal

                result = MaterialConverter(config=self.loader).convert(mat, "aiStandardSurface")
                self.assertTrue(result.converted, result.reason)
                upstream = support.upstream_plug(result.new_material + ".normalCamera")
                self.assertIsNotNone(upstream)
                # object-space normal must map to a NORMAL node, not a bump node
                self.assertEqual(cmds.nodeType(upstream.split(".")[0]), "aiNormalMap")
