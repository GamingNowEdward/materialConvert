# PBR Material Converter

**English** | [简体中文](docs/README_zh.md)

Maya toolkit for PBR material conversion, building, and scene management across Arnold / Redshift / V-Ray.

## Installation

Place the `materialConvert` folder anywhere, then create a Shelf button in Maya with the following 3 lines (replace the path with your actual path):

**Option 1: Copy to Maya scripts directory (recommended)**

```python
import sys
sys.path.insert(0, r"C:\Users\<username>\Documents\maya\<version>\scripts\materialConvert")
exec(open(r"C:\Users\<username>\Documents\maya\<version>\scripts\materialConvert\main.py").read())
```

**Option 2: Place in any directory**

```python
import sys
sys.path.insert(0, r"your_path\materialConvert")
exec(open(r"your_path\materialConvert\main.py").read())
```

**Option 3: Use bat file (easiest)**

Double-click `copy_launch.bat` to copy the launch command to clipboard, then paste directly into Maya Script Editor.

**Supported**: Maya 2024+
**Requires**: none (zero external dependencies, pure `maya.cmds` API)

## Features

### Material Converter
- Batch convert PBR materials between Arnold / Redshift / V-Ray
- Auto-detect material types, one-click convert all
- Supports bump/normal nodes, color correction nodes, and displacement nodes
- Progress bar for batch conversion, single-step undo (Ctrl+Z)
- Supports 6 material types: `aiStandardSurface` / `aiOpenPBRSurface` / `RedshiftMaterial` / `RedshiftOpenPBRMaterial` / `RedshiftStandardMaterial` / `VRayMtl`

### Material Builder
- One-click build complete PBR materials from texture paths
- Supports Color / Roughness / Glossiness (inverted) / Metallic / Normal / Bump / Displacement / Opacity / Transmission / Reflection / Sheen / SSS / Emission channels
- SSS channel support (colorCorrect + layeredTexture + ramp)
- Displacement node chain support
- Material type dropdown driven by `config/material/*.json` — new materials appear automatically
- Optional "Add To Quick Select Set" toggle
- Create File From P2D: create file node from selected place2dTexture

### Batch Builder
- Scan a directory and auto-parse PBR texture sets by filename (`config/texture_channels.json`)
- Group textures into materials and preview which materials will be created (`Materials to Build`)
- Show parsed channels and unparsed files in one table with a sortable Status column
- Batch build all / selected materials to any supported renderer
- Toggle full Builder pipeline (colorCorrect + layeredTexture + ramp) or simple direct connection
- Supports BaseColor / Roughness / Glossiness (inverted) / Metallic / Normal / Bump / Displacement / Opacity / Transmission / Reflection / Sheen / SSS (Translucency + Scattering) / Emission


### Node Tools
- **Select Nodes**: Batch select by type (material/file/bump/layeredTexture/CC), excluding default materials
- **Set File Color Space**: Batch set color space on selected file nodes
- **Auto Match Selected**: Automatically match color space by tracing all downstream connections (single-channel/outAlpha/intermediate nodes) with normalized attribute keywords (reference `config/colorSpace.json`); ambiguous nodes (filename role ≠ channel role) are skipped and kept selected for manual review
- **Color Management**: Set ignoreColorSpaceFileRules on all file nodes
- **Rename Shading Engine**: Batch rename SG to match material names

## Architecture

### Data Flow
```
Source material → [Source JSON config] → Universal format → [Target JSON config] → Target material
```

### Key Design Principles
- **Config-driven**: All renderer mappings defined in JSON files, zero hardcoded attribute names in Python code
- **Easy extension**: Adding new renderer support = add JSON file in `config/material/`, no code changes needed
- **Modular converters**: 4 independent modules handle attribute transfer, bump/normal, color correction, and displacement
- **Unified imports**: PySide version detection centralized in `ui/__init__.py`
- **Logging**: Unified Logger class with callback support for UI integration

## Project Structure

```
materialConvert/
├── config/                          # JSON configuration files
│   ├── material/                    # Renderer material attribute mappings
│   │   ├── common.json              # Universal PBR parameters
│   │   ├── aiStandardSurface.json
│   │   ├── aiOpenPBRSurface.json
│   │   ├── RedshiftMaterial.json
│   │   ├── RedshiftOpenPBRMaterial.json
│   │   ├── RedshiftStandardMaterial.json
│   │   └── VRayMtl.json
│   ├── bumpNormal.json              # Bump/normal node mappings
│   ├── colorCorrection.json         # Color correction node mappings
│   ├── colorSpace.json              # Color space auto-match rules
│   ├── texture_channels.json       # Batch Builder filename-to-channel rules
│   └── builder_naming.json          # Material Builder naming conventions
├── core/                            # Core engine
│   ├── converter.py                 # MaterialConverter dispatcher
│   ├── converters/                  # Business conversion modules
│   │   ├── attribute.py             # Attribute collection & transfer
│   │   ├── bump.py                  # Bump/normal conversion
│   │   ├── cc.py                    # Color correction conversion
│   │   └── displacement.py          # Displacement conversion
│   ├── config_loader.py             # JSON config parser
│   ├── node_utils.py                # Maya node utility functions
│   ├── prerequisites.py             # Renderer prerequisite handling
│   ├── logger.py                    # Unified logging module
│   ├── builder_context.py           # Material Builder shared state
│   ├── texture_scanner.py           # Directory scanning / filename-to-channel parsing
│   ├── batch_builder.py             # Batch build orchestration
│   └── material_builder.py          # Material Builder core logic
├── ui/                              # User interface
│   ├── converter_ui.py              # Main window (QTabWidget)
│   ├── styles.py                    # QSS dark theme
│   └── tabs/                        # Four functional tabs
│       ├── converter_tab.py         # Material conversion
│       ├── builder_tab.py           # Material Builder
│       ├── batch_builder_tab.py    # Batch Builder
│       └── node_tools_tab.py        # Node Tools
├── docs/                            # Documentation
│   ├── CONVERSION_SPEC.md           # Full conversion specification
│   ├── CONVERSION_SPEC_zh.md        # 中文版转换规格说明
│   └── README_zh.md                 # 中文版 README
├── main.py                          # Entry script
└── CHANGELOG.md                     # Changelog
```

## Documentation

- [CONVERSION_SPEC.md](docs/CONVERSION_SPEC.md) — Full conversion specification
- [CONVERSION_SPEC_zh.md](docs/CONVERSION_SPEC_zh.md) — 中文版转换规格说明

## License

MIT
