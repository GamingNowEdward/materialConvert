from core.config_loader import ConfigLoader
from core.converters import attribute as attribute_module
from core.converters.attribute import AttributeConverter
from core.logger import LogLevel, Logger


class FakeUtils:
    def __init__(self):
        self.calls = []

    def collect_attribute_info(self, mat, attrs, logger=None):
        self.calls.append(("collect", mat, sorted(attrs)))
        return {a: {"value": None, "connection": None, "plug": f"{mat}.{a}"}
                for a in attrs}

    def node_name_from_plug(self, plug):
        return (plug or "").split(".")[0]

    def smart_connect(self, src, dst, logger=None):
        self.calls.append(("smart_connect", src, dst))
        return True

    def is_cc_node(self, node, config, logger=None):
        return False


class FakeCC:
    def transfer(self, *args, **kwargs):
        from core.results import TransferOutcome

        return TransferOutcome()


def _conv(logger=None):
    return AttributeConverter(ConfigLoader(), FakeUtils(), FakeCC(),
                              logger or Logger())


def test_collect_attrs_includes_common_and_bump():
    loader = ConfigLoader()
    utils = FakeUtils()
    conv = AttributeConverter(loader, utils, FakeCC(), Logger())
    src = loader.get_material_config("aiStandardSurface")
    conv.collect_attrs("mat1", src)
    _, mat, attrs = utils.calls[0]
    assert mat == "mat1"
    assert "baseColor" in attrs
    assert "normalCamera" in attrs
    assert "specularRoughness" in attrs


def test_zero_black_colors():
    loader = ConfigLoader()
    conv = _conv()
    src = loader.get_material_config("aiStandardSurface")
    attr_info = {
        "baseColor": {"value": (0, 0, 0), "connection": None, "plug": "m.baseColor"},
        "base": {"value": 1.0, "connection": None, "plug": "m.base"},
        "specularColor": {"value": (0.5, 0.5, 0.5), "connection": None,
                          "plug": "m.specularColor"},
        "specular": {"value": 1.0, "connection": None, "plug": "m.specular"},
        "emissionColor": {"value": (0, 0, 0), "connection": "file1.outColor",
                          "plug": "m.emissionColor"},
        "emission": {"value": 1.0, "connection": None, "plug": "m.emission"},
    }
    conv._zero_black_colors(attr_info, src)
    assert attr_info["base"]["value"] == 0
    assert attr_info["specular"]["value"] == 1.0
    assert attr_info["emission"]["value"] == 1.0


def test_transfer_float_broadcast_to_color(monkeypatch):
    conv = _conv()
    calls = []
    monkeypatch.setattr(attribute_module.cmds, "objExists", lambda plug: True)
    monkeypatch.setattr(attribute_module.cmds, "getAttr",
                        lambda plug, type=None: "float3")
    monkeypatch.setattr(attribute_module.cmds, "setAttr",
                        lambda plug, *v: calls.append((plug, v)))
    ok = conv._transfer_one("mat1", "baseColor", "srcColor",
                            {"value": 0.5, "connection": None}, {}, "arnold")
    assert ok is True
    assert calls == [("mat1.baseColor", (0.5, 0.5, 0.5))]


def test_transfer_float_to_float(monkeypatch):
    conv = _conv()
    calls = []
    monkeypatch.setattr(attribute_module.cmds, "objExists", lambda plug: True)
    monkeypatch.setattr(attribute_module.cmds, "getAttr",
                        lambda plug, type=None: "float")
    monkeypatch.setattr(attribute_module.cmds, "setAttr",
                        lambda plug, *v: calls.append((plug, v)))
    ok = conv._transfer_one("mat1", "metallic", "srcVal",
                            {"value": 0.8, "connection": None}, {}, "arnold")
    assert ok is True
    assert calls == [("mat1.metallic", (0.8,))]


def test_transfer_color_falls_back_first_channel(monkeypatch):
    conv = _conv()
    calls = []
    state = {"n": 0}

    def set_attr(plug, *v):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("float3 -> float")
        calls.append((plug, v))

    monkeypatch.setattr(attribute_module.cmds, "objExists", lambda plug: True)
    monkeypatch.setattr(attribute_module.cmds, "setAttr", set_attr)
    ok = conv._transfer_one("mat1", "roughness", "srcColor",
                            {"value": (0.2, 0.3, 0.4), "connection": None},
                            {}, "arnold")
    assert ok is True
    assert calls == [("mat1.roughness", (0.2,))]


def test_transfer_color_all_fail(monkeypatch):
    log = Logger()
    conv = _conv(log)

    def set_attr(plug, *v):
        raise RuntimeError("boom")

    monkeypatch.setattr(attribute_module.cmds, "objExists", lambda plug: True)
    monkeypatch.setattr(attribute_module.cmds, "setAttr", set_attr)
    ok = conv._transfer_one("mat1", "roughness", "srcColor",
                            {"value": (0.2, 0.3, 0.4), "connection": None},
                            {}, "arnold")
    assert ok is False
    warns = [r for r in log.poll(0) if r.level == LogLevel.WARN]
    assert len(warns) == 1
    assert "failed to set color value" in warns[0].message


def test_transfer_unsupported_type(monkeypatch):
    log = Logger()
    conv = _conv(log)
    monkeypatch.setattr(attribute_module.cmds, "objExists", lambda plug: True)
    ok = conv._transfer_one("mat1", "baseColor", "srcColor",
                            {"value": "hello", "connection": None}, {}, "arnold")
    assert ok is False
    warns = [r for r in log.poll(0) if r.level == LogLevel.WARN]
    assert len(warns) == 1
    assert "unsupported value type" in warns[0].message


def test_transfer_missing_target_plug(monkeypatch):
    log = Logger()
    conv = _conv(log)
    monkeypatch.setattr(attribute_module.cmds, "objExists", lambda plug: False)
    ok = conv._transfer_one("mat1", "baseColor", "srcColor",
                            {"value": 0.5, "connection": None}, {}, "arnold")
    assert ok is False
    warns = [r for r in log.poll(0) if r.level == LogLevel.WARN]
    assert len(warns) == 1
    assert "does not exist" in warns[0].message


def test_fix_vray_emission_triggers(monkeypatch):
    loader = ConfigLoader()
    conv = _conv()
    src = loader.get_material_config("VRayMtl")
    target = loader.get_material_config("RedshiftMaterial")
    attr_info = {"illumColor": {"value": (1, 0, 0), "connection": None,
                                "plug": "m.illumColor"}}
    calls = []
    monkeypatch.setattr(attribute_module.cmds, "setAttr",
                        lambda plug, v: calls.append((plug, v)))
    conv._fix_vray_emission(attr_info, src, "mat1", target)
    assert calls == [("mat1.emission_weight", 1)]


def test_fix_vray_emission_skips_when_source_has_weight(monkeypatch):
    loader = ConfigLoader()
    conv = _conv()
    src = loader.get_material_config("aiStandardSurface")
    target = loader.get_material_config("RedshiftMaterial")
    calls = []
    monkeypatch.setattr(attribute_module.cmds, "setAttr",
                        lambda plug, v: calls.append((plug, v)))
    conv._fix_vray_emission({}, src, "mat1", target)
    assert calls == []


def test_fix_vray_emission_black_without_connection_skips(monkeypatch):
    loader = ConfigLoader()
    conv = _conv()
    src = loader.get_material_config("VRayMtl")
    target = loader.get_material_config("RedshiftMaterial")
    attr_info = {"illumColor": {"value": (0, 0, 0), "connection": None,
                                "plug": "m.illumColor"}}
    calls = []
    monkeypatch.setattr(attribute_module.cmds, "setAttr",
                        lambda plug, v: calls.append((plug, v)))
    conv._fix_vray_emission(attr_info, src, "mat1", target)
    assert calls == []


def test_transfer_scalar_invert(monkeypatch):
    conv = _conv()
    calls = []
    monkeypatch.setattr(attribute_module.cmds, "objExists", lambda plug: True)
    monkeypatch.setattr(attribute_module.cmds, "getAttr",
                        lambda plug, type=None: "float")
    monkeypatch.setattr(attribute_module.cmds, "setAttr",
                        lambda plug, *v: calls.append((plug, v)))
    ok = conv._transfer_one("mat1", "specularRoughness", "reflectionGlossiness",
                            {"value": 0.25, "connection": None}, {}, "arnold",
                            invert=True)
    assert ok is True
    assert calls == [("mat1.specularRoughness", (0.75,))]


def test_transfer_scalar_invert_false_keeps_value(monkeypatch):
    conv = _conv()
    calls = []
    monkeypatch.setattr(attribute_module.cmds, "objExists", lambda plug: True)
    monkeypatch.setattr(attribute_module.cmds, "getAttr",
                        lambda plug, type=None: "float")
    monkeypatch.setattr(attribute_module.cmds, "setAttr",
                        lambda plug, *v: calls.append((plug, v)))
    conv._transfer_one("mat1", "specularRoughness", "reflectionGlossiness",
                       {"value": 0.25, "connection": None}, {}, "arnold",
                       invert=False)
    assert calls == [("mat1.specularRoughness", (0.25,))]


def test_apply_inversions_inserts_reverse_node(monkeypatch):
    loader = ConfigLoader()
    utils = FakeUtils()
    conv = AttributeConverter(loader, utils, FakeCC(), Logger())
    source = loader.get_material_config("VRayMtl")
    target = loader.get_material_config("aiStandardSurface")

    created = []
    cmds_calls = []
    monkeypatch.setattr(attribute_module.cmds, "objExists", lambda plug: True)
    monkeypatch.setattr(attribute_module.cmds, "listConnections",
                        lambda *a, **k: ["file1.outAlpha"])
    monkeypatch.setattr(attribute_module.cmds, "disconnectAttr",
                        lambda src, dst: cmds_calls.append(("disconnect", src, dst)))
    monkeypatch.setattr(
        attribute_module.cmds, "shadingNode",
        lambda node_type, **k: created.append(node_type)
        or "mat1_reflectionGlossiness_invert")
    monkeypatch.setattr(attribute_module.cmds, "connectAttr",
                        lambda src, dst, force=False: cmds_calls.append(("connect", src, dst)))

    conv._apply_inversions("mat1", source, target, {"specularRoughness"})

    # Node is named after the SOURCE glossiness attribute, not the target roughness plug.
    assert created == ["reverse"]
    assert ("disconnect", "file1.outAlpha", "mat1.specularRoughness") in cmds_calls
    assert ("connect", "mat1_reflectionGlossiness_invert.outputX",
            "mat1.specularRoughness") in cmds_calls
    assert ("smart_connect", "file1.outAlpha",
            "mat1_reflectionGlossiness_invert.inputX") in utils.calls


def test_apply_inversions_skips_value_channel(monkeypatch):
    loader = ConfigLoader()
    utils = FakeUtils()
    conv = AttributeConverter(loader, utils, FakeCC(), Logger())
    source = loader.get_material_config("VRayMtl")
    target = loader.get_material_config("aiStandardSurface")
    created = []
    monkeypatch.setattr(attribute_module.cmds, "objExists", lambda plug: True)
    monkeypatch.setattr(attribute_module.cmds, "listConnections",
                        lambda *a, **k: [])
    monkeypatch.setattr(attribute_module.cmds, "shadingNode",
                        lambda node_type, **k: created.append(node_type) or "rev")
    conv._apply_inversions("mat1", source, target, {"specularRoughness"})
    assert created == []


def test_trace_alpha_plug_follows_only_upstream(monkeypatch):
    """Regression: node-level listConnections must pass destination=False.

    Without it, Maya returned *.message / defaultRenderUtilityList plumbing and
    downstream plugs, so the alpha trace could jump into an unrelated material
    network and enable alphaIsLuminance on the wrong file.
    """
    conv = _conv()
    upstream_only = {
        "mat1.specularRoughness": ["rev.outputX"],
        "rev": ["realFile.outAlpha"],
    }
    # What a source=True-only query would return on node names (cross-talk).
    any_direction = {
        "mat1.specularRoughness": ["rev.outputX"],
        "rev": ["otherFile.outAlpha"],
    }

    def list_connections(node, plugs=False, source=False, destination=None):
        table = upstream_only if destination is False else any_direction
        return table.get(node, [])

    monkeypatch.setattr(attribute_module.cmds, "listConnections", list_connections)
    monkeypatch.setattr(attribute_module.cmds, "attributeQuery",
                        lambda attr, node=None, exists=True:
                        node in ("realFile", "otherFile"))
    assert conv._trace_alpha_plug("mat1.specularRoughness") == "realFile.outAlpha"


# --------------------------------------------------------------------------- #
# Alpha Is Luminance logging volume
# --------------------------------------------------------------------------- #

class _AlphaConfig:
    def __init__(self, attr_map):
        self.attr_map = attr_map


def test_missing_alpha_source_is_summarized_once(monkeypatch):
    """A material with ~30 mapped attributes must not log one line per attribute."""
    log = Logger()
    conv = _conv(log)
    target = ConfigLoader().get_material_config("aiStandardSurface")
    monkeypatch.setattr(attribute_module.cmds, "objExists", lambda plug: True)
    monkeypatch.setattr(attribute_module.cmds, "listConnections", lambda *a, **k: [])

    failed, notes = conv._fix_alpha_luminance("mat1", "arnold", target)

    assert failed == []
    assert notes == []
    records = log.poll(0)
    assert not [r for r in records if "No alpha source traced" in r.message]
    summaries = [r for r in records if "no alpha source" in r.message]
    assert len(summaries) == 1
    assert summaries[0].level == LogLevel.DEBUG


def test_shared_target_attribute_is_traced_once(monkeypatch):
    """Two common attrs mapping to one target plug must not walk it twice."""
    log = Logger()
    conv = _conv(log)
    calls = []
    monkeypatch.setattr(conv, "_trace_alpha_plug",
                        lambda plug, *a, **k: calls.append(plug))
    monkeypatch.setattr(attribute_module.cmds, "objExists", lambda plug: True)

    conv._fix_alpha_luminance(
        "mat1", "arnold",
        _AlphaConfig({"a": "shared", "b": "shared", "c": "other"}),
    )
    assert calls == ["mat1.shared", "mat1.other"]


def test_found_alpha_source_is_still_logged(monkeypatch):
    """A real hit stays at DEBUG (trace hit + enable), and nothing says "no source"."""
    log = Logger()
    conv = _conv(log)
    monkeypatch.setattr(attribute_module.cmds, "objExists", lambda plug: True)
    monkeypatch.setattr(attribute_module.cmds, "listConnections",
                        lambda *a, **k: ["tex1.outAlpha"])
    monkeypatch.setattr(attribute_module.cmds, "attributeQuery", lambda *a, **k: True)
    monkeypatch.setattr(attribute_module.cmds, "getAttr", lambda *a, **k: False)
    set_calls = []
    monkeypatch.setattr(attribute_module.cmds, "setAttr",
                        lambda *a, **k: set_calls.append(a))

    failed, notes = conv._fix_alpha_luminance("mat1", "arnold", _AlphaConfig({"a": "shared"}))

    assert failed == []
    assert set_calls == [("tex1.alphaIsLuminance", True)]
    # Enabling it on a non-opacity channel is now reported.
    assert len(notes) == 1
    assert "non-opacity channel" in notes[0]
    messages = [r.message for r in log.poll(0)]
    assert any("Alpha source found" in m for m in messages)
    assert any("Enabled Alpha Is Luminance on tex1" in m for m in messages)
    assert not any("no alpha source" in m for m in messages)
