"""Cross-material conversion matrix: every available source material type is
converted to every other, and every mapped common attribute is checked.

The plain (non-inverted) mapping is asserted here, so a V-Ray source is forced
into roughness mode (useRoughness=1) to keep glossiness channels direct; the
glossiness inversion itself is covered in test_conversion_special_live.py.
Renderer plugins that are not installed are filtered out generically (the matrix
widens automatically once a renderer is installed).
"""

from __future__ import annotations

import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class CrossConversionMatrix(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()
        cls.configs = support.available_material_configs(cls.loader)

    def test_every_pair_maps_every_attribute(self):
        self.assertGreaterEqual(
            len(self.configs), 2,
            "need at least two available renderers for cross conversion")
        pairs = 0
        for src in self.configs:
            for tgt in self.configs:
                if src.node_type == tgt.node_type:
                    continue
                with self.subTest(src=src.node_type, tgt=tgt.node_type):
                    self._check_pair(src, tgt)
                pairs += 1
        self.assertGreater(pairs, 0)

    def _check_pair(self, src, tgt):
        from core.converter import MaterialConverter

        cmds.file(new=True, force=True)
        converter = MaterialConverter(config=self.loader)

        mat = support.create_material(src.node_type, "srcMat")
        # Keep the direct mapping: V-Ray roughness mode stores roughness, not glossiness.
        if cmds.objExists(mat + ".useRoughness"):
            cmds.setAttr(mat + ".useRoughness", 1)

        source_values = support.populate_material(mat, src, self.loader.get_common_attrs())
        self.assertTrue(source_values, "no source attributes set for %s" % src.node_type)

        result = converter.convert(mat, tgt.node_type)
        self.assertTrue(result.created, result.reason)
        self.assertTrue(result.converted, result.reason)
        target = result.new_material

        checked = 0
        for common_attr, (src_value, _src_type) in source_values.items():
            tgt_attr = tgt.get_maya_attr(common_attr)
            if not tgt_attr:
                continue
            tgt_plug = "%s.%s" % (target, tgt_attr)
            if not cmds.objExists(tgt_plug):
                continue
            tgt_type = cmds.getAttr(tgt_plug, type=True)
            expected = support.expected_target_value(src_value, tgt_type)
            actual = support.read_plug_value(tgt_plug)
            support.assert_plug_equal(
                self, actual, expected,
                "%s -> %s | %s (%s): got %r want %r"
                % (src.node_type, tgt.node_type, common_attr, tgt_attr, actual, expected))
            checked += 1

        self.assertGreater(
            checked, 0,
            "no attributes compared for %s -> %s" % (src.node_type, tgt.node_type))
