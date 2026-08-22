import shutil
from pathlib import Path

import pytest

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
