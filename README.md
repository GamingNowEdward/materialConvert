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

**Zero external dependencies** — no pip install required.

## Features

### Material Converter
- Batch convert PBR materials between Arnold / Redshift / V-Ray
- Auto-detect material types, one-click convert all
- Supports bump/normal nodes, color correction nodes, and displacement nodes
- Progress bar for batch conversion, single-step undo (Ctrl+Z)
- Supports 6 material types: `aiStandardSurface` / `aiOpenPBRSurface` / `RedshiftMaterial` / `RedshiftOpenPBRMaterial` / `RedshiftStandardMaterial` / `VRayMtl`

### Material Builder
- One-click build complete PBR materials from texture paths
- Supports Color / Roughness / Normal / Bump / Displacement channels
- SSS channel support (colorCorrect + layeredTexture + ramp)
- Displacement node chain support
- Renderer buttons dynamically generated from config
- Create File From P2D: create file node from selected place2dTexture

### Node Tools
- **Select Nodes**: Batch select by type (material/file/bump/layeredTexture/CC), excluding default materials
- **Set File Color Space**: Batch set color space on selected file nodes
- **Auto Match Selected**: Automatically match color space based on filename keywords and connection channels (reference `config/colorSpace.json`)
- **Color Management**: Set ignoreColorSpaceFileRules on all file nodes
- **Rename Shading Engine**: Batch rename SG to match material names

### Transform Tools
- **Align To Floor**: Move objects so lowest point touches Y=0
- **Axis Alignment**: Align to X/Y/Z min/max bounds
- **Center Pivots**: Center pivot points on selected objects
- **World Space Location**: Move objects to specified world coordinates
- **Freeze Translations**: Reset translation values to zero
- **Freeze Rotations**: Reset rotation values to zero
- **Freeze Scale**: Reset scale values to one
- **Freeze All**: Reset all transforms at once
- **Apply All Pipeline**: Center pivots → Set location → Floor align → Y-min align → Freeze all

### Attr Modifier
- Batch modify attribute values on selected nodes
- Supports Boolean, Float, Integer, and String data types
- Automatically checks both transform and shape nodes

### Locator
- Auto-create Layout Locator for selected objects
- Scale Locator based on bounding box dimensions
- Per-axis (X/Y/Z) independent scale multipliers
- Optional display override color
- Prefix support for naming convention

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
│   ├── builder_specs.json           # Material Builder renderer specs
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
│   └── builder_context.py           # Material Builder shared state
├── ui/                              # User interface
│   ├── converter_ui.py              # Main window (QTabWidget)
│   ├── styles.py                    # QSS dark theme
│   └── tabs/                        # Six functional tabs
│       ├── converter_tab.py         # Material conversion
│       ├── builder_tab.py           # Material Builder
│       ├── node_tools_tab.py        # Node Tools
│       ├── transform_tab.py         # Transform Tools
│       ├── attr_modifier_tab.py     # Attr Modifier
│       └── locator_tab.py           # Locator tool
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
