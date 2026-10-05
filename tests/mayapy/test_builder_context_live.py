"""Live BuilderContext behaviour: node naming, connections, layered nodes, paths."""

from __future__ import annotations

import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class BuilderContextLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()

    def _ctx(self):
        from core.builder_context import BuilderContext
        return BuilderContext(config_loader=self.loader)

    def test_get_naming(self):
        naming = self._ctx().get_naming()
        self.assertIn("prefix", naming)
        self.assertIn("qss_prefix", naming)

    def test_create_node_uses_naming_prefix(self):
        ctx = self._ctx()
        node = ctx.create_node("file", "file", "abc", "baseColor", "texture")
        self.assertTrue(cmds.objExists(node))
        self.assertEqual(cmds.nodeType(node), "file")
        self.assertTrue(node.startswith(ctx.get_naming()["prefix"]["file"]))

    def test_connect_is_idempotent(self):
        ctx = self._ctx()
        f = ctx.create_node("file", "file", "cc1", "baseColor", "texture")
        mat = support.create_material("aiStandardSurface", "cc1mat")
        ctx.connect(f, "outColor", mat, "baseColor")
        ctx.connect(f, "outColor", mat, "baseColor")  # must not raise / duplicate
        self.assertEqual(support.upstream_plug(mat + ".baseColor"), f + ".outColor")

    def test_build_layered_node(self):
        ctx = self._ctx()
        lyr = ctx.build_layered_node("lyr", "baseColor")
        self.assertEqual(cmds.nodeType(lyr), "layeredTexture")

    def test_clean_path(self):
        from core.builder_context import BuilderContext
        self.assertEqual(BuilderContext.clean_path("  C:/tex/a.png  "), "C:/tex/a.png")
        self.assertEqual(BuilderContext.clean_path("file:///C:/tex/a.png"), "C:/tex/a.png")
