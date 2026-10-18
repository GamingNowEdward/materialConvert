"""Offline configuration schema tests (review finding O02)."""

import json

from core import config_schema


def _base(tmp_path):
    mat = tmp_path / "material"
    mat.mkdir(parents=True)
    (mat / "common.json").write_text(json.dumps({
        "color": {"baseColor": "baseColor"},
        "scalar": {"specularRoughness": "roughness"},
        "color_weight_pairs": [["baseColor", "baseWeight"]],
    }), encoding="utf-8")
    (mat / "TestMat.json").write_text(json.dumps({
        "material": {"node_type": "testMat", "uiPanel_display_name": "Test",
                     "renderer": "arnold"},
        "color": {"baseColor": "baseColor"},
        "scalar": {"specularRoughness": "roughness"},
    }), encoding="utf-8")
    (tmp_path / "bumpNormal.json").write_text(json.dumps({
        "common": {"normal": {"scale": "scale", "file_source": "outColor"}},
        "arnold": {"normal": {"node_type": "aiNormalMap", "input": "input",
                              "output": "outValue"}},
    }), encoding="utf-8")
    (tmp_path / "colorCorrection.json").write_text(json.dumps({
        "common": {"base": {"gamma": "gamma"}},
        "arnold": {"material": {"node_type": "aiColorCorrect", "input": "input",
                                "output": "outColor"}},
    }), encoding="utf-8")
    (tmp_path / "texture_channels.json").write_text(json.dumps({
        "extensions": [".png"],
        "channels": {"BaseColor": {"aliases": ["basecolor"],
                                   "common_attr": "baseColor", "type": "color"}},
    }), encoding="utf-8")
    (tmp_path / "builder_naming.json").write_text(json.dumps({
        "layered_colors": [[1, 1, 1]],
        "layered_blend_modes": [0],
    }), encoding="utf-8")
    return tmp_path


def _errors(issues):
    return [issue for issue in issues if issue.level == "ERROR"]


def _write_material(tmp_path, filename, payload):
    (tmp_path / "material" / filename).write_text(json.dumps(payload), encoding="utf-8")


def test_shipped_config_is_clean():
    assert config_schema.run_all() == []


def test_missing_material_block_is_an_error(tmp_path):
    _base(tmp_path)
    _write_material(tmp_path, "TestMat.json", {"color": {"baseColor": "baseColor"}})

    issues = config_schema.run_all(str(tmp_path))

    assert any("missing 'material'" in issue.message for issue in _errors(issues))


def test_unknown_renderer_is_an_error(tmp_path):
    _base(tmp_path)
    _write_material(tmp_path, "TestMat.json", {
        "material": {"node_type": "testMat", "uiPanel_display_name": "Test",
                     "renderer": "unreal"},
    })

    issues = config_schema.run_all(str(tmp_path))

    assert any("unknown renderer" in issue.message for issue in _errors(issues))


def test_non_object_section_is_an_error(tmp_path):
    _base(tmp_path)
    _write_material(tmp_path, "TestMat.json", {
        "material": {"node_type": "testMat", "uiPanel_display_name": "Test",
                     "renderer": "arnold"},
        "color": ["baseColor"],
    })

    issues = config_schema.run_all(str(tmp_path))

    assert any("section must be an object" in issue.message for issue in _errors(issues))


def test_duplicate_node_type_is_an_error(tmp_path):
    _base(tmp_path)
    _write_material(tmp_path, "ZZDuplicate.json", {
        "material": {"node_type": "testMat", "uiPanel_display_name": "Other",
                     "renderer": "arnold"},
    })

    issues = config_schema.run_all(str(tmp_path))

    assert any("duplicate node_type 'testMat'" in issue.message
               for issue in _errors(issues))


def test_missing_attribute_name_is_an_error(tmp_path):
    _base(tmp_path)
    _write_material(tmp_path, "TestMat.json", {
        "material": {"node_type": "testMat", "uiPanel_display_name": "Test",
                     "renderer": "arnold"},
        "scalar": {"specularRoughness": 5},
    })

    issues = config_schema.run_all(str(tmp_path))

    assert any("attribute mapping must be a string" in issue.message
               for issue in _errors(issues))


def test_incomplete_prerequisite_is_an_error(tmp_path):
    _base(tmp_path)
    _write_material(tmp_path, "TestMat.json", {
        "material": {"node_type": "testMat", "uiPanel_display_name": "Test",
                     "renderer": "arnold"},
        "scalar": {"specularRoughness": "roughness",
                   "prerequisites": {"bad": {"attribute": "x"}}},
    })

    issues = config_schema.run_all(str(tmp_path))

    assert any("missing value" in issue.message for issue in _errors(issues))


def test_unknown_common_attr_reference_is_a_warning(tmp_path):
    _base(tmp_path)
    _write_material(tmp_path, "TestMat.json", {
        "material": {"node_type": "testMat", "uiPanel_display_name": "Test",
                     "renderer": "arnold"},
        "color": {"ghostAttr": "ghostAttr"},
    })

    issues = config_schema.run_all(str(tmp_path))

    warnings = [i for i in issues if i.level == "WARN"]
    assert any("ghostAttr" in issue.field_path for issue in warnings)


def test_texture_channel_unknown_common_attr_is_an_error(tmp_path):
    _base(tmp_path)
    (tmp_path / "texture_channels.json").write_text(json.dumps({
        "extensions": [".png"],
        "channels": {"Bad": {"aliases": ["bad"], "common_attr": "noSuchAttr"}},
    }), encoding="utf-8")

    issues = config_schema.run_all(str(tmp_path))

    assert any("unknown common attribute 'noSuchAttr'" in issue.message
               for issue in _errors(issues))


def test_builder_naming_length_mismatch_is_an_error(tmp_path):
    _base(tmp_path)
    (tmp_path / "builder_naming.json").write_text(json.dumps({
        "layered_colors": [[1, 1, 1], [0, 0, 0]],
        "layered_blend_modes": [0],
    }), encoding="utf-8")

    issues = config_schema.run_all(str(tmp_path))

    assert any("same length" in issue.message for issue in _errors(issues))


def test_normal_space_value_must_be_a_mode_value(tmp_path):
    _base(tmp_path)
    (tmp_path / "bumpNormal.json").write_text(json.dumps({
        "common": {},
        "arnold": {"normal": {
            "node_type": "aiNormalMap", "input": "input", "output": "outValue",
            "is_normal": "inputType", "is_normal_value": [1, 2],
            "normal_space": {"tangent": 1, "object": 9},
        }},
    }), encoding="utf-8")

    issues = config_schema.run_all(str(tmp_path))

    assert any("is not part of is_normal_value" in issue.message
               for issue in _errors(issues))


def test_mode_switch_requires_paired_value(tmp_path):
    _base(tmp_path)
    (tmp_path / "bumpNormal.json").write_text(json.dumps({
        "common": {},
        "arnold": {"normal": {
            "node_type": "aiNormalMap", "input": "input", "output": "outValue",
            "is_normal": "inputType",
        }},
    }), encoding="utf-8")

    issues = config_schema.run_all(str(tmp_path))

    assert any("declared together" in issue.message for issue in _errors(issues))


def test_color_correction_requires_material_block(tmp_path):
    _base(tmp_path)
    (tmp_path / "colorCorrection.json").write_text(json.dumps({
        "common": {},
        "arnold": {"base": {"gamma": "gamma"}},
    }), encoding="utf-8")

    issues = config_schema.run_all(str(tmp_path))

    assert any("missing 'material' object" in issue.message for issue in _errors(issues))


def test_extra_nodes_require_type_and_path(tmp_path):
    _base(tmp_path)
    (tmp_path / "bumpNormal.json").write_text(json.dumps({
        "common": {},
        "arnold": {"normal": {
            "node_type": "aiNormalMap", "input": "input", "output": "outValue",
            "extra_nodes": [{"output": "out"}],
        }},
    }), encoding="utf-8")

    issues = config_schema.run_all(str(tmp_path))

    messages = " ".join(issue.message for issue in _errors(issues))
    assert "node_type" in messages and "path" in messages


def test_loader_keeps_first_duplicate_and_sorts_files(tmp_path, monkeypatch):
    from core.config_loader import ConfigLoader
    from core.logger import get_logger

    _base(tmp_path)
    _write_material(tmp_path, "AAAFirst.json", {
        "material": {"node_type": "testMat", "uiPanel_display_name": "First",
                     "renderer": "arnold"},
    })
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", str(tmp_path))

    logger = get_logger()
    logger.poll(0)
    loader = ConfigLoader()

    kept = loader.get_material_config("testMat")
    assert kept.filename == "AAAFirst.json"  # sorted load order decides
    errors = [r for r in logger.poll(0) if "duplicate node_type" in r.message]
    assert errors
