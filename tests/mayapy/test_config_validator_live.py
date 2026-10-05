"""Live ConfigValidator run against real Maya nodes.

Every material / bumpNormal / colorCorrection mapping must resolve on the
installed renderer plugins (mtoa / vrayformaya / lookdevKit ...). Renderers whose
plugin is missing are skipped by the validator itself (whole group SKIP), which is
expected and not an error.
"""

from __future__ import annotations

import unittest

import support


@unittest.skipIf(support.cmds is None, "mayapy required")
class ConfigValidatorLive(support.MayaTestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = support.make_loader()

    def test_validate_all_reports_no_errors_or_warnings(self):
        from core.config_validator import ConfigValidator
        from core.logger import LogLevel

        unavailable = [c.node_type for c in support.unavailable_material_configs(self.loader)]
        if unavailable:
            print("ConfigValidatorLive: renderers not installed, skipped by validator: %s"
                  % ", ".join(unavailable))

        validator = ConfigValidator(loader=self.loader)
        results, summary = validator.validate_all()

        errors = [r for r in results if r.level == LogLevel.ERROR]
        warns = [r for r in results if r.level == LogLevel.WARN]
        detail = "\n".join("%s: %s" % (r.scope, r.detail) for r in errors + warns)

        self.assertEqual(errors, [], "Config validation ERROR(s):\n" + detail)
        self.assertEqual(warns, [], "Config validation WARN(s):\n" + detail)
        self.assertGreater(summary["ok"], 0)
        # temporary validation nodes must be cleaned up
        self.assertEqual(validator._created, [])
