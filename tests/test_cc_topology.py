"""Unit tests for CC chain topology handling.

The source material's own graph must never be rewritten: a shared intermediate
node (layeredTexture / ramp / ...) between the source CC and the material is
copied instead, and deeper chains are reported as an explicit limitation.
"""

import types

from core.converters import cc as cc_module
from core.converters.cc import CCConverter
from core.logger import Logger


class FakeUtils:
    def __init__(self):
        self.created = []
        self.smart_connects = []
        self.params = []

    def create_cc_node(self, cc_config, base_name=None, logger=None):
        self.created.append(base_name)
        return "newCC"

    def set_cc_params(self, node, params, cc_config, logger=None):
        self.params.append((node, dict(params)))

    def smart_connect(self, src, dst, logger=None):
        self.smart_connects.append((src, dst))
        return True

    def collect_cc_chain_params(self, cc_node, cc_config, logger=None):
        return {}, None

    @staticmethod
    def node_name_from_plug(plug):
        return (plug or "").split(".", 1)[0]


class FakeConfig:
    def __init__(self, cc_config=None, materials=()):
        self.cc_config = cc_config
        self.materials = set(materials)

    def get_color_correction_config(self, renderer):
        return self.cc_config

    def identify_cc_renderer(self, node_type):
        return "arnold" if node_type else None

    def get_material_config(self, node_type):
        return object() if node_type in self.materials else None


class FakeCmds:
    def __init__(self):
        self.upstream = {}
        self.node_types = {}
        self.duplicates = {}
        self.input_pairs = {}
        self.connect_calls = []
        self.disconnect_calls = []
        self.duplicate_error = None
        self.connect_errors = {}

    def listConnections(self, node_or_plug, source=True, destination=False,
                        plugs=False, connections=False):
        if connections and plugs:
            return list(self.input_pairs.get(node_or_plug, []))
        return list(self.upstream.get(node_or_plug, []))

    def nodeType(self, node):
        return self.node_types.get(node, "layeredTexture")

    def duplicate(self, node, upstreamNodes=False, name=None):
        if self.duplicate_error is not None:
            raise self.duplicate_error
        clone = self.duplicates.get(node, name or (node + "_conv"))
        return [clone]

    def disconnectAttr(self, src, dst):
        self.disconnect_calls.append((src, dst))

    def connectAttr(self, src, dst, force=True):
        error = self.connect_errors.get(dst)
        if error is not None:
            raise error
        self.connect_calls.append((src, dst))


def _cc_config():
    return types.SimpleNamespace(
        node_type="colorCorrect", input="inColor", output="outColor")


def _make(monkeypatch, cmds=None, utils=None, config=None):
    fake_cmds = cmds or FakeCmds()
    monkeypatch.setattr(cc_module, "cmds", fake_cmds)
    fake_utils = utils or FakeUtils()
    converter = CCConverter(config or FakeConfig(_cc_config()), fake_utils,
                            logger=Logger())
    return converter, fake_cmds, fake_utils


def _entry(**overrides):
    entry = {
        "cc_node": "cc1",
        "cc_node_name": "cc1",
        "cc_out_dests": [],
        "params": {"gamma": 1.0},
        "input_plug": "file1.outColor",
        "output_plug": "cc1.outColor",
    }
    entry.update(overrides)
    return entry


def test_direct_topology_connects_target_plug(monkeypatch):
    converter, fake, utils = _make(monkeypatch)

    outcome = converter.transfer(_entry(), "mat.baseColor", "arnold")

    assert outcome
    assert utils.created == ["cc1_ai"]
    assert ("newCC.outColor", "mat.baseColor") in utils.smart_connects


def test_single_hop_copies_intermediate_node(monkeypatch):
    converter, fake, utils = _make(monkeypatch)
    fake.upstream["layered1.inputs[1].color"] = ["cc1.outColor"]
    fake.input_pairs["layered1_conv"] = [
        "layered1_conv.inputs[1].color", "cc1.outColor",
    ]

    outcome = converter.transfer(
        _entry(output_plug="layered1.outColor",
               cc_out_dests=["layered1.inputs[1].color"]),
        "mat.baseColor", "arnold")

    assert outcome
    # the source intermediate node is not touched: only the copy is rewired
    assert ("cc1.outColor", "layered1_conv.inputs[1].color") in fake.disconnect_calls
    assert ("newCC.outColor", "layered1_conv.inputs[1].color") in fake.connect_calls
    assert ("layered1_conv.outColor", "mat.baseColor") in fake.connect_calls
    assert not any("layered1.inputs" in dst for _src, dst in fake.connect_calls)


def test_single_hop_does_not_restore_source_chain(monkeypatch):
    converter, fake, _utils = _make(monkeypatch)
    fake.upstream["layered1.inputs[1].color"] = ["cc1.outColor"]
    fake.input_pairs["layered1_conv"] = []

    converter.transfer(
        _entry(output_plug="layered1.outColor",
               cc_out_dests=["layered1.inputs[1].color"]),
        "mat.baseColor", "arnold")

    # no connection back onto the source material attribute
    assert not any(dst == "mat.baseColor" and src.startswith("cc1.")
                   for src, dst in fake.connect_calls)


def test_multi_hop_chain_is_reported_as_unsupported(monkeypatch):
    converter, fake, utils = _make(monkeypatch)
    # the intermediate node's CC slot is not driven by the source CC
    fake.upstream["layered1.inputs[1].color"] = ["otherNode.outColor"]

    outcome = converter.transfer(
        _entry(output_plug="layered1.outColor",
               cc_out_dests=["layered1.inputs[1].color"]),
        "mat.baseColor", "arnold")

    assert outcome                      # conversion of the material is not failed
    assert outcome.unsupported          # ... but the limitation is reported
    assert utils.created == []           # no useless CC node is created
    assert fake.connect_calls == []


def test_single_hop_copy_failure_is_critical(monkeypatch):
    converter, fake, _utils = _make(monkeypatch)
    fake.upstream["layered1.inputs[1].color"] = ["cc1.outColor"]
    fake.duplicate_error = RuntimeError("cannot duplicate")

    outcome = converter.transfer(
        _entry(output_plug="layered1.outColor",
               cc_out_dests=["layered1.inputs[1].color"]),
        "mat.baseColor", "arnold")

    assert not outcome
    assert any("failed to copy intermediate node" in item for item in outcome.critical)


def test_single_hop_input_connect_failure_is_critical(monkeypatch):
    converter, fake, _utils = _make(monkeypatch)
    fake.upstream["layered1.inputs[1].color"] = ["cc1.outColor"]
    fake.connect_errors["layered1_conv.inputs[1].color"] = RuntimeError("locked")

    outcome = converter.transfer(
        _entry(output_plug="layered1.outColor",
               cc_out_dests=["layered1.inputs[1].color"]),
        "mat.baseColor", "arnold")

    assert not outcome
    assert any("inputs[1].color" in item for item in outcome.critical)


def test_target_without_cc_config_connects_raw_input(monkeypatch):
    config = FakeConfig(None)
    converter, _fake, utils = _make(monkeypatch, config=config)

    outcome = converter.transfer(_entry(), "mat.baseColor", "arnold")

    assert outcome
    assert utils.smart_connects == [("file1.outColor", "mat.baseColor")]
    assert utils.created == []


def test_direct_topology_with_non_material_downstream_still_wires_target(monkeypatch):
    """A shared CC that also drives a non-material node must still wire the
    new material channel (it is never part of the CC's downstream list)."""
    converter, fake, utils = _make(monkeypatch)
    entry = _entry(cc_out_dests=["lay1.inputs[0].color"])

    outcome = converter.transfer(entry, "mat.baseColor", "arnold")

    assert outcome
    # the external downstream follows the new CC ...
    assert ("newCC.outColor", "lay1.inputs[0].color") in utils.smart_connects
    # ... and the target material channel is wired explicitly
    assert ("newCC.outColor", "mat.baseColor") in utils.smart_connects


def test_cache_records_source_output_slot(monkeypatch):
    """The slot the material actually reads (e.g. outAlpha) is remembered."""
    converter, _fake, _utils = _make(monkeypatch)
    cache = {}

    converter._cache(cache, "specularRoughness", "cc1", "arnold", {"plug": "cc1.outAlpha"})

    assert cache["specularRoughness"]["source_output_attr"] == "outAlpha"


def test_cache_ignores_foreign_output_plug(monkeypatch):
    converter, _fake, _utils = _make(monkeypatch)
    cache = {}

    # the material is fed through an intermediate node, so the CC output slot is
    # unknown here
    converter._cache(cache, "baseColor", "cc1", "arnold", {"plug": "lay1.outColor"})

    assert cache["baseColor"]["source_output_attr"] is None


def test_cc_scalar_channel_prefers_source_output_slot(monkeypatch):
    """A CC driving a float channel connects through outAlpha, not outColor."""
    converter, _fake, utils = _make(monkeypatch)
    cache = {}
    converter._cache(cache, "specularRoughness", "cc1", "arnold", {"plug": "cc1.outAlpha"})

    outcome = converter.transfer(cache["specularRoughness"], "mat.specularRoughness", "arnold")

    assert outcome
    assert ("newCC.outAlpha", "mat.specularRoughness") in utils.smart_connects
    assert ("newCC.outColor", "mat.specularRoughness") not in utils.smart_connects
