import sys

import pytest
import maya.cmds as cmds

from core.builder_context import BuilderContext
from core.config_loader import ConfigLoader
from core.logger import LogLevel, Logger


def test_core_builder_context_imports_without_ui():
    """守护：core.builder_context 可在无 UI/PySide 环境下独立 import。

    删除 ui 相关模块与 core.builder_context 自身缓存后重新导入，必须成功，
    且不得触发任何 ui 模块加载。
    """
    for name in list(sys.modules):
        if name == "ui" or name.startswith("ui.") or name == "core.builder_context":
            del sys.modules[name]

    import core.builder_context  # noqa: F401  不应抛异常

    assert not any(name == "ui" or name.startswith("ui.") for name in sys.modules)


def test_create_node_uses_shading_node(monkeypatch):
    log = Logger()
    ctx = BuilderContext(logger=log)
    monkeypatch.setattr(cmds, "shadingNode", lambda *a, **k: "aiStandardSurface_hero")
    node = ctx.create_node("aiStandardSurface", "material", "hero")
    assert node == "aiStandardSurface_hero"


def test_build_layered_node(monkeypatch):
    log = Logger()
    ctx = BuilderContext(logger=log)
    monkeypatch.setattr(cmds, "shadingNode", lambda *a, **k: "layeredTexture_hero")
    lyr = ctx.build_layered_node("hero", None, layers=3)
    assert lyr == "layeredTexture_hero"


def test_connect_success_logs(monkeypatch):
    log = Logger()
    ctx = BuilderContext(logger=log)
    monkeypatch.setattr(cmds, "isConnected", lambda *a, **k: False)
    monkeypatch.setattr(cmds, "connectAttr", lambda *a, **k: None)
    ctx.connect("src", "outColor", "dst", "color")
    records = log.poll(0)
    assert any(r.level == LogLevel.DEBUG and "Connected" in r.message for r in records)


def test_connect_already_connected_is_idempotent(monkeypatch):
    log = Logger()
    ctx = BuilderContext(logger=log)
    monkeypatch.setattr(cmds, "isConnected", lambda *a, **k: True)
    ctx.connect("src", "outColor", "dst", "color")
    records = log.poll(0)
    assert any(r.level == LogLevel.DEBUG and "Already connected" in r.message for r in records)


def test_connect_failure_logs_error_and_raises(monkeypatch):
    log = Logger()
    ctx = BuilderContext(logger=log)

    def boom(*a, **k):
        raise RuntimeError("maya down")

    monkeypatch.setattr(cmds, "isConnected", boom)
    with pytest.raises(RuntimeError):
        ctx.connect("src", "outColor", "dst", "color")
    records = log.poll(0)
    assert any(r.level == LogLevel.ERROR for r in records)


def test_clean_path():
    assert BuilderContext.clean_path("  file:///C:/tex.png  ") == "C:/tex.png"
    assert BuilderContext.clean_path("C:/tex.png") == "C:/tex.png"


def test_get_naming():
    ctx = BuilderContext()
    naming = ctx.get_naming()
    assert "prefix" in naming
    assert "default_name" in naming


def test_injected_config_loader_is_shared():
    loader = ConfigLoader()
    ctx = BuilderContext(config_loader=loader)
    assert ctx.config is loader
    assert ctx.get_naming()["prefix"] == loader.get_builder_naming()["prefix"]