"""Live BatchBuilder: build one material from a scanner dict and orchestrate a
batch (order, progress callback, undo chunk)."""

from __future__ import annotations

import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class BatchBuilderLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()
        cls.target = "aiStandardSurface"

    def _bb(self):
        from core.builder_context import BuilderContext
        from core.batch_builder import BatchBuilder
        ctx = BuilderContext(config_loader=self.loader)
        return BatchBuilder(ctx)

    def setUp(self):
        super().setUp()
        if self.loader.get_material_config(self.target) is None:
            self.skipTest("%s missing" % self.target)

    def test_build_material_from_scanner_dict(self):
        material = {
            "name": "bm1",
            "channels": {
                "baseColor": {"path": "C:/tex/bm1_base.png"},
                "specularRoughness": {"path": "C:/tex/bm1_rough.png",
                                      "options": {"invert": True}},
            },
        }
        mat = self._bb().build_material(self.target, material, use_full_chain=False, use_qss=False)
        self.assertTrue(cmds.objExists(mat))
        self.assertIsNotNone(support.upstream_plug(mat + ".baseColor"))

    def test_build_all_progress_and_order(self):
        materials = [
            {"name": "bm1", "channels": {"baseColor": {"path": "C:/tex/a.png"}}},
            {"name": "bm2", "channels": {"baseColor": {"path": "C:/tex/b.png"}}},
        ]
        progress = []
        results = self._bb().build_all(
            materials, self.target, use_full_chain=False, use_qss=False,
            on_progress=lambda done, total, res: progress.append((done, total)))

        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.built for r in results))
        self.assertEqual(progress, [(1, 2), (2, 2)])

    def test_empty_batch(self):
        self.assertEqual(self._bb().build_all([], self.target), [])
