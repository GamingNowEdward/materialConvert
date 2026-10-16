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

    # ------------------------------------------------------------------ #
    # Legacy RedshiftNormalMap (embedded texture path) compatibility
    # ------------------------------------------------------------------ #

    def _build_legacy_normal_source(self, tex_path=None, with_p2d=False):
        mat = cmds.shadingNode("RedshiftMaterial", asShader=True, name="legacyMat")
        sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="legacyMatSG")
        cmds.connectAttr("%s.outColor" % mat, "%s.surfaceShader" % sg)
        nm = cmds.shadingNode("RedshiftNormalMap", asTexture=True, name="legacyNm")
        if tex_path is not None:
            cmds.setAttr("%s.tex0" % nm, tex_path, type="string")
        cmds.connectAttr("%s.outDisplacementVector" % nm, "%s.bump_input" % mat, force=True)
        p2d = None
        if with_p2d:
            p2d = cmds.shadingNode("place2dTexture", asUtility=True, name="legacyP2d")
            cmds.connectAttr("%s.outUV" % p2d, "%s.uvCoord" % nm, force=True)
        return mat, nm, p2d

    def _require_legacy_renderers(self):
        if not support.is_plugin_loaded("redshift4maya"):
            self.skipTest("redshift4maya not available")
        if not support.is_plugin_loaded("mtoa"):
            self.skipTest("mtoa not available")

    def _target_normal_upstream(self, target, node_type):
        cfg = self.loader.get_material_config(node_type)
        plug = "%s.%s" % (target, cfg.get_maya_attr("normal_bump"))
        return support.upstream_plug(plug)

    def test_legacy_normal_map_converts_to_arnold(self):
        self._require_legacy_renderers()
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        tex = "C:/tex/legacy_nrm.png"
        mat, nm, _ = self._build_legacy_normal_source(tex_path=tex)

        result = MaterialConverter(config=self.loader).convert(mat, "aiStandardSurface")
        self.assertTrue(result.converted, result.reason)

        up = self._target_normal_upstream(result.new_material, "aiStandardSurface")
        self.assertIsNotNone(up, "target normal not connected")
        bn = up.split(".")[0]
        self.assertEqual(cmds.nodeType(bn), "aiNormalMap")

        file_up = support.upstream_plug("%s.input" % bn)
        self.assertIsNotNone(file_up, "aiNormalMap input not connected")
        file_node = file_up.split(".")[0]
        self.assertEqual(cmds.nodeType(file_node), "file")
        self.assertEqual(cmds.getAttr("%s.fileTextureName" % file_node), tex)
        # source network preserved (old nodes are never deleted)
        self.assertTrue(cmds.objExists(nm))

    def test_legacy_normal_map_converts_to_vray(self):
        if not support.is_plugin_loaded("redshift4maya"):
            self.skipTest("redshift4maya not available")
        if not support.is_plugin_loaded("vrayformaya"):
            self.skipTest("vrayformaya not available")
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        tex = "C:/tex/legacy_nrm.png"
        mat, nm, _ = self._build_legacy_normal_source(tex_path=tex)

        result = MaterialConverter(config=self.loader).convert(mat, "VRayMtl")
        self.assertTrue(result.converted, result.reason)

        cfg = self.loader.get_material_config("VRayMtl")
        bump_map = cfg.get_maya_attr("normal_bump")
        up = support.upstream_plug("%s.%s" % (result.new_material, bump_map))
        self.assertIsNotNone(up, "V-Ray bumpMap not connected")
        file_node = up.split(".")[0]
        self.assertEqual(cmds.nodeType(file_node), "file")
        self.assertEqual(cmds.getAttr("%s.fileTextureName" % file_node), tex)

        mapping = self.loader.get_bump_normal_config("vray").normal
        self.assertEqual(
            cmds.getAttr("%s.%s" % (result.new_material, mapping.is_normal)),
            mapping.effective_mode_value())

    def test_legacy_normal_map_reuses_existing_p2d(self):
        self._require_legacy_renderers()
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        mat, nm, p2d = self._build_legacy_normal_source(
            tex_path="C:/tex/legacy_nrm.png", with_p2d=True)
        p2d_before = set(cmds.ls(type="place2dTexture") or [])

        result = MaterialConverter(config=self.loader).convert(mat, "aiStandardSurface")
        self.assertTrue(result.converted, result.reason)
        self.assertEqual(set(cmds.ls(type="place2dTexture") or []), p2d_before,
                         "existing place2dTexture must be reused, not duplicated")

        up = self._target_normal_upstream(result.new_material, "aiStandardSurface")
        file_node = support.upstream_plug("%s.input" % up.split(".")[0]).split(".")[0]
        self.assertEqual(support.upstream_plug("%s.uvCoord" % file_node).split(".")[0], p2d)

    def test_legacy_normal_map_creates_p2d_when_absent(self):
        self._require_legacy_renderers()
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        mat, nm, _ = self._build_legacy_normal_source(tex_path="C:/tex/legacy_nrm.png")
        p2d_before = set(cmds.ls(type="place2dTexture") or [])

        result = MaterialConverter(config=self.loader).convert(mat, "aiStandardSurface")
        self.assertTrue(result.converted, result.reason)
        new_p2d = set(cmds.ls(type="place2dTexture") or []) - p2d_before
        self.assertEqual(len(new_p2d), 1)
        self.assertTrue(next(iter(new_p2d)).startswith("p2d_%s" % nm))

    def test_legacy_normal_map_empty_path_is_skipped(self):
        self._require_legacy_renderers()
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        mat, nm, _ = self._build_legacy_normal_source(tex_path=None)
        files_before = set(cmds.ls(type="file") or [])
        p2d_before = set(cmds.ls(type="place2dTexture") or [])

        result = MaterialConverter(config=self.loader).convert(mat, "aiStandardSurface")
        self.assertTrue(result.converted, result.reason)
        self.assertIsNone(
            self._target_normal_upstream(result.new_material, "aiStandardSurface"),
            "empty embedded path must not produce a normal connection")
        self.assertEqual(set(cmds.ls(type="file") or []) - files_before, set())
        self.assertEqual(set(cmds.ls(type="place2dTexture") or []) - p2d_before, set())

    def test_legacy_normal_map_same_renderer_reconnect(self):
        if not support.is_plugin_loaded("redshift4maya"):
            self.skipTest("redshift4maya not available")
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        mat, nm, _ = self._build_legacy_normal_source(tex_path="C:/tex/legacy_nrm.png")

        result = MaterialConverter(config=self.loader).convert(mat, "RedshiftStandardMaterial")
        self.assertTrue(result.converted, result.reason)
        up = self._target_normal_upstream(result.new_material, "RedshiftStandardMaterial")
        self.assertIsNotNone(up, "legacy node was not reconnected")
        self.assertEqual(up.split(".")[0], nm)
        self.assertFalse(result.reason)

    def test_legacy_normal_map_does_not_duplicate_file(self):
        self._require_legacy_renderers()
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        mat, nm, _ = self._build_legacy_normal_source(tex_path="C:/tex/legacy_nrm.png")

        MaterialConverter(config=self.loader).convert(mat, "aiStandardSurface")
        first = [n for n in (cmds.ls(type="file") or []) if n.startswith("tex_")]
        MaterialConverter(config=self.loader).convert(mat, "aiStandardSurface")
        second = [n for n in (cmds.ls(type="file") or []) if n.startswith("tex_")]
        self.assertEqual(len(second), len(first),
                         "re-conversion must reuse the embedded-path file node")

    def test_legacy_materialization_failure_fails_conversion(self):
        self._require_legacy_renderers()
        from core.converter import MaterialConverter
        from core.converters.bump import BumpConverter

        cmds.file(new=True, force=True)
        mat, nm, _ = self._build_legacy_normal_source(tex_path="C:/tex/legacy_nrm.png")

        original = BumpConverter._build_file_from_path

        def _fail(self, bn_node, path, bn_cfg):
            return None, False

        BumpConverter._build_file_from_path = _fail
        try:
            result = MaterialConverter(config=self.loader).convert(mat, "aiStandardSurface")
        finally:
            BumpConverter._build_file_from_path = original

        self.assertFalse(result.converted, "materialization failure must fail conversion")
        self.assertIn("bump", (result.reason or "").lower())

    def test_legacy_p2d_connection_failure_fails_conversion(self):
        self._require_legacy_renderers()
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        mat, nm, _ = self._build_legacy_normal_source(tex_path="C:/tex/legacy_nrm.png")

        original = cmds.connectAttr

        def _connect(src, dst, *args, **kwargs):
            if dst.endswith(".uvCoord"):
                raise RuntimeError("simulated uv connection failure")
            return original(src, dst, *args, **kwargs)

        cmds.connectAttr = _connect
        try:
            result = MaterialConverter(config=self.loader).convert(mat, "aiStandardSurface")
        finally:
            cmds.connectAttr = original

        self.assertFalse(result.converted, "p2d connection failure must fail conversion")
        self.assertIn("bump", (result.reason or "").lower())
        # the partially built file node is left in the scene (old nodes are never deleted)
        self.assertTrue([n for n in (cmds.ls(type="file") or []) if n.startswith("tex_")])
