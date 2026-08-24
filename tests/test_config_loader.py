import json

from core.config_loader import ConfigLoader, normalize_keyword

VALID_RENDERERS = {"arnold", "redshift", "vray"}


def test_normalize_keyword():
    assert normalize_keyword("Base_Color") == "basecolor"
    assert normalize_keyword("spec-rough") == "specrough"


def test_material_configs_satisfy_spec():
    """AGENTS.md hard rule: every material JSON must carry
    uiPanel_display_name and renderer with a valid value."""
    loader = ConfigLoader()
    configs = loader.get_all_material_configs()
    assert len(configs) >= 6
    for node_type, cfg in configs.items():
        assert cfg.uiPanel_display_name, f"{node_type}: missing uiPanel_display_name"
        assert cfg.renderer in VALID_RENDERERS, f"{node_type}: bad renderer {cfg.renderer!r}"
        assert cfg.node_type, f"{node_type}: missing node_type"
        assert cfg.attr_map, f"{node_type}: empty attr_map"


def test_material_attr_map_covers_essential_common_attrs():
    loader = ConfigLoader()
    common = loader.get_common_attrs()
    assert "baseColor" in common
    assert "specularRoughness" in common
    for cfg in loader.get_all_material_configs().values():
        for essential in ("baseColor", "specularRoughness", "metallic",
                          "opacity", "normal_bump"):
            assert cfg.get_maya_attr(essential), (
                f"{cfg.node_type}: no mapping for {essential}"
            )


def test_displacement_defaults():
    loader = ConfigLoader()
    for cfg in loader.get_all_material_configs().values():
        assert cfg.displacement_node_type, f"{cfg.node_type}: no displacement node_type"
        assert cfg.displacement_file_source == "outAlpha", cfg.node_type
        assert cfg.displacement_lyr_src in ("outAlpha", "outColor"), cfg.node_type
        assert cfg.displacement_output, cfg.node_type


def test_prerequisites_parsed():
    loader = ConfigLoader()
    rs = loader.get_material_config("RedshiftMaterial")
    assert rs.get_prerequisites()["refl_brdf"] == {"attribute": "refl_brdf", "value": 1}
    assert rs.get_attr_prerequisites("metallic") == {
        "attribute": "refl_fresnel_mode", "value": 2
    }
    vray = loader.get_material_config("VRayMtl")
    assert vray.get_prerequisites()["roughness_mode"]["attribute"] == "useRoughness"
    assert vray.get_prerequisites()["reflection_color"]["value"] == [1, 1, 1]


def test_color_weight_pairs_roundtrip():
    loader = ConfigLoader()
    pairs = loader.get_color_weight_pairs()
    assert pairs
    for color_attr, weight_attr in pairs:
        assert loader.get_weight_attr_for_common_attr(color_attr) == weight_attr
    assert loader.get_weight_attr_for_common_attr("nonexistent") == ""


def test_bump_normal_configs_merged_from_common():
    loader = ConfigLoader()
    arnold = loader.get_bump_normal_config("arnold")
    assert arnold is not None
    assert arnold.bump and arnold.normal
    # arnold.bump 未在 JSON 定义 input -> 从 common 段合并
    assert arnold.bump.input == "input"
    assert arnold.normal.scale == "strength"
    vray = loader.get_bump_normal_config("vray")
    assert vray.bump.is_material_attribute is True
    # vray 显式定义的值不被 common 覆盖
    assert vray.bump.input == "bumpMap"
    assert vray.bump.input_type == "bumpMapType"
    assert vray.bump.input_type_value == 0


def test_cc_configs_and_identify():
    loader = ConfigLoader()
    cc_configs = loader.get_all_cc_configs()
    expected = {
        "maya": ("colorCorrect", [0, 360], 180),
        "arnold": ("aiColorCorrect", [-1, 1], 0),
        "redshift": ("RedshiftColorCorrection", [0, 360], 0),
        "vray": ("VRayColorCorrection", [-180, 180], 0),
    }
    for renderer, (node_type, hue_range, center) in expected.items():
        cc = cc_configs[renderer]
        assert cc.node_type == node_type
        assert cc.hue_range == hue_range
        assert cc.hue_center == center
        assert loader.identify_cc_renderer(node_type) == renderer
    # maya 显式 gamma="" 保持空，不被 common 覆盖
    assert cc_configs["maya"].gamma == ""
    # vray 显式 gamma="" 同样保留（common 合并只补缺失字段）
    assert cc_configs["vray"].gamma == ""


def test_filename_role_keywords():
    loader = ConfigLoader()
    roles = loader.get_filename_role_keywords()
    assert "basecolor" in roles["srgb"]
    assert "albedo" in roles["srgb"]
    assert "color" in roles["srgb"]
    assert "metallic" in roles["raw"]
    assert "roughness" in roles["raw"]
    assert "normal" in roles["raw"]
    assert "displacement" in roles["raw"]
    # 短别名（len < 5）被过滤，避免子串误触
    short = {"col", "dif", "base", "diff", "spec", "refl", "refr", "glos",
             "bmp", "nrm", "sss", "emit", "disp", "opac", "glow", "nmap", "fuzz"}
    for word in short:
        assert word not in roles["srgb"], f"{word} leaked into srgb"
        assert word not in roles["raw"], f"{word} leaked into raw"
    assert set(roles["srgb"]).isdisjoint(roles["raw"])


def test_expanded_attribute_keywords():
    loader = ConfigLoader()
    expanded = loader.get_expanded_attribute_keywords()
    assert "basecolor" in expanded["srgb"]
    assert "sheencolor" in expanded["srgb"]
    assert "illumcolor" in expanded["srgb"]
    assert "metalness" in expanded["raw"]
    assert "normalcamera" in expanded["raw"]
    assert "diffuseroughness" in expanded["raw"]
    assert "geometryopacity" in expanded["raw"]
    assert "bumpmap" in expanded["raw"]


def test_find_bn_renderer():
    loader = ConfigLoader()
    renderer, mapping = loader.find_bn_renderer("bump2d")
    assert renderer == "maya"
    assert mapping.node_type == "bump2d"
    renderer, mapping = loader.find_bn_renderer("RedshiftBumpMap")
    assert renderer == "redshift"
    assert loader.find_bn_renderer("nonexistent") == (None, None)
    types = loader.get_all_bn_types()
    assert {"bump2d", "aiBump2d", "aiNormalMap", "RedshiftBumpMap"} <= types


def test_display_and_renderer_name():
    loader = ConfigLoader()
    assert loader.get_display_name("aiStandardSurface") == "Arnold Standard Surface"
    assert loader.get_display_name("nonexistent") == "nonexistent"
    assert loader.get_renderer_name("RedshiftMaterial") == "redshift"
    assert loader.get_renderer_name("nonexistent") == "unknown"


def test_builder_naming():
    loader = ConfigLoader()
    naming = loader.get_builder_naming()
    assert naming["qss_prefix"] == "QS_M_"
    for key in ("material", "p2d", "file", "layered", "ramp", "cc"):
        assert naming["prefix"][key]
    assert len(naming["layered_colors"]) == len(naming["layered_blend_modes"])


def _write_temp_config(tmp_path):
    material_dir = tmp_path / "material"
    material_dir.mkdir()
    (material_dir / "common.json").write_text(json.dumps({}), encoding="utf-8")
    bn = {
        "common": {
            "bump": {"scale": "scale", "input": "input",
                     "file_source": "outAlpha", "default_scale": 0.1},
            "normal": {"scale": "scale", "input": "input",
                       "file_source": "outColor", "default_scale": 1.0},
        },
        "mytest": {
            "bump": {"node_type": "TestBump", "input": "customInput",
                     "is_material_attribute": False},
            "normal": {"node_type": "TestNormal"},
        },
    }
    (tmp_path / "bumpNormal.json").write_text(json.dumps(bn), encoding="utf-8")
    cc = {
        "common": {"base": {"gamma": "gamma"}, "color": {"hue": "hue"}},
        "mytest": {"material": {"node_type": "TestCC"}},
    }
    (tmp_path / "colorCorrection.json").write_text(json.dumps(cc), encoding="utf-8")
    return material_dir


def test_renderer_config_common_merge(tmp_path, monkeypatch):
    _write_temp_config(tmp_path)
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", str(tmp_path))
    loader = ConfigLoader()
    bn = loader.get_bump_normal_config("mytest")
    assert bn.bump.input == "customInput"
    assert bn.bump.scale == "scale"
    assert bn.normal.scale == "scale"
    assert bn.normal.input == "input"
    cc = loader.get_color_correction_config("mytest")
    assert cc.node_type == "TestCC"
    assert cc.gamma == "gamma"
    assert cc.hue == "hue"


def test_material_config_section_prerequisites(tmp_path, monkeypatch):
    material_dir = _write_temp_config(tmp_path)
    (material_dir / "TestMat.json").write_text(json.dumps({
        "material": {
            "node_type": "TestMat",
            "uiPanel_display_name": "Test",
            "renderer": "arnold",
            "prerequisites": {"a": {"attribute": "attrA", "value": 1}},
        },
        "base": {
            "baseColor": "baseColor",
            "prerequisites": {"baseColor": {"attribute": "attrB", "value": [1, 0, 0]}},
        },
        "displacement": {"node_type": "disp", "displacementTexture": "in"},
    }), encoding="utf-8")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", str(tmp_path))
    loader = ConfigLoader()
    cfg = loader.get_material_config("TestMat")
    assert cfg.get_prerequisites() == {"a": {"attribute": "attrA", "value": 1}}
    assert cfg.get_attr_prerequisites("baseColor") == {
        "attribute": "attrB", "value": [1, 0, 0]
    }
    assert cfg.get_maya_attr("baseColor") == "baseColor"
    assert cfg.displacement_node_type == "disp"
    assert cfg.displacement_file_source == "outAlpha"
    assert cfg.displacement_output == "displacement"


def test_material_config_defaults(tmp_path, monkeypatch):
    material_dir = _write_temp_config(tmp_path)
    (material_dir / "Bare.json").write_text(json.dumps({
        "material": {},
        "base": {"baseColor": ""},
    }), encoding="utf-8")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", str(tmp_path))
    loader = ConfigLoader()
    cfg = loader.get_material_config("")
    assert cfg.node_type == ""
    assert cfg.renderer == "unknown"
    assert cfg.uiPanel_display_name == ""
    assert cfg.get_maya_attr("baseColor") == ""