from core import converter as converter_module
from core.config_loader import ConfigLoader
from core.converter import MaterialConverter
from core.logger import LogLevel, Logger


def _converter(logger=None):
    return MaterialConverter(config=ConfigLoader(), logger=logger or Logger())


def test_resolve_inverted_attrs_when_glossiness_mode(monkeypatch):
    loader = ConfigLoader()
    conv = _converter()
    vray = loader.get_material_config("VRayMtl")
    monkeypatch.setattr(converter_module.cmds, "getAttr", lambda plug: 0)
    assert conv._resolve_inverted_attrs("mat1", vray) == {
        "specularRoughness", "coatRoughness", "fuzzRoughness"}


def test_resolve_inverted_attrs_when_roughness_mode(monkeypatch):
    loader = ConfigLoader()
    conv = _converter()
    vray = loader.get_material_config("VRayMtl")
    monkeypatch.setattr(converter_module.cmds, "getAttr", lambda plug: 1)
    assert conv._resolve_inverted_attrs("mat1", vray) == set()


def test_resolve_inverted_attrs_read_failure_warns_and_inverts(monkeypatch):
    log = Logger()
    conv = _converter(log)
    vray = ConfigLoader().get_material_config("VRayMtl")

    def raise_exc(plug):
        raise RuntimeError("boom")

    monkeypatch.setattr(converter_module.cmds, "getAttr", raise_exc)
    assert conv._resolve_inverted_attrs("mat1", vray) == {
        "specularRoughness", "coatRoughness", "fuzzRoughness"}
    warns = [r for r in log.poll(0) if r.level == LogLevel.WARN]
    assert warns
    assert "Failed to read" in warns[0].message


def test_resolve_inverted_attrs_no_invert_declaration():
    loader = ConfigLoader()
    conv = _converter()
    ai = loader.get_material_config("aiStandardSurface")
    assert conv._resolve_inverted_attrs("mat1", ai) == set()
