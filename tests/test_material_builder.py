from core.builder_context import BuilderContext
from core.config_loader import ConfigLoader
from core.logger import LogLevel, Logger
from core.material_builder import MaterialBuilder


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
        "mat1", "arnold", "hero", None, config, True, {}, {}
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