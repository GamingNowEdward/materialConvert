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
        pass


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
    skips = [r for r in log.poll(0) if r.level == LogLevel.SKIP]
    assert len(skips) == 1
    assert "unsupported value type" in skips[0].message


def test_transfer_missing_target_plug(monkeypatch):
    log = Logger()
    conv = _conv(log)
    monkeypatch.setattr(attribute_module.cmds, "objExists", lambda plug: False)
    ok = conv._transfer_one("mat1", "baseColor", "srcColor",
                            {"value": 0.5, "connection": None}, {}, "arnold")
    assert ok is False
    skips = [r for r in log.poll(0) if r.level == LogLevel.SKIP]
    assert len(skips) == 1
    assert "does not exist" in skips[0].message


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