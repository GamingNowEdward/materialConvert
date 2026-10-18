"""Performance baseline for conversion and scanning (review finding O03).

Not a pass/fail benchmark: this suite records the number of ``cmds`` queries and
the elapsed time for one fixed scenario so optimisations can be compared against
the same workload.  The assertions are deliberately loose and only catch a
catastrophic regression (e.g. a query loop added per file).

Run locally with mayapy; it is not part of CI.
"""

from __future__ import annotations

import time
import unittest

import support

cmds = support.cmds

_METERED = ("ls", "listConnections", "nodeType", "getAttr", "objExists")


class CallCounter:
    def __init__(self):
        self.calls = {}

    def install(self, module, names=_METERED):
        originals = {}
        for name in names:
            original = getattr(module, name)
            originals[name] = original
            setattr(module, name, self._wrap(name, original))
        return originals

    def _wrap(self, name, original):
        def counted(*args, **kwargs):
            self.calls[name] = self.calls.get(name, 0) + 1
            return original(*args, **kwargs)

        return counted

    @staticmethod
    def restore(module, originals):
        for name, original in originals.items():
            setattr(module, name, original)

    @property
    def total(self):
        return sum(self.calls.values())


@unittest.skipIf(cmds is None, "mayapy required")
class PerfBaseline(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()

    def test_single_conversion_query_baseline(self):
        src = self.loader.get_material_config("aiStandardSurface")
        tgt = self.loader.get_material_config("VRayMtl")
        if src is None or tgt is None:
            self.skipTest("arnold / vray configs missing")
        if not support.is_plugin_loaded(src.plugin) or not support.is_plugin_loaded(tgt.plugin):
            self.skipTest("arnold / vray plugins not installed")

        cmds.file(new=True, force=True)
        mat = support.build_material(
            self.loader, "aiStandardSurface", "perfBase",
            {"baseColor": "C:/tex/perf_base.png",
             "specularRoughness": "C:/tex/perf_rough.png"},
            use_full_chain=False,
        )

        from core.converter import MaterialConverter

        counter = CallCounter()
        originals = counter.install(cmds)
        started = time.perf_counter()
        try:
            result = MaterialConverter(config=self.loader).convert(mat, "VRayMtl")
        finally:
            CallCounter.restore(cmds, originals)
        elapsed = time.perf_counter() - started

        self.assertTrue(result.converted, result.reason)
        print("[perf] single conversion: %.4fs, %d cmds call(s) %s"
              % (elapsed, counter.total, counter.calls))
        # catastrophic-regression guard only
        self.assertLess(counter.total, 5000)

    def test_batch_conversion_query_baseline(self):
        src = self.loader.get_material_config("aiStandardSurface")
        tgt = self.loader.get_material_config("VRayMtl")
        if src is None or tgt is None:
            self.skipTest("arnold / vray configs missing")
        if not support.is_plugin_loaded(src.plugin) or not support.is_plugin_loaded(tgt.plugin):
            self.skipTest("arnold / vray plugins not installed")

        cmds.file(new=True, force=True)
        materials = [
            support.build_material(
                self.loader, "aiStandardSurface", "perfBatch%d" % index,
                {"baseColor": "C:/tex/perf_base.png"}, use_full_chain=False)
            for index in range(5)
        ]

        from core.converter import MaterialConverter

        counter = CallCounter()
        originals = counter.install(cmds)
        started = time.perf_counter()
        try:
            results = MaterialConverter(config=self.loader).convert_all(
                materials, "VRayMtl")
        finally:
            CallCounter.restore(cmds, originals)
        elapsed = time.perf_counter() - started

        self.assertEqual(len(results), 5)
        self.assertTrue(all(result.converted for result in results),
                        [result.reason for result in results])
        print("[perf] 5-material batch: %.4fs, %d cmds call(s) %s"
              % (elapsed, counter.total, counter.calls))

    def test_scanner_alias_baseline(self):
        from core.logger import Logger
        from core.texture_scanner import TextureScanner

        scanner = TextureScanner(logger=Logger())
        stems = []
        for index in range(200):
            stems.append("rock%d_baseColor" % index)
            stems.append("rock%d_roughness" % index)

        started = time.perf_counter()
        parsed = [scanner._parse(stem) for stem in stems]
        elapsed = time.perf_counter() - started

        self.assertTrue(all(item is not None for item in parsed))
        print("[perf] parsed %d stems in %.4fs" % (len(stems), elapsed))
        self.assertLess(elapsed, 10.0)
