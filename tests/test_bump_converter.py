"""Unit tests for normal-space preservation (review finding B05).

Object-space and tangent-space normals share one switch attribute per renderer
(Maya ``bumpInterp`` / Redshift ``inputType`` / V-Ray ``bumpMapType``); the
converter must carry the source space into the target and report targets that
cannot express it.
"""

from core.config_loader import ConfigLoader
from core.converters import bump as bump_module
from core.converters.bump import BumpConverter
from core.logger import Logger


class FakeUtils:
    def __init__(self):
        self.connected = []

    def identify_node_type(self, node, logger=None):
        return "RedshiftMaterial"

    def smart_connect(self, src, dst, logger=None):
        self.connected.append((src, dst))
        return True

    @staticmethod
    def node_name_from_plug(plug):
        return (plug or "").split(".", 1)[0]


class FakeCmds:
    def __init__(self):
        self.node_types = {"src_mat": "RedshiftMaterial", "bn1": "RedshiftBumpMap"}
        self.attrs = {}
        self.conns = {}
        self.set_calls = []
        self.connect_calls = []
        self.created = []

    def nodeType(self, node):
        return self.node_types.get(node, "unknown")

    def getAttr(self, plug):
        return self.attrs[plug]

    def listConnections(self, plug, **kwargs):
        return list(self.conns.get(plug, []))

    def setAttr(self, plug, *args, **kwargs):
        self.set_calls.append((plug, args[0] if args else None))

    def objExists(self, plug):
        return True

    def connectAttr(self, src, dst, force=True):
        self.connect_calls.append((src, dst))

    def shadingNode(self, node_type, **kwargs):
        name = kwargs.get("name") or (node_type + "1")
        self.created.append((node_type, name))
        return name


def _make(monkeypatch, input_type=2, scale=1.0):
    fake = FakeCmds()
    fake.attrs["bn1.inputType"] = input_type
    fake.attrs["bn1.scale"] = scale
    fake.conns["bn1.input"] = ["file1.outColor"]
    fake.conns["src_mat.bump_input"] = ["bn1"]
    monkeypatch.setattr(bump_module, "cmds", fake)
    utils = FakeUtils()
    converter = BumpConverter(ConfigLoader(), utils, logger=Logger())
    return converter, fake, utils


def test_object_space_survives_redshift_to_vray(monkeypatch):
    converter, fake, _utils = _make(monkeypatch, input_type=2)

    outcome = converter.convert("src_mat", "target", "redshift", "vray")

    assert outcome
    assert ("target.bumpMapType", 2) in fake.set_calls
    assert not outcome.issues


def test_object_space_survives_redshift_to_maya(monkeypatch):
    converter, fake, _utils = _make(monkeypatch, input_type=2)
    fake.node_types["target"] = "bump2d_target"

    outcome = converter.convert("src_mat", "target", "redshift", "maya")

    assert outcome
    assert ("bn1_mayaNrm.bumpInterp", 2) in fake.set_calls


def test_tangent_space_writes_tangent_value(monkeypatch):
    converter, fake, _utils = _make(monkeypatch, input_type=1)

    outcome = converter.convert("src_mat", "target", "redshift", "vray")

    assert outcome
    assert ("target.bumpMapType", 1) in fake.set_calls


def test_object_space_on_arnold_is_reported_not_silent(monkeypatch):
    converter, fake, _utils = _make(monkeypatch, input_type=2)
    fake.node_types["target"] = "aiStandardSurface"

    outcome = converter.convert("src_mat", "target", "redshift", "arnold")

    assert outcome
    assert any("object-space normal not representable" in item
               for item in outcome.issues), outcome.issues
    # the normal node itself is still created and wired
    created_types = [node_type for node_type, _name in fake.created]
    assert "aiNormalMap" in created_types
    assert any(dst == "target.normalCamera" for _src, dst in fake.connect_calls)


def test_bump_mode_writes_bump_value(monkeypatch):
    converter, fake, _utils = _make(monkeypatch, input_type=0)

    outcome = converter.convert("src_mat", "target", "redshift", "vray")

    assert outcome
    assert ("target.bumpMapType", 0) in fake.set_calls
    assert not outcome.issues


def test_mode_write_failure_is_critical(monkeypatch):
    converter, fake, _utils = _make(monkeypatch, input_type=2)

    def failing_set(plug, *args, **kwargs):
        if plug == "target.bumpMapType":
            raise RuntimeError("locked")
        fake.set_calls.append((plug, args[0] if args else None))

    monkeypatch.setattr(fake, "setAttr", failing_set)

    outcome = converter.convert("src_mat", "target", "redshift", "vray")

    assert not outcome
    assert any("failed to set mode" in item for item in outcome.critical)
