"""Shared harness for the mayapy-based integration test suite.

These tests drive the live Maya kernel (real node creation, connections,
shading-engine wiring, plugin behaviour). They are **not** part of CI; run them
locally with Maya's ``mayapy.exe``::

    mayapy -m unittest discover -s tests/mayapy -t tests -v

Each test starts from a fresh empty scene. Renderer plugins available on the
machine are loaded once at import time.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
import uuid as uuidlib

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:  # mayapy only; import-safe so pure-Python tooling can import this module
    import maya.standalone

    maya.standalone.initialize(name="python")
    import maya.cmds as cmds
except Exception:  # pragma: no cover - executed only outside mayapy
    cmds = None


PLUGINS = ("mtoa", "redshift4maya", "vrayformaya", "lookdevKit")

# Some plugins are not on MAYA_PLUG_IN_PATH under mayapy standalone but ship next
# to the Maya install; fall back to the absolute path.
_PLUGIN_RELATIVE = {
    "lookdevKit": os.path.join("bin", "plug-ins", "lookdevKit.mll"),
}

SPECIAL_COMMON_ATTRS = {"normal_bump", "displacementScale", "displacementTexture"}


def _maya_root():
    # sys.executable is <maya_root>/bin/mayapy.exe
    return os.path.dirname(os.path.dirname(os.path.abspath(sys.executable)))


def ensure_plugins(names=PLUGINS):
    """Load the given plugins; return {name: loaded_bool}. Never raises."""
    if cmds is None:
        return {}
    status = {}
    for name in names:
        loaded = False
        try:
            loaded = bool(cmds.pluginInfo(name, query=True, loaded=True))
        except Exception:
            loaded = False
        if not loaded:
            try:
                cmds.loadPlugin(name)
                loaded = True
            except Exception:
                rel = _PLUGIN_RELATIVE.get(name)
                if rel:
                    path = os.path.join(_maya_root(), rel)
                    if os.path.exists(path):
                        try:
                            cmds.loadPlugin(path)
                            loaded = True
                        except Exception:
                            loaded = False
        status[name] = loaded
    return status


PLUGIN_STATUS = ensure_plugins()


def is_plugin_loaded(name):
    return bool(PLUGIN_STATUS.get(name))


def make_loader():
    from core.config_loader import ConfigLoader

    return ConfigLoader()


def available_material_configs(loader):
    """Material configs whose renderer plugin is loaded (generic plugin filtering).

    Renderers without an installed plugin are excluded so the cross-conversion
    matrix only runs for what is actually available on this machine; installing a
    renderer automatically widens the matrix.
    """
    result = []
    for cfg in loader.get_all_material_configs().values():
        if not cfg.plugin or is_plugin_loaded(cfg.plugin):
            result.append(cfg)
    return sorted(result, key=lambda c: c.node_type)


def unavailable_material_configs(loader):
    available = {c.node_type for c in available_material_configs(loader)}
    return [
        c for c in sorted(loader.get_all_material_configs().values(),
                          key=lambda c: c.node_type)
        if c.node_type not in available
    ]


class MayaTestCase(unittest.TestCase):
    """Base class giving each test a fresh scene."""

    def setUp(self):
        cmds.file(new=True, force=True)

    def temp_dir(self):
        path = os.path.join(tempfile.gettempdir(), "matconvert_tests",
                            uuidlib.uuid4().hex[:8])
        os.makedirs(path, exist_ok=True)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path


# --------------------------------------------------------------------------- #
# Node / value helpers shared by the conversion tests
# --------------------------------------------------------------------------- #

def create_material(node_type, name):
    return cmds.shadingNode(node_type, asShader=True, name=name)


def build_material(loader, node_type, name, input_paths, channel_options=None,
                   use_full_chain=True):
    """Build a material via MaterialBuilder (used to set up complex source nets)."""
    from core.builder_context import BuilderContext
    from core.material_builder import MaterialBuilder

    ctx = BuilderContext(config_loader=loader)
    builder = MaterialBuilder(ctx, config=loader)
    return builder.build(node_type, name, input_paths, use_qss=False,
                         use_full_chain=use_full_chain,
                         channel_options=channel_options or {})


def read_plug_value(plug):
    value = cmds.getAttr(plug)
    if isinstance(value, list) and value and isinstance(value[0], (tuple, list)):
        return value[0]
    return value


def upstream_plug(plug):
    conns = cmds.listConnections(plug, source=True, destination=False, plugs=True) or []
    return conns[0] if conns else None


def populate_material(mat, config, common_attrs):
    """Set a distinct, valid value on every mapped & settable source attribute.

    ``common_attrs`` is the universal attribute list (``loader.get_common_attrs()``);
    only these are transferable, so ``config.attr_map`` keys that come from the
    displacement schema (``file_source`` / ``output`` ...) are ignored.

    Returns ``{common_attr: (value, attr_type)}`` for the attributes that were set.
    Specialized attrs handled by dedicated modules (normal_bump, displacement) are
    skipped.
    """
    values = {}
    counter = [0]

    def next_scalar():
        counter[0] += 1
        return round(0.1 + (counter[0] % 8) * 0.1, 3)

    for common_attr in common_attrs:
        if common_attr in SPECIAL_COMMON_ATTRS:
            continue
        attr = config.get_maya_attr(common_attr)
        if not attr:
            continue
        plug = "%s.%s" % (mat, attr)
        if not cmds.objExists(plug):
            continue
        try:
            attr_type = cmds.getAttr(plug, type=True)
        except Exception:
            continue
        try:
            if attr_type in ("float3", "double3"):
                value = (next_scalar(), next_scalar(), next_scalar())
                cmds.setAttr(plug, *value)
            elif attr_type == "bool":
                value = True
                cmds.setAttr(plug, value)
            elif attr_type in ("long", "short", "byte", "enum"):
                value = 1
                cmds.setAttr(plug, value)
            else:
                value = next_scalar()
                cmds.setAttr(plug, value)
        except Exception:
            continue
        values[common_attr] = (value, attr_type)
    return values


def expected_target_value(src_value, target_attr_type):
    """What the target attribute should hold after a plain (no-invert) transfer.

    Vector targets (``float3`` / ``double3``) receive a broadcast when the source
    is scalar; scalar targets (any other type, e.g. ``doubleLinear``) receive the
    first channel when the source is a color.
    """
    is_vector = target_attr_type in ("float3", "double3")
    if isinstance(src_value, (tuple, list)):
        return tuple(src_value) if is_vector else src_value[0]
    if is_vector:
        return (src_value, src_value, src_value)
    return src_value


def assert_plug_equal(testcase, actual, expected, message):
    got = tuple(actual) if isinstance(actual, (tuple, list)) else (actual,)
    want = tuple(expected) if isinstance(expected, (tuple, list)) else (expected,)
    testcase.assertEqual(len(got), len(want), message)
    for got_channel, want_channel in zip(got, want):
        testcase.assertAlmostEqual(
            float(got_channel), float(want_channel), places=5, msg=message)

