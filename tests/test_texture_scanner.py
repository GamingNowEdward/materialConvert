import json
import shutil
from pathlib import Path

import pytest

from core.logger import LogLevel, Logger
from core.texture_scanner import TextureScanner


@pytest.fixture
def scan_dir():
    path = Path(__file__).resolve().parent / "_tmp_scanner"
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def test_scan_groups_and_detects_conflicts(scan_dir):
    (scan_dir / "hero_baseColor.png").write_text("", encoding="utf-8")
    (scan_dir / "hero_roughness.png").write_text("", encoding="utf-8")
    (scan_dir / "hero_albedo.png").write_text("", encoding="utf-8")
    (scan_dir / "unknown_file.png").write_text("", encoding="utf-8")

    scanner = TextureScanner()
    result = scanner.scan(str(scan_dir))

    assert len(result["materials"]) == 1
    assert result["materials"][0]["name"].lower() == "hero"
    assert "baseColor" in result["materials"][0]["channels"]
    assert len(result["unparsed"]) == 1
    assert len(result["conflicts"]) == 1
    assert result["conflict_materials"] == [result["materials"][0]["name"]]


def test_conflict_records_every_candidate(scan_dir):
    """Regression guard: a conflict must keep every candidate and the kept path."""
    (scan_dir / "rock_Roughness.png").write_text("", encoding="utf-8")
    (scan_dir / "rock_Glossiness.png").write_text("", encoding="utf-8")
    (scan_dir / "rock_Gloss.png").write_text("", encoding="utf-8")

    result = TextureScanner().scan(str(scan_dir))

    assert len(result["conflicts"]) == 1
    conflict = result["conflicts"][0]
    assert conflict["common_attr"] == "specularRoughness"
    assert conflict["kept"] == conflict["existing"]
    assert conflict["kept"] in conflict["candidates"]
    assert len(conflict["candidates"]) == 3
    assert len(conflict["dropped"]) == 2
    assert all(path not in conflict["dropped"] for path in [conflict["kept"]])
    # the kept file wins deterministically (sorted directory listing)
    kept = result["materials"][0]["channels"]["specularRoughness"]["path"]
    assert kept == conflict["kept"]


def test_scan_invalid_directory():
    scanner = TextureScanner()
    result = scanner.scan("Z:/does/not/exist")
    assert result == {
        "materials": [], "unparsed": [], "conflicts": [], "conflict_materials": [],
    }


def test_parse_metallic_vs_short_words():
    scanner = TextureScanner()
    parsed = scanner._parse("hero_metallic")
    assert parsed is not None
    assert parsed[1] == "metallic"
    parsed = scanner._parse("hero_metmap")
    assert parsed[1] == "metallic"
    assert scanner._parse("hero_metal") is None
    assert scanner._parse("hero_met") is None


def test_parse_translucency_beats_trans():
    scanner = TextureScanner()
    parsed = scanner._parse("hero_translucency")
    assert parsed is not None
    assert parsed[1] == "subsurfaceColor"
    parsed = scanner._parse("hero_trans")
    assert parsed[1] == "transmissionColor"


def test_clean_base_name():
    scanner = TextureScanner()
    assert scanner._clean_base_name("hero_") == "hero"
    assert scanner._clean_base_name("_hero_") == "hero"
    assert scanner._clean_base_name("hero_base_color") == "hero_base_color"
    assert scanner._clean_base_name("hero__base") == "hero_base"


def test_parse_invert_and_mode_options(tmp_path):
    config = {
        "extensions": [".png"],
        "channels": {
            "Gloss": {"aliases": ["gloss"], "common_attr": "specularRoughness",
                      "type": "float", "invert": True},
            "Normal": {"aliases": ["nrm"], "common_attr": "normal_bump",
                       "type": "normal"},
            "Bump": {"aliases": ["bump"], "common_attr": "normal_bump",
                     "type": "bump"},
            "NoAttr": {"aliases": ["noattr"], "type": "float"},
        },
    }
    path = tmp_path / "channels.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    scanner = TextureScanner(config_path=str(path))
    parsed = scanner._parse("hero_gloss")
    assert (parsed[0], parsed[1], parsed[2], parsed[3]) == (
        "Gloss", "specularRoughness", "hero", {"invert": True}
    )
    assert scanner._parse("hero_nrm")[3] == {"mode": "normal"}
    assert scanner._parse("hero_bump")[3] == {"mode": "bump"}
    assert scanner._parse("hero_noattr") is None


def test_parse_no_common_attr_warns(tmp_path):
    config = {
        "extensions": [".png"],
        "channels": {"NoAttr": {"aliases": ["noattr"], "type": "float"}},
    }
    path = tmp_path / "channels.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    log = Logger()
    scanner = TextureScanner(config_path=str(path), logger=log)
    assert scanner._parse("hero_noattr") is None
    warns = [r for r in log.poll(0) if r.level == LogLevel.WARN]
    assert len(warns) == 1
    assert "has no common_attr" in warns[0].message


def test_scan_metallic_not_matched_by_short_words(scan_dir):
    (scan_dir / "hero_metallic.png").write_text("", encoding="utf-8")
    (scan_dir / "hero_metal.png").write_text("", encoding="utf-8")
    scanner = TextureScanner()
    result = scanner.scan(str(scan_dir))
    materials = result["materials"]
    assert len(materials) == 1
    assert "metallic" in materials[0]["channels"]
    assert len(result["unparsed"]) == 1


# --------------------------------------------------------------------------- #
# Set-wide common tokens (a suffix every file shares) and numeric suffixes
# --------------------------------------------------------------------------- #

_SET_NAMES = [
    "FabricCottonMuslin004_SSS_2K_METALNESS",
    "FabricCottonMuslin004_NRM16_2K_METALNESS",
    "FabricCottonMuslin004_NRM_2K_METALNESS",
    "FabricCottonMuslin004_MASK_2K_METALNESS",
    "FabricCottonMuslin004_DISP16_2K_METALNESS",
    "FabricCottonMuslin004_COL_2K_METALNESS",
    "FabricCottonMuslin004_AO_2K_METALNESS",
    "FabricCottonMuslin004_2K_METALNESS",
    "FabricCottonMuslin004_ROUGHNESS_2K_METALNESS",
    "FabricCottonMuslin004_TRANSLUCENCY_2K_METALNESS",
    "FabricCottonMuslin004_Preview1",
]


def _write_set(scan_dir, names):
    for name in names:
        (scan_dir / (name + ".png")).write_text("", encoding="utf-8")


def test_parse_numeric_suffix_channels():
    scanner = TextureScanner()
    assert scanner._parse("hero_nrm16")[1] == "normal_bump"
    assert scanner._parse("hero_disp16")[1] == "displacementTexture"


def test_common_suffix_is_not_the_channel(scan_dir):
    """A token every file shares is a set suffix, not this file's channel."""
    _write_set(scan_dir, _SET_NAMES)

    log = Logger()
    result = TextureScanner(logger=log).scan(str(scan_dir))

    assert len(result["materials"]) == 1
    material = result["materials"][0]
    assert material["name"].lower().startswith("fabriccottonmuslin004")
    channels = {name: data["channel"] for name, data in material["channels"].items()}
    assert channels["baseColor"] == "BaseColor"
    assert channels["specularRoughness"] == "Roughness"
    assert channels["normal_bump"] == "Normal"
    assert channels["displacementTexture"] == "Displacement"
    assert channels["subsurfaceColor"] in ("TranslucencyColor", "ScatteringColor")

    # SSS vs TRANSLUCENCY and NRM vs NRM16 both map to one common attribute
    conflicted = {item["common_attr"] for item in result["conflicts"]}
    assert conflicted == {"subsurfaceColor", "normal_bump"}

    # files without a channel token of their own stay unparsed
    unparsed = {Path(path).stem for path in result["unparsed"]}
    assert unparsed == {
        "FabricCottonMuslin004_AO_2K_METALNESS",
        "FabricCottonMuslin004_2K_METALNESS",
        "FabricCottonMuslin004_Preview1",
    }

    infos = [r.message for r in log.poll(0) if r.level == LogLevel.INFO]
    assert any("Ignoring common alias token" in message and "metalness" in message
               for message in infos)


def test_single_channel_directory_still_parses(scan_dir):
    """When ignoring the common token resolves nothing, fall back to plain parsing."""
    _write_set(scan_dir, ["rockA_METALNESS", "rockB_METALNESS", "rockC_METALNESS"])

    result = TextureScanner().scan(str(scan_dir))

    assert len(result["materials"]) == 3
    assert all("metallic" in material["channels"] for material in result["materials"])
    assert result["unparsed"] == []


def test_small_directory_keeps_plain_behaviour(scan_dir):
    """Two files are too few for "shared by most files" to mean anything."""
    _write_set(scan_dir, ["fabric_COL_2K_METALNESS", "fabric_ROUGHNESS_2K_METALNESS"])

    result = TextureScanner().scan(str(scan_dir))

    # plain behaviour: the common-token filter is not applied, so the files stay
    # separate materials and the METALNESS suffix still wins where it is longer
    assert len(result["materials"]) == 2
    channels = {name for material in result["materials"] for name in material["channels"]}
    assert channels == {"metallic", "specularRoughness"}


def test_asset_name_containing_an_alias_is_kept(scan_dir):
    """The asset name is never treated as a common token."""
    _write_set(scan_dir, [
        "MetalnessPanel_BaseColor", "MetalnessPanel_Roughness", "MetalnessPanel_Normal",
    ])

    result = TextureScanner().scan(str(scan_dir))

    assert len(result["materials"]) == 1
    material = result["materials"][0]
    assert material["name"].lower() == "metalnesspanel"
    assert set(material["channels"]) == {"baseColor", "specularRoughness", "normal_bump"}


def test_plain_set_is_unaffected(scan_dir):
    _write_set(scan_dir, ["wood_basecolor", "wood_roughness", "wood_normal"])

    result = TextureScanner().scan(str(scan_dir))

    assert len(result["materials"]) == 1
    assert result["materials"][0]["name"].lower() == "wood"
    assert set(result["materials"][0]["channels"]) == {
        "baseColor", "specularRoughness", "normal_bump"}
    assert result["conflicts"] == []


# --------------------------------------------------------------------------- #
# Duplicate channels: the higher bit depth / resolution wins
# --------------------------------------------------------------------------- #

def test_higher_bit_depth_wins_a_duplicate_channel(scan_dir):
    _write_set(scan_dir, ["rock_NRM16_2K", "rock_NRM_2K", "rock_basecolor"])

    result = TextureScanner().scan(str(scan_dir))

    material = result["materials"][0]
    kept = material["channels"]["normal_bump"]["path"]
    assert Path(kept).stem == "rock_NRM16_2K"

    conflict = result["conflicts"][0]
    assert conflict["common_attr"] == "normal_bump"
    assert Path(conflict["kept"]).stem == "rock_NRM16_2K"
    assert [Path(path).stem for path in conflict["dropped"]] == ["rock_NRM_2K"]


def test_higher_resolution_wins_a_duplicate_channel(scan_dir):
    # the resolution is glued to the channel token, so both files name one material
    _write_set(scan_dir, ["rock_rough4k", "rock_rough", "rock_basecolor"])

    result = TextureScanner().scan(str(scan_dir))

    kept = result["materials"][0]["channels"]["specularRoughness"]["path"]
    assert Path(kept).stem == "rock_rough4k"
    assert [Path(path).stem for path in result["conflicts"][0]["dropped"]] == ["rock_rough"]


def test_equal_quality_keeps_the_first_name(scan_dir):
    _write_set(scan_dir, ["rock_Roughness", "rock_Glossiness", "rock_basecolor"])

    result = TextureScanner().scan(str(scan_dir))

    conflict = result["conflicts"][0]
    assert Path(conflict["kept"]).stem == "rock_Glossiness"
    assert [Path(path).stem for path in conflict["dropped"]] == ["rock_Roughness"]
    assert result["materials"][0]["channels"]["specularRoughness"]["path"] == conflict["kept"]
