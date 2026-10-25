"""Unit tests for the displacement converter's failure propagation.

These encode the failure semantics: a displacement texture/scale/create failure
must never be reported as a successful conversion, and "no source displacement"
must stay distinguishable from "source data could not be read".
"""

import types

from core.converters import displacement as displacement_module
from core.converters.displacement import DisplacementConverter
from core.logger import LogLevel, Logger


class FakeUtils:
    def __init__(self, connect_ok=True):
        self.connect_ok = connect_ok
        self.connected = []

    def smart_connect(self, src, dst, logger=None):
        if self.connect_ok:
            self.connected.append((src, dst))
        return self.connect_ok

    @staticmethod
    def node_name_from_plug(plug):
        return (plug or "").split(".", 1)[0]


class FakeCmds:
    def __init__(self):
        self.conns = {}
        self.attrs = {}
        self.exists = set()
        self.created = []
        self.connect_calls = []
        self.shading_node_error = None
        self.connect_errors = {}
        self.setattr_errors = {}
        self.outputs_exist = True

    def listConnections(self, plug, **kwargs):
        value = self.conns.get(plug, [])
        if isinstance(value, Exception):
            raise value
        return list(value)

    def getAttr(self, plug):
        value = self.attrs.get(plug, 1.0)
        if isinstance(value, Exception):
            raise value
        return value

    def setAttr(self, plug, *args, **kwargs):
        error = self.setattr_errors.get(plug)
        if error is not None:
            raise error
        self.attrs[plug] = args[0] if args else None

    def objExists(self, plug):
        if plug in self.exists:
            return True
        if plug.startswith("mat."):
            # source-material displacement attributes used by the config schema
            return True
        node, _sep, attr = plug.partition(".")
        return self.outputs_exist and node.startswith("disp") and attr == "out"

    def shadingNode(self, node_type, **kwargs):
        if self.shading_node_error is not None:
            raise self.shading_node_error
        name = "disp%d" % (len(self.created) + 1)
        self.created.append(name)
        return name

    def connectAttr(self, src, dst, force=True):
        error = self.connect_errors.get((src, dst))
        if error is not None:
            raise error
        self.connect_calls.append((src, dst))


def _source_config():
    return types.SimpleNamespace(
        displacement_node_type="displacementShader",
        displacement_texture="displacement",
        displacement_scale="displacementScale",
    )


def _target_config():
    return types.SimpleNamespace(
        displacement_node_type="RedshiftDisplacement",
        displacement_texture="displacement",
        displacement_scale="scale",
        displacement_output="out",
    )


def _converter(monkeypatch, cmds=None, utils=None, log=None):
    fake = cmds or FakeCmds()
    monkeypatch.setattr(displacement_module, "cmds", fake)
    log = log or Logger()
    conv = DisplacementConverter(None, utils or FakeUtils(), logger=log)
    return conv, fake, log


def _prepare(conv, sgs=("sg1",)):
    return conv.prepare("mat", "mat_rs", _source_config(), _target_config(),
                        "redshift", list(sgs))


def test_prepare_plans_without_committing_to_sg(monkeypatch):
    conv, fake, _log = _converter(monkeypatch)
    fake.conns["mat.displacement"] = ["tex1.outAlpha"]
    fake.attrs["mat.displacementScale"] = 0.5
    fake.exists = {"disp1.out"}

    plan = _prepare(conv)

    assert plan.ok
    assert plan.entries == [{"sg": "sg1", "node": "disp1", "output": "out"}]
    assert fake.connect_calls == []  # nothing committed yet
    assert conv.utils.connected == [("tex1.outAlpha", "disp1.displacement")]
    assert fake.attrs["disp1.scale"] == 0.5


def test_apply_commits_to_each_sg(monkeypatch):
    conv, fake, _log = _converter(monkeypatch)
    fake.conns["mat.displacement"] = ["tex1.outAlpha"]
    fake.exists = {"disp1.out"}

    plan = _prepare(conv, ("sg1", "sg2"))
    failures = conv.apply(plan)

    assert failures == []
    assert fake.connect_calls == [
        ("disp1.out", "sg1.displacementShader"),
        ("disp1.out", "sg2.displacementShader"),
    ]


def test_texture_connection_failure_is_critical(monkeypatch):
    conv, fake, log = _converter(monkeypatch, utils=FakeUtils(connect_ok=False))
    fake.conns["mat.displacement"] = ["tex1.outAlpha"]
    fake.exists = {"disp1.out"}

    plan = _prepare(conv)
    assert not plan.ok
    assert any("failed to connect displacement texture" in item for item in plan.critical)

    outcome = conv.convert("mat", "mat_rs", _source_config(), _target_config(),
                           "redshift", ["sg1"])
    assert not outcome
    assert outcome.critical
    errors = [r for r in log.poll(0) if r.level == LogLevel.ERROR]
    assert errors


def test_scale_write_failure_is_a_non_critical_issue(monkeypatch):
    conv, fake, _log = _converter(monkeypatch)
    fake.conns["mat.displacement"] = ["tex1.outAlpha"]
    fake.exists = {"disp1.out"}
    fake.setattr_errors["disp1.scale"] = RuntimeError("locked")

    outcome = conv.convert("mat", "mat_rs", _source_config(), _target_config(),
                           "redshift", ["sg1"])
    assert outcome
    assert any("displacement scale not set" in item for item in outcome.issues)


def test_node_creation_failure_is_critical(monkeypatch):
    conv, fake, _log = _converter(monkeypatch)
    fake.conns["mat.displacement"] = ["tex1.outAlpha"]
    fake.shading_node_error = RuntimeError("no plugin")

    plan = _prepare(conv)
    assert not plan.ok
    assert any("failed to create RedshiftDisplacement" in item for item in plan.critical)


def test_missing_output_attribute_is_critical(monkeypatch):
    conv, fake, _log = _converter(monkeypatch)
    fake.conns["mat.displacement"] = ["tex1.outAlpha"]
    fake.outputs_exist = False  # no usable output

    plan = _prepare(conv)
    assert not plan.ok
    assert any("no usable displacement output" in item for item in plan.critical)


def test_source_read_failure_is_not_the_same_as_no_displacement(monkeypatch):
    conv, fake, _log = _converter(monkeypatch)
    fake.conns["mat.displacement"] = RuntimeError("scene locked")

    ignored, ok = conv._collect("mat", "sg1", _source_config())
    assert ignored is None
    assert ok is False

    fake.conns["mat.displacement"] = []
    ignored, ok = conv._collect("mat", "sg1", _source_config())
    assert ignored is None
    assert ok is True


def test_source_node_without_texture_is_skipped(monkeypatch):
    conv, fake, _log = _converter(monkeypatch)
    fake.conns["sg1.displacementShader"] = ["srcDisp"]
    fake.conns["srcDisp.displacement"] = []
    fake.exists = {"srcDisp.displacement"}

    plan = _prepare(conv)
    assert plan.ok
    assert plan.entries == []
    assert plan.skipped == 1
    assert fake.created == []


def test_duplicate_source_displacement_reuses_one_node(monkeypatch):
    conv, fake, _log = _converter(monkeypatch)
    fake.conns["mat.displacement"] = ["tex1.outAlpha"]
    fake.attrs["mat.displacementScale"] = 0.25
    fake.exists = {"disp1.out"}

    plan = _prepare(conv, ("sg1", "sg2"))
    assert plan.ok
    assert fake.created == ["disp1"]
    assert [entry["sg"] for entry in plan.entries] == ["sg1", "sg2"]


def test_apply_failure_reports_the_shading_engine(monkeypatch):
    conv, fake, _log = _converter(monkeypatch)
    fake.conns["mat.displacement"] = ["tex1.outAlpha"]
    fake.exists = {"disp1.out"}
    fake.connect_errors[("disp1.out", "sg2.displacementShader")] = RuntimeError("locked")

    plan = _prepare(conv, ("sg1", "sg2"))
    failures = conv.apply(plan)

    assert [item["sg"] for item in failures] == ["sg2"]
    assert "sg2.displacementShader" in failures[0]["reason"]


def test_convert_reports_commit_failure(monkeypatch):
    conv, fake, _log = _converter(monkeypatch)
    fake.conns["mat.displacement"] = ["tex1.outAlpha"]
    fake.connect_errors[("disp1.out", "sg2.displacementShader")] = RuntimeError("locked")

    outcome = conv.convert("mat", "mat_rs", _source_config(), _target_config(),
                           "redshift", ("sg1", "sg2"))
    assert not outcome
    assert any("sg2.displacementShader" in item for item in outcome.critical)


def test_native_to_native_is_a_noop(monkeypatch):
    conv, fake, _log = _converter(monkeypatch)
    source = types.SimpleNamespace(
        displacement_node_type="displacementShader",
        displacement_texture="displacement",
        displacement_scale="displacementScale",
    )
    target = types.SimpleNamespace(
        displacement_node_type="displacementShader",
        displacement_texture="displacement",
        displacement_scale="scale",
        displacement_output="displacement",
    )

    outcome = conv.convert("mat", "mat2", source, target, "maya", ["sg1"])
    assert outcome
    assert fake.created == []


def test_no_shading_engine_skips_quietly(monkeypatch):
    conv, fake, _log = _converter(monkeypatch)
    outcome = conv.convert("mat", "mat_rs", _source_config(), _target_config(),
                           "redshift", [])
    assert outcome
    assert fake.created == []
