import pytest

from core.builder_context import BuilderContext
from core.config_loader import ConfigLoader
from core.logger import LogLevel, Logger
from core.material_builder import MaterialBuilder
from core.prerequisites import PrerequisiteOutcome


def _make_builder(log):
    ctx = BuilderContext(logger=log)
    return MaterialBuilder(ctx, logger=log)


def test_color_chain_missing_channel_is_silent():
    """回归保护：通道不在 input_paths 时静默返回，不产生任何日志。"""
    log = Logger()
    builder = _make_builder(log)
    config = ConfigLoader().get_material_config("aiStandardSurface")
    ok = builder._build_color_chain(
        "mat1", "arnold", "hero", None, config, True, {}, "baseColor", "color"
    )
    assert ok is False
    assert log.poll(0) == []


def test_scalar_chain_missing_channel_is_silent():
    log = Logger()
    builder = _make_builder(log)
    config = ConfigLoader().get_material_config("aiStandardSurface")
    ok = builder._build_scalar_chain(
        "mat1", "hero", None, config, "metallic", "metallic", {}
    )
    assert ok is False
    assert log.poll(0) == []


def test_bump_normal_missing_channel_is_silent():
    log = Logger()
    builder = _make_builder(log)
    config = ConfigLoader().get_material_config("aiStandardSurface")
    ok = builder._build_bump_normal(
        "mat1", "arnold", "hero", None, config, {}, {}
    )
    assert ok is False
    assert log.poll(0) == []


def test_channel_without_mapping_emits_skip():
    """配置缺失仍保留 SKIP 记录（默认可见）。"""
    log = Logger()
    builder = _make_builder(log)
    config = ConfigLoader().get_material_config("aiStandardSurface")
    ok = builder._build_scalar_chain(
        "mat1", "hero", None, config, "ghostChannel", "ghost",
        {"ghostChannel": "C:/x.png"}
    )
    assert ok is False
    records = log.poll(0)
    assert len(records) == 1
    assert records[0].level == LogLevel.SKIP
    assert "no target attribute mapping" in records[0].message


def test_create_qss_names_from_material_node(monkeypatch):
    """QSS 名由唯一化后的材质节点名派生，不依赖 Maya 自动改名。"""
    log = Logger()
    builder = _make_builder(log)
    calls = []

    def fake_sets(nodes, name=None):
        calls.append(name)
        return name

    monkeypatch.setattr("maya.cmds.sets", fake_sets)
    actual = builder._create_qss("M_Material1", ["M_Material1", "M_Material1SG"])
    assert actual == "QS_M_Material1"
    assert calls == ["QS_M_Material1"]
    records = log.poll(0)
    assert len(records) == 1
    assert "QS_M_Material1" in records[0].message


def test_apply_material_prereqs_records_failures(monkeypatch):
    """回归保护（B03）：前置条件失败必须进入结构化结果，不能只写日志。"""
    log = Logger()
    builder = _make_builder(log)
    config = ConfigLoader().get_material_config("VRayMtl")
    monkeypatch.setattr(
        "core.material_builder.apply_prerequisites",
        lambda *a, **k: PrerequisiteOutcome(
            ok=False, failures=["M_hero.useRoughness=1 (locked)"]),
    )

    outcome = builder._apply_material_prereqs("M_hero", config)

    assert not outcome
    assert builder.last_build_issues == ["M_hero.useRoughness=1 (locked)"]
    errors = [r for r in log.poll(0) if r.level == LogLevel.ERROR]
    assert errors
    assert "useRoughness" in errors[0].message


def test_apply_material_prereqs_success_keeps_issues_empty(monkeypatch):
    log = Logger()
    builder = _make_builder(log)
    config = ConfigLoader().get_material_config("VRayMtl")
    monkeypatch.setattr(
        "core.material_builder.apply_prerequisites",
        lambda *a, **k: PrerequisiteOutcome(),
    )

    outcome = builder._apply_material_prereqs("M_hero", config)

    assert outcome
    assert builder.last_build_issues == []
    records = log.poll(0)
    assert not [r for r in records if r.level in (LogLevel.ERROR, LogLevel.WARN)]


def test_build_aborts_when_prerequisites_fail(monkeypatch):
    """B03：前置条件失败即中止该材质（不再产出 built=True 且无 issues）。"""
    log = Logger()
    ctx = BuilderContext(logger=log)
    builder = MaterialBuilder(ctx, logger=log)
    config = ConfigLoader().get_material_config("VRayMtl")
    monkeypatch.setattr(builder.config, "get_material_config", lambda node_type: config)
    monkeypatch.setattr(ctx, "create_node", lambda *a, **k: "M_hero")
    monkeypatch.setattr("core.material_builder.cmds.sets", lambda **kw: "M_heroSG")
    monkeypatch.setattr(
        "core.material_builder.apply_prerequisites",
        lambda *a, **k: PrerequisiteOutcome(ok=False, failures=["M_hero.useRoughness=1 (x)"]),
    )

    with pytest.raises(RuntimeError, match="prerequisites failed"):
        builder._build("VRayMtl", "hero", {})

    assert builder.last_build_issues == ["M_hero.useRoughness=1 (x)"]
