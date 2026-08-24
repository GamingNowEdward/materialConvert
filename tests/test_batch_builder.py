from core.batch_builder import BatchBuilder
from core.logger import Logger


class FakeMaterialBuilder:
    instances = []

    def __init__(self, ctx, logger=None):
        self.ctx = ctx
        self.logger = logger
        self.calls = []
        FakeMaterialBuilder.instances.append(self)

    def build(self, node_type, base_name, input_paths, use_nrm=True, use_disp=False,
              use_qss=True, use_full_chain=True, channel_options=None):
        self.calls.append({
            "node_type": node_type,
            "base_name": base_name,
            "input_paths": input_paths,
            "use_nrm": use_nrm,
            "use_disp": use_disp,
            "use_qss": use_qss,
            "use_full_chain": use_full_chain,
            "channel_options": channel_options,
        })
        return f"M_{base_name}"


def _make_batch(monkeypatch):
    monkeypatch.setattr("core.batch_builder.MaterialBuilder", FakeMaterialBuilder)
    return BatchBuilder(ctx=object(), logger=Logger())


def test_build_material_maps_channels(monkeypatch):
    bb = _make_batch(monkeypatch)
    material = {
        "name": "hero",
        "channels": {
            "baseColor": {"channel": "BaseColor", "path": "C:/hero_baseColor.png",
                          "options": {}},
            "metallic": {"channel": "Metallic", "path": "C:/hero_metallic.png",
                         "options": {"invert": True}},
        },
    }
    result = bb.build_material("aiStandardSurface", material)
    assert result == "M_hero"
    call = FakeMaterialBuilder.instances[-1].calls[-1]
    assert call["node_type"] == "aiStandardSurface"
    assert call["base_name"] == "hero"
    assert call["input_paths"] == {
        "baseColor": "C:/hero_baseColor.png",
        "metallic": "C:/hero_metallic.png",
    }
    assert call["channel_options"] == {"metallic": {"invert": True}}
    assert call["use_disp"] is False
    assert call["use_nrm"] is True
    assert call["use_qss"] is True
    assert call["use_full_chain"] is True


def test_build_material_with_displacement_sets_use_disp(monkeypatch):
    bb = _make_batch(monkeypatch)
    material = {
        "name": "terrain",
        "channels": {
            "baseColor": {"channel": "BaseColor", "path": "C:/t_baseColor.png",
                          "options": {}},
            "displacementTexture": {"channel": "Displacement",
                                    "path": "C:/t_disp.png", "options": {}},
        },
    }
    bb.build_material("RedshiftMaterial", material)
    call = FakeMaterialBuilder.instances[-1].calls[-1]
    assert call["use_disp"] is True
    assert "displacementTexture" in call["input_paths"]


def test_build_material_empty_channels(monkeypatch):
    bb = _make_batch(monkeypatch)
    material = {"name": "empty", "channels": {}}
    bb.build_material("aiStandardSurface", material)
    call = FakeMaterialBuilder.instances[-1].calls[-1]
    assert call["input_paths"] == {}
    assert call["channel_options"] == {}
    assert call["use_disp"] is False


def test_build_material_passes_chain_options(monkeypatch):
    bb = _make_batch(monkeypatch)
    material = {
        "name": "hero",
        "channels": {
            "baseColor": {"channel": "BaseColor", "path": "C:/h.png", "options": {}},
        },
    }
    bb.build_material("aiStandardSurface", material, use_full_chain=False, use_qss=False)
    call = FakeMaterialBuilder.instances[-1].calls[-1]
    assert call["use_full_chain"] is False
    assert call["use_qss"] is False