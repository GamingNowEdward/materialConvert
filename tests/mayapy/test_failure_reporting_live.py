"""Live regression tests for the Option-C failure reporting:

* a critical channel failure (bump input) aborts the conversion (failed),
* a non-critical attribute failure is recorded as an issue (converted, with_issues),
* BatchBuilder/BuildResult surface per-channel issues.
"""

from __future__ import annotations

import unittest

import support

cmds = support.cmds


@unittest.skipIf(cmds is None, "mayapy required")
class FailureReportingLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()

    def _require(self, node_type):
        if self.loader.get_material_config(node_type) is None:
            self.skipTest("%s config missing" % node_type)

    def test_bump_input_failure_aborts_conversion(self):
        self._require("aiStandardSurface")
        self._require("VRayMtl")

        cmds.file(new=True, force=True)
        src = support.create_material("aiStandardSurface", "bfail_src")
        bn = cmds.shadingNode("aiBump2d", asUtility=True, name="bfail_bn")
        md = cmds.shadingNode("multiplyDivide", asUtility=True, name="bfail_md")
        cmds.connectAttr(md + ".outputX", bn + ".bumpMap", force=True)
        cmds.connectAttr(bn + ".outValue", src + ".normalCamera", force=True)

        from core.converter import MaterialConverter
        from core.results import summarize_results
        result = MaterialConverter(config=self.loader).convert(src, "VRayMtl")

        self.assertFalse(result.converted)
        self.assertTrue(result.reason)
        self.assertEqual(summarize_results([result])["failed"], 1)

    def test_attribute_failure_is_an_issue_not_a_failure(self):
        self._require("aiStandardSurface")
        self._require("VRayMtl")

        cmds.file(new=True, force=True)
        src = support.create_material("aiStandardSurface", "ifail_src")
        cmds.setAttr(src + ".specular", 0.7)  # specularWeight -> VRay reflectionColorAmount

        original = cmds.setAttr
        target_plug = "ifail_src_vray.reflectionColorAmount"

        def flaky(plug, *args, **kwargs):
            if plug == target_plug:
                raise RuntimeError("simulated setAttr failure")
            return original(plug, *args, **kwargs)

        cmds.setAttr = flaky
        try:
            from core.converter import MaterialConverter
            from core.results import summarize_results
            result = MaterialConverter(config=self.loader).convert(src, "VRayMtl")
        finally:
            cmds.setAttr = original

        self.assertTrue(result.converted)
        self.assertTrue(result.issues)
        self.assertTrue(result.has_issues)
        summary = summarize_results([result])
        self.assertEqual(summary["converted"], 1)
        self.assertEqual(summary["with_issues"], 1)
        self.assertEqual(summary["failed"], 0)

    def test_batch_builder_surfaces_channel_issues(self):
        self._require("aiStandardSurface")

        from core.builder_context import BuilderContext
        from core.batch_builder import BatchBuilder
        from core.results import summarize_build_results

        bb = BatchBuilder(BuilderContext(config_loader=self.loader))

        def fake_build(*args, **kwargs):
            bb.builder.last_build_issues = ["metallic: texture not connected"]
            return "M_fake"

        bb.builder.build = fake_build
        results = bb.build_all(
            [{"name": "fake", "channels": {}}], "aiStandardSurface",
            use_full_chain=False, use_qss=False)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].built)
        self.assertEqual(results[0].issues, ["metallic: texture not connected"])
        self.assertEqual(summarize_build_results(results)["with_issues"], 1)
