"""Make the parent ``tests`` directory importable as ``import support``.

When the mayapy suite lives under ``tests/mayapy/``, ``unittest discover -t tests``
imports the test modules as top-level names, so ``support`` (in ``tests/``) must be
on ``sys.path``. This mirrors the attribute-manager project's layout.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_TESTS = os.path.dirname(_HERE)
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)

# Announce the environment once per run: a suite that "passed with skips" must be
# distinguishable from one that actually exercised every renderer.
try:
    import support

    print("[mayapy] " + support.describe_environment())
except Exception as exc:  # pragma: no cover - diagnostics only
    print("[mayapy] environment probe failed: %r" % (exc,))
