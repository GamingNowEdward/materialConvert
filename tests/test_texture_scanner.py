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


def test_scan_invalid_directory():
    scanner = TextureScanner()
    result = scanner.scan("Z:/does/not/exist")
    assert result == {"materials": [], "unparsed": [], "conflicts": []}


def test_find_alias_short_only_token_match():
    scanner = TextureScanner()
    assert scanner._find_alias("hero_metallic", "met") is None
    assert scanner._find_alias("hero_met", "met") == (5, 8)


def test_find_alias_long_skips_underscores_with_boundary():
    scanner = TextureScanner()
    assert scanner._find_alias("hero_met_allic_01", "metallic") is not None
    assert scanner._find_alias("hero_metallic", "metallic") == (5, 13)
    assert scanner._find_alias("hero_metallicx", "metallic") is None
    assert scanner._find_alias("heroxmetallic", "metallic") is None


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
