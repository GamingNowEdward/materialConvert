# PBR Material Converter

**English** | [简体中文](docs/README_zh.md)

**Conversion Specification:** [English](docs/CONVERSION_SPEC.md) | [简体中文](docs/CONVERSION_SPEC_zh.md)

**Renderer JSON Config Guide:** [English](docs/CONFIG_GUIDE.md) | [简体中文](docs/CONFIG_GUIDE_zh.md)

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

![Material Converter tab](docs/images/convert_tab.webp)

- Batch convert PBR materials between Arnold / Redshift / V-Ray
- Auto-detect material types, one-click convert all
- Supports bump/normal nodes, color correction nodes, and displacement nodes
- Progress bar for batch conversion, single-step undo (Ctrl+Z)
- Supports 6 material types: `aiStandardSurface` / `aiOpenPBRSurface` / `RedshiftMaterial` / `RedshiftOpenPBRMaterial` / `RedshiftStandardMaterial` / `VRayMtl`

### Material Builder

![Material Builder tab](docs/images/materialBuilder_tab.webp)

- One-click build complete PBR materials from texture paths
- Supports Color / Roughness / Glossiness (inverted) / Metallic / Normal / Bump / Displacement / Opacity / Transmission / Reflection / Sheen / SSS / Emission channels
- SSS channel support (colorCorrect + layeredTexture + ramp)
- Displacement node chain support
- Material type dropdown driven by `config/material/*.json` — new materials appear automatically
- Optional "Add To Quick Select Set" toggle

### Batch Builder

![Batch Builder tab](docs/images/batchBuilder_tab.webp)

- Scan a directory and auto-parse PBR texture sets by filename (`config/texture_channels.json`)
- Group textures into materials and preview which materials will be created (`Materials to Build`)
- Show parsed channels and unparsed files in one table with a sortable Status column
- Batch build all / selected materials to any supported renderer
- Toggle full Builder pipeline (colorCorrect + layeredTexture + ramp) or simple direct connection
- Supports BaseColor / Roughness / Glossiness (inverted) / Metallic / Normal / Bump / Displacement / Opacity / Transmission / Reflection / Sheen / SSS (Translucency + Scattering) / Emission


### Colorspace

![Colorspace tab](docs/images/colorSpace_tab.webp)

- Dedicated **Colorspace** tab — the single UI entry point for all file-node color-space operations (Node Tools no longer exposes any color-space UI)
- **File Node List**: scans all scene `file` nodes into a sortable table (File Node / File Path / Colorspace / Prematch Colorspace / Diagnostic); the Diagnostic column carries the match state (e.g. `CONFLICT: ...`) and sorts by severity, not alphabetically
- **Refresh**: evaluates automatic matching for every file node **without modifying the scene**
- **Automatic Matching** driven by two drivers: **Name Driver** (filename keywords from `config/texture_channels.json`) and **Channel Driver** (BFS-tracing all downstream connections against `commonAttributeRoles` + `config/material/*.json` expanded keywords); final states `MATCHED` / `CONFLICT` / `AMBIGUOUS` / `UNMATCHED` / `INVALID`
- **Apply Selected** / **Apply All Matched**: apply only `MATCHED` results to `file.colorSpace` (single undo chunk); `CONFLICT` / `AMBIGUOUS` / `UNMATCHED` / `INVALID` are never auto-applied
- **Manual Colorspace Assignment**: pick from the actual Maya input spaces and apply to selected rows only — never alters matcher rules or config
- Selecting a row syncs the Maya selection to the corresponding file node(s); utility button sets `ignoreColorSpaceFileRules` on all file nodes

### Node Tools

![Node Tools tab](docs/images/nodeTools_tab.webp)

- **Select Nodes**: Batch select by type (material/file/bump/layeredTexture/CC), excluding default materials
- **Rename Shading Engine**: Batch rename SG to match material names
- **Create File From P2D**: create a `file` node from the selected `place2dTexture`, copying the 2D transform attributes and UV/filter connections

### Log

![Log tab](docs/images/log_tab.webp)

- Global structured log viewer with level, source, and text filters
- Config Validation controls for checking all JSON config spelling against actual Maya node types (materials / `bumpNormal.json` / `colorCorrection.json`)
- Creates temporary nodes to check `node_type` and every mapped attribute (incl. prerequisites and displacement), then cleans up
- Renderers without an installed plugin are auto-loaded when possible, otherwise skipped entirely (never misreported as spelling errors)

## Architecture

### Data Flow
```
Source material → [Source JSON config] → Universal format → [Target JSON config] → Target material
```

### Key Design Principles
- **Config-driven**: All renderer mappings defined in JSON files, zero hardcoded attribute names in Python code
- **Config-driven CC types**: Color-correction node detection reads the node types defined in `config/colorCorrection.json`; adding a configured CC type requires no Python type-list update
- **Easy extension**: Adding new renderer support = add JSON file in `config/material/`, no code changes needed
- **Modular converters**: 4 independent modules handle attribute transfer, bump/normal, color correction, and displacement
- **Unified imports**: PySide version detection centralized in `ui/__init__.py`
- **Co-existence-safe startup**: the project root is put first on `sys.path`, and same-named top-level packages (`core` / `ui` / `main`) owned by another flat-layout tool are released — including their cached submodules — so the last launched tool wins without breaking the other's open window
- **Logging**: Unified structured logger (ERROR/WARN/SKIP/INFO/DEBUG/OK) with ring buffer; the visible Log tab mirrors the buffer via the single-consumer `drain()` API, removing rows evicted from the buffer. Log rows that carry nodes can right-click `Select Node(s)` to select them directly. Logger and UI model both retain at most `DEFAULT_MAX_RECORDS` (20,000) records

## Project Structure

```
materialConvert/
├── config/                          # JSON configuration files
│   ├── material/                    # Renderer material attribute mappings
│   │   ├── common.json              # Universal PBR parameters and color-weight relationships
│   │   ├── aiStandardSurface.json
│   │   ├── aiOpenPBRSurface.json
│   │   ├── RedshiftMaterial.json
│   │   ├── RedshiftOpenPBRMaterial.json
│   │   ├── RedshiftStandardMaterial.json
│   │   └── VRayMtl.json
│   ├── bumpNormal.json              # Bump/normal node mappings
│   ├── colorCorrection.json         # Color correction node mappings
│   ├── colorSpace.json              # Color space auto-match rules
│   ├── texture_channels.json        # Batch Builder filename-to-channel rules
│   └── builder_naming.json          # Material Builder naming conventions
├── core/                            # Core engine
│   ├── converter.py                 # MaterialConverter dispatcher
│   ├── results.py                   # ConversionResult / BuildResult result models
│   ├── converters/                  # Business conversion modules
│   │   ├── attribute.py             # Attribute collection & transfer
│   │   ├── bump.py                  # Bump/normal conversion
│   │   ├── cc.py                    # Color correction conversion
│   │   └── displacement.py          # Displacement conversion
│   ├── config_loader.py             # JSON config parser
│   ├── module_reload.py             # Path-based purge of this project's modules on reload
│   ├── node_utils.py                # Maya node utility functions
│   ├── prerequisites.py             # Renderer prerequisite handling
│   ├── logger.py                    # Unified logging module
│   ├── builder_context.py           # Material Builder shared state
│   ├── texture_scanner.py           # Directory scanning / filename-to-channel parsing
│   ├── batch_builder.py             # Batch build orchestration
│   ├── material_builder.py          # Material Builder core logic
│   ├── colorspace.py                # Color-space match core (name/channel drivers + resolver + matcher)
│   └── config_validator.py          # JSON config validation (Log tab)
├── ui/                              # User interface
│   ├── main_window.py               # Main window (QMainWindow + QTabWidget)
│   ├── feedback.py                  # Best-effort operation feedback decorator
│   ├── log_panel.py                 # Embedded global log viewer (polling, filters, QTableView)
│   ├── styles.py                    # QSS dark theme
│   ├── widgets.py                   # Shared target-combo population helper
│   └── tabs/                        # Six functional tabs
│       ├── converter_tab.py         # Material conversion
│       ├── builder_tab.py           # Material Builder
│       ├── batch_builder_tab.py     # Batch Builder
│       ├── colorspace_tab.py        # Colorspace (file-node color-space management)
│       ├── node_tools_tab.py        # Node Tools
│       └── log_tab.py               # Log (global log viewer + config validation)
├── docs/                            # Documentation
│   ├── AGENTS.md                    # AI Agent development guide
│   ├── CONVERSION_SPEC.md           # Full conversion specification
│   ├── CONVERSION_SPEC_zh.md        # 中文版转换规格说明
│   ├── CONFIG_GUIDE.md              # Renderer JSON config authoring guide
│   ├── CONFIG_GUIDE_zh.md           # 渲染器 JSON 配置编写指南（中文版）
│   ├── images/                      # README preview screenshots (one per tab)
│   └── README_zh.md                 # 中文版 README
├── scripts/                         # Repository maintenance scripts
│   └── check_no_silent_pass.py      # CI guard: no silent except/print in core/ui
├── tests/                           # Pure-Python unit tests (no Maya required)
├── .github/
│   └── workflows/test.yml           # CI: pytest + guard script (Python 3.11 + PySide6)
├── main.py                          # Entry script
├── copy_launch.bat                  # Double-click to copy launch command
├── LICENSE
├── CHANGELOG.md                     # Changelog
└── CHANGELOG_zh.md                  # 中文版更新日志
```

## Documentation

- [CONVERSION_SPEC.md](docs/CONVERSION_SPEC.md) — Full conversion specification
- [CONVERSION_SPEC_zh.md](docs/CONVERSION_SPEC_zh.md) — 中文版转换规格说明
- [CONFIG_GUIDE.md](docs/CONFIG_GUIDE.md) — Renderer JSON config authoring guide
- [CONFIG_GUIDE_zh.md](docs/CONFIG_GUIDE_zh.md) — 渲染器 JSON 配置编写指南（中文版）

## Development

- Pure-Python tests (no Maya required): `python -m pytest tests/ -v`
- CI (`.github/workflows/test.yml`) runs the same pytest suite plus `scripts/check_no_silent_pass.py` on Python 3.11 + PySide6

## License

MIT
