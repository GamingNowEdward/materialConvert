from core.batch_builder import BatchBuilder
from core.logger import Logger


class FakeMaterialBuilder:
    instances = []
    fail_names = set()

    def __init__(self, ctx, logger=None):
        self.ctx = ctx
        self.logger = logger
        self.calls = []
        FakeMaterialBuilder.instances.append(self)

    def build(self, node_type, base_name, input_paths, use_qss=True, use_full_chain=True,
              channel_options=None):
        if base_name in FakeMaterialBuilder.fail_names:
            raise RuntimeError(f"boom: {base_name}")
        self.calls.append({
            "node_type": node_type,
            "base_name": base_name,
            "input_paths": input_paths,
            "use_qss": use_qss,
            "use_full_chain": use_full_chain,
            "channel_options": channel_options,
        })
        return f"M_{base_name}"


def _make_batch(monkeypatch):
    monkeypatch.setattr("core.batch_builder.MaterialBuilder", FakeMaterialBuilder)
    FakeMaterialBuilder.instances = []
    FakeMaterialBuilder.fail_names = set()
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
    assert call["use_qss"] is True
    assert call["use_full_chain"] is True


def test_build_material_with_displacement_includes_channel(monkeypatch):
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
    assert "displacementTexture" in call["input_paths"]


def test_build_material_empty_channels(monkeypatch):
    bb = _make_batch(monkeypatch)
    material = {"name": "empty", "channels": {}}
    bb.build_material("aiStandardSurface", material)
    call = FakeMaterialBuilder.instances[-1].calls[-1]
    assert call["input_paths"] == {}
    assert call["channel_options"] == {}


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


def _materials(*names):
    return [{"name": name, "channels": {}} for name in names]


def _record_undo(monkeypatch, undo_calls):
    monkeypatch.setattr(
        "core.batch_builder.cmds.undoInfo", lambda **kwargs: undo_calls.append(kwargs)
    )


def test_build_all_returns_results_in_order_and_wraps_undo(monkeypatch):
    bb = _make_batch(monkeypatch)
    undo_calls = []
    _record_undo(monkeypatch, undo_calls)

    results = bb.build_all(_materials("a", "b"), "aiStandardSurface")

    assert [r.material for r in results] == ["a", "b"]
    assert [r.built for r in results] == [True, True]
    assert [r.new_material for r in results] == ["M_a", "M_b"]
    assert undo_calls == [{"openChunk": True}, {"closeChunk": True}]


def test_build_all_isolates_failures(monkeypatch):
    bb = _make_batch(monkeypatch)
    FakeMaterialBuilder.fail_names = {"bad"}

    results = bb.build_all(_materials("good", "bad", "good2"), "aiStandardSurface")

    assert [r.built for r in results] == [True, False, True]
    assert results[1].new_material is None
    assert "boom: bad" in results[1].reason


def test_build_all_progress_callback_exception_never_aborts(monkeypatch):
    bb = _make_batch(monkeypatch)
    seen = []

    def on_progress(done, total, result):
        seen.append((done, total, result.material))
        if done == 1:
            raise RuntimeError("ui exploded")

    results = bb.build_all(
        _materials("a", "b"), "aiStandardSurface", on_progress=on_progress
    )

    assert seen == [(1, 2, "a"), (2, 2, "b")]
    assert len(results) == 2


def test_build_all_empty_returns_empty_and_closes_undo(monkeypatch):
    bb = _make_batch(monkeypatch)
    undo_calls = []
    _record_undo(monkeypatch, undo_calls)

    assert bb.build_all([], "aiStandardSurface") == []
    assert undo_calls == [{"openChunk": True}, {"closeChunk": True}]


def test_build_all_closes_undo_chunk_on_progress_failure(monkeypatch):
    bb = _make_batch(monkeypatch)
    undo_calls = []
    _record_undo(monkeypatch, undo_calls)

    def on_progress(done, total, result):
        raise RuntimeError("explode")

    bb.build_all(_materials("a"), "aiStandardSurface", on_progress=on_progress)

    assert undo_calls[-1] == {"closeChunk": True}