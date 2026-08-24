import pytest

from core.config_loader import ColorCorrectionConfig, ConfigLoader
from core.logger import LogLevel, Logger
import core.node_utils as node_utils


def _cc(hue_range=None, hue_center=0):
    data = {}
    if hue_range is not None:
        data["color"] = {"hue_range": hue_range, "hue_center": hue_center}
    return ColorCorrectionConfig(data, "test")


def test_hue_no_range_passthrough():
    plain = _cc(None, 0)
    assert node_utils._hue_to_offset(42, plain) == 42
    assert node_utils._offset_to_hue(-7, plain) == -7


def test_hue_roundtrip_symmetric():
    arnold = _cc([-1, 1], 0)
    for v in (-1, -0.5, 0, 0.25, 1):
        offset = node_utils._hue_to_offset(v, arnold)
        assert offset == pytest.approx(v * 180)
        assert node_utils._offset_to_hue(offset, arnold) == pytest.approx(v)


def test_hue_roundtrip_center_offset():
    maya = _cc([0, 360], 180)
    for v in (0, 30, 90, 180, 270, 350):
        offset = node_utils._hue_to_offset(v, maya)
        assert -180 <= offset <= 180
        assert node_utils._offset_to_hue(offset, maya) == pytest.approx(v)


def test_hue_offset_wraps():
    maya = _cc([0, 360], 180)
    assert node_utils._hue_to_offset(0, maya) == -180
    assert node_utils._hue_to_offset(350, maya) == 170
    assert node_utils._hue_to_offset(200, maya) == 20
    assert node_utils._offset_to_hue(-180, maya) == 0
    assert node_utils._offset_to_hue(170, maya) == 350


def test_hue_across_renderers():
    rs = _cc([0, 360], 0)
    arnold = _cc([-1, 1], 0)
    maya = _cc([0, 360], 180)
    vray = _cc([-180, 180], 0)
    # AGENTS.md 陷阱场景：Redshift hue=0 转换后应回到 Arnold 中性值 0
    offset = node_utils._hue_to_offset(0, rs)
    assert node_utils._offset_to_hue(offset, arnold) == pytest.approx(0)
    # Redshift hue=30 -> Arnold 对称缩放
    offset = node_utils._hue_to_offset(30, rs)
    assert node_utils._offset_to_hue(offset, arnold) == pytest.approx(30 / 180)
    # Arnold hue=0.5 -> Maya 中心偏移
    offset = node_utils._hue_to_offset(0.5, arnold)
    assert node_utils._offset_to_hue(offset, maya) == pytest.approx(270)
    # Redshift hue=45 -> V-Ray 角度直通
    offset = node_utils._hue_to_offset(45, rs)
    assert node_utils._offset_to_hue(offset, vray) == pytest.approx(45)


def test_hue_roundtrip_with_real_configs():
    loader = ConfigLoader()
    samples = {
        "maya": (0, 30, 90, 180, 270, 340),
        "arnold": (-1, -0.5, 0, 0.5, 1),
        "redshift": (0, 30, 90, 180, 270, 340),
        "vray": (-180, -90, 0, 90, 180),
    }
    for renderer, values in samples.items():
        cc = loader.get_color_correction_config(renderer)
        for v in values:
            offset = node_utils._hue_to_offset(v, cc)
            assert node_utils._offset_to_hue(offset, cc) == pytest.approx(v)


def test_smart_connect_direct(monkeypatch):
    log = Logger()
    calls = []
    monkeypatch.setattr(node_utils.cmds, "isConnected", lambda a, b: False)
    monkeypatch.setattr(node_utils.cmds, "connectAttr",
                        lambda a, b, force=True: calls.append((a, b)))
    assert node_utils.smart_connect("file1.outColor", "mat1.baseColor", logger=log) is True
    assert calls == [("file1.outColor", "mat1.baseColor")]


def test_smart_connect_already_connected(monkeypatch):
    monkeypatch.setattr(node_utils.cmds, "isConnected", lambda a, b: True)
    assert node_utils.smart_connect("a.out", "b.in", logger=Logger()) is True


def test_smart_connect_outcolor_fallback(monkeypatch):
    calls = []
    state = {"n": 0}

    def connect_attr(a, b, force=True):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("type mismatch")
        calls.append((a, b))

    monkeypatch.setattr(node_utils.cmds, "isConnected", lambda a, b: False)
    monkeypatch.setattr(node_utils.cmds, "connectAttr", connect_attr)
    assert node_utils.smart_connect("file1.outAlpha", "mat1.diffuseColor",
                                    logger=Logger()) is True
    assert calls == [("file1.outColor", "mat1.diffuseColor")]


def test_smart_connect_outalpha_fallback(monkeypatch):
    calls = []
    state = {"n": 0}

    def connect_attr(a, b, force=True):
        state["n"] += 1
        if state["n"] in (1, 2):
            raise RuntimeError("fail")
        calls.append((a, b))

    monkeypatch.setattr(node_utils.cmds, "isConnected", lambda a, b: False)
    monkeypatch.setattr(node_utils.cmds, "connectAttr", connect_attr)
    assert node_utils.smart_connect("file1.outAlpha", "mat1.diffuse",
                                    logger=Logger()) is True
    assert calls == [("file1.outAlpha", "mat1.diffuse")]


def test_smart_connect_all_fail(monkeypatch):
    log = Logger()
    monkeypatch.setattr(node_utils.cmds, "isConnected", lambda a, b: False)

    def boom(a, b, force=True):
        raise RuntimeError("boom")

    monkeypatch.setattr(node_utils.cmds, "connectAttr", boom)
    assert node_utils.smart_connect("file1.outColor", "mat1.baseColor", logger=log) is False
    warns = [r for r in log.poll(0) if r.level == LogLevel.WARN]
    assert len(warns) == 1
    assert "boom" in warns[0].message


def test_smart_connect_empty_plug():
    log = Logger()
    assert node_utils.smart_connect("", "b.in", logger=log) is False
    assert node_utils.smart_connect("a.out", None, logger=log) is False
    warns = [r for r in log.poll(0) if r.level == LogLevel.WARN]
    assert len(warns) == 2