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
    """Regression guard: a channel absent from input_paths returns silently, no log."""
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
        "mat1", "hero", None, config, "metallic", "metallic", {}, False
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
    """A missing mapping still emits the SKIP record (visible by default)."""
    log = Logger()
    builder = _make_builder(log)
    config = ConfigLoader().get_material_config("aiStandardSurface")
    ok = builder._build_scalar_chain(
        "mat1", "hero", None, config, "ghostChannel", "ghost",
        {"ghostChannel": "C:/x.png"}, False
    )
    assert ok is False
    records = log.poll(0)
    assert len(records) == 1
    assert records[0].level == LogLevel.SKIP
    assert "no target attribute mapping" in records[0].message


def test_create_qss_names_from_material_node(monkeypatch):
    """The QSS name derives from the uniquified material node, not a Maya rename."""
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
    """Regression guard: prerequisite failures must reach the structured result, not just the log."""
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
    """A prerequisite failure aborts the material (no more built=True with no issues)."""
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


def test_stale_build_issues_are_cleared_before_any_raise(monkeypatch):
    """The previous material's issues must not leak into this failure detail."""
    log = Logger()
    ctx = BuilderContext(logger=log)
    builder = MaterialBuilder(ctx, logger=log)
    builder.last_build_issues = ["STALE_ISSUE_FROM_PREVIOUS_MATERIAL"]

    with pytest.raises(RuntimeError, match="Missing material config"):
        builder._build("NoSuchMaterialType", "hero", {})

    assert builder.last_build_issues == []


def test_configure_ramp_writes_configured_stops(monkeypatch):
    """A freshly created ramp must get its colorEntryList, or its output is constant."""
    log = Logger()
    builder = _make_builder(log)
    calls = []
    monkeypatch.setattr("core.material_builder.cmds.setAttr",
                        lambda *a, **k: calls.append(a))

    assert builder._configure_ramp("ramp1") == []

    assert ("ramp1.colorEntryList[0].position", 0.0) in calls
    assert ("ramp1.colorEntryList[1].position", 1.0) in calls
    assert ("ramp1.colorEntryList[0].color", 0.0, 0.0, 0.0) in calls
    assert ("ramp1.colorEntryList[1].color", 1.0, 1.0, 1.0) in calls
    assert not [r for r in log.poll(0) if r.level == LogLevel.WARN]


def test_configure_ramp_falls_back_to_black_white(monkeypatch):
    log = Logger()
    builder = _make_builder(log)
    builder.ctx._naming["ramp_stops"] = []
    calls = []
    monkeypatch.setattr("core.material_builder.cmds.setAttr",
                        lambda *a, **k: calls.append(a))

    failures = builder._configure_ramp("ramp1")

    assert ("ramp1.colorEntryList[0].color", 0.0, 0.0, 0.0) in calls
    assert ("ramp1.colorEntryList[1].color", 1.0, 1.0, 1.0) in calls
    # the fallback is reported so the result never claims the config was applied
    assert len(failures) == 1
    assert "ramp_stops" in failures[0]
    warns = [r for r in log.poll(0) if r.level == LogLevel.WARN]
    assert warns and "ramp_stops" in warns[0].message


def test_configure_ramp_write_failure_is_reported(monkeypatch):
    """A failed stop write must surface as a build issue, not a silent success."""
    log = Logger()
    builder = _make_builder(log)

    def boom(*a, **k):
        raise RuntimeError("locked")

    monkeypatch.setattr("core.material_builder.cmds.setAttr", boom)

    failures = builder._configure_ramp("ramp1")

    assert failures and all("could not write ramp stop" in f for f in failures)


def test_scalar_full_chain_records_ramp_failures(monkeypatch):
    log = Logger()
    builder = _make_builder(log)
    config = ConfigLoader().get_material_config("aiStandardSurface")
    configured = []
    monkeypatch.setattr(
        builder, "_configure_ramp",
        lambda ramp: configured.append(ramp) or ["could not write ramp stop 0 (locked)"])
    monkeypatch.setattr(builder.ctx, "create_node", lambda *a, **k: "ramp1")
    monkeypatch.setattr(builder.ctx, "connect", lambda *a, **k: None)
    monkeypatch.setattr("core.material_builder.node_utils.smart_connect",
                        lambda *a, **k: True)

    ok = builder._build_scalar_chain(
        "M1", "hero", lambda *a, **k: "tex1", config,
        "specularRoughness", "rough", {"specularRoughness": "r.png"}, True,
    )

    assert ok is True
    assert configured == ["ramp1"]
    assert any("ramp could not write ramp stop 0" in issue
               for issue in builder.last_build_issues)


def test_scalar_full_chain_configures_ramp(monkeypatch):
    log = Logger()
    builder = _make_builder(log)
    config = ConfigLoader().get_material_config("aiStandardSurface")
    configured = []
    monkeypatch.setattr(builder, "_configure_ramp",
                        lambda ramp: configured.append(ramp) or [])
    monkeypatch.setattr(builder.ctx, "create_node", lambda *a, **k: "ramp1")
    monkeypatch.setattr(builder.ctx, "connect", lambda *a, **k: None)

    ok = builder._build_scalar_chain(
        "M1", "hero", lambda *a, **k: "tex1", config,
        "specularRoughness", "rough", {"specularRoughness": "r.png"}, True,
    )

    assert ok is True
    assert configured == ["ramp1"]
    assert builder.last_build_issues == []


def test_full_chain_only_applies_to_roughness(monkeypatch):
    """Full chain applies to specularRoughness only; metallic / opacity stay direct."""
    log = Logger()
    ctx = BuilderContext(logger=log)
    builder = MaterialBuilder(ctx, logger=log)
    calls = []

    monkeypatch.setattr(builder.config, "get_material_config",
                        lambda nt: ConfigLoader().get_material_config("aiStandardSurface"))
    monkeypatch.setattr(ctx, "create_node", lambda *a, **k: "M1")
    monkeypatch.setattr(ctx, "connect", lambda *a, **k: None)
    monkeypatch.setattr("core.material_builder.cmds.sets", lambda **k: "M1SG")
    monkeypatch.setattr("core.material_builder.cmds.select", lambda *a, **k: None)
    monkeypatch.setattr("core.material_builder.cmds.pluginInfo", lambda *a, **k: True)
    monkeypatch.setattr(builder, "_build_color_chain", lambda *a, **k: False)
    monkeypatch.setattr(builder, "_build_bump_normal", lambda *a, **k: False)
    monkeypatch.setattr(builder, "_build_scalar_chain",
                        lambda *a, **k: calls.append((a[4], a[7])) or False)

    builder._build("aiStandardSurface", "hero",
                   {"specularRoughness": "r.png", "metallic": "m.png", "opacity": "o.png"},
                   use_qss=False, use_full_chain=True)

    assert dict(calls) == {"specularRoughness": True, "metallic": False, "opacity": False}
