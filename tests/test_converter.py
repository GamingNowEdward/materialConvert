from core import converter as converter_module
from core.config_loader import ConfigLoader
from core.converter import MaterialConverter
from core.logger import LogLevel, Logger
from core.results import ConversionResult


def _converter(logger=None):
    return MaterialConverter(config=ConfigLoader(), logger=logger or Logger())


def _result(total_sgs=2):
    return ConversionResult(material="src", created=True, new_material="src_ai",
                            total_sgs=total_sgs)


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


# --------------------------------------------------------------------------- #
# Transactional shading-engine commit
# --------------------------------------------------------------------------- #

class FakeScene:
    """Minimal wiring model for the commit/rollback pair."""

    def __init__(self, initial):
        self.current = dict(initial)
        self.connect_calls = []
        self.disconnect_calls = []
        self.connect_errors = {}
        self.list_errors = set()

    def listConnections(self, plug, source=True, destination=False, plugs=False):
        if plug in self.list_errors:
            raise RuntimeError("scene read failure")
        upstream = self.current.get(plug)
        return [upstream] if upstream else []

    def connectAttr(self, src, dst, force=True):
        error = self.connect_errors.get(dst)
        if error is not None:
            raise error
        self.connect_calls.append((src, dst))
        self.current[dst] = src

    def disconnectAttr(self, src, dst):
        self.disconnect_calls.append((src, dst))
        self.current.pop(dst, None)


def _install_scene(monkeypatch, scene):
    monkeypatch.setattr(converter_module.cmds, "listConnections", scene.listConnections)
    monkeypatch.setattr(converter_module.cmds, "connectAttr", scene.connectAttr)
    monkeypatch.setattr(converter_module.cmds, "disconnectAttr", scene.disconnectAttr)
    return scene


def test_commit_restores_every_sg_it_can_when_one_connection_fails(monkeypatch):
    scene = _install_scene(monkeypatch, FakeScene({
        "sg1.surfaceShader": "src.outColor",
        "sg2.surfaceShader": "src.outColor",
    }))
    scene.connect_errors["sg2.surfaceShader"] = RuntimeError("locked")
    conv = _converter()
    log = conv.logger
    result = _result()

    conv._commit_shading_engines(result, "src", "src_ai", ["sg1", "sg2"])

    assert result.converted is False
    assert result.wired == 0
    assert result.reason == "shading engine commit failed"
    assert [item["sg"] for item in result.sg_failures] == ["sg2"]
    assert result.wired_before_rollback == 1
    # sg1 was committed and rolled back; sg2 was never changed (its connect
    # failed), so it is skipped instead of being spuriously "restored":
    # the scene is correct and restored is True.
    assert scene.current["sg1.surfaceShader"] == "src.outColor"
    assert result.restored is True


def test_commit_rolls_back_displacement_when_disp_apply_fails(monkeypatch):
    scene = _install_scene(monkeypatch, FakeScene({
        "sg1.surfaceShader": "src.outColor",
        "sg2.surfaceShader": "src.outColor",
    }))
    conv = _converter()
    conv.disp_converter.apply = lambda plan: [{"sg": "sg2", "reason": "disp locked"}]
    result = _result()

    conv._commit_shading_engines(result, "src", "src_ai", ["sg1", "sg2"],
                                 disp_plan=object())

    assert result.converted is False
    assert result.restored is True
    assert result.sg_failures == [{"sg": "sg2", "reason": "disp locked"}]
    assert scene.current["sg1.surfaceShader"] == "src.outColor"
    assert scene.current["sg2.surfaceShader"] == "src.outColor"


def test_commit_succeeds_and_reports_wired_count(monkeypatch):
    scene = _install_scene(monkeypatch, FakeScene({
        "sg1.surfaceShader": "src.outColor",
        "sg2.surfaceShader": "src.outColor",
    }))
    scene.connect_errors.clear()
    conv = _converter()
    result = _result()

    conv._commit_shading_engines(result, "src", "src_ai", ["sg1", "sg2"])

    assert result.converted is True
    assert result.wired == 2
    assert result.restored is False
    assert scene.current["sg1.surfaceShader"] == "src_ai.outColor"
    assert scene.current["sg2.surfaceShader"] == "src_ai.outColor"


def test_unreadable_snapshot_aborts_before_rewiring(monkeypatch):
    initial = {
        "sg1.surfaceShader": "src.outColor",
        "sg2.surfaceShader": "src.outColor",
    }
    scene = _install_scene(monkeypatch, FakeScene(initial))
    # sg2's wiring cannot be read: the commit must abort before touching the
    # scene, because a later failure could then not be rolled back.
    scene.list_errors.add("sg2.surfaceShader")
    conv = _converter()
    log = conv.logger
    result = _result()

    conv._commit_shading_engines(result, "src", "src_ai", ["sg1", "sg2"])

    assert result.converted is False
    assert result.reason == "failed to snapshot shading engine wiring"
    assert result.wired == 0
    assert result.unwired is True
    assert [item["sg"] for item in result.sg_failures] == ["sg2"]
    # nothing was rewired: the scene is exactly as before
    assert scene.connect_calls == []
    assert scene.current == initial
    errors = [r for r in log.poll(0) if r.level == LogLevel.ERROR]
    assert any("could not be snapshotted" in r.message for r in errors)


def test_rollback_does_not_disconnect_an_untouched_slot(monkeypatch):
    scene = _install_scene(monkeypatch, FakeScene({
        "sg1.surfaceShader": "src.outColor",
        # no displacement wiring at all
    }))
    conv = _converter()
    conv.disp_converter.apply = lambda plan: [{"sg": "sg1", "reason": "disp locked"}]
    result = _result(total_sgs=1)

    conv._commit_shading_engines(result, "src", "src_ai", ["sg1"],
                                 disp_plan=object())

    assert result.restored is True
    assert not any(dst == "sg1.displacementShader" for _src, dst in scene.disconnect_calls)
    assert scene.current["sg1.surfaceShader"] == "src.outColor"
