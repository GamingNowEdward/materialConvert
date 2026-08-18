# Changelog

## Unreleased

### Added
- New **Batch Builder** tab (`ui/tabs/batch_builder_tab.py`) with directory scanning, filename-driven channel parsing, merged parsed/unparsed table (sortable Status), and `Materials to Build` preview list
- `config/texture_channels.json`: filename keyword → channel rules driven by `common.json` builder keys, including common PBR suffixes (Poly Haven / ambientCG / Quixel / Substance / Unity / Unreal presets)
- `core/texture_scanner.py`: non-recursive directory scanning, longest-alias-first matching, token + underscore-tolerant substring matching
- `core/batch_builder.py`: converts scanner output into `MaterialBuilder` short keys and orchestrates batch builds
- `MaterialBuilder` extended channels: Metallic, Opacity, Emission, Transmission, Reflection, Sheen, SSS, and Glossiness (inverted via `file.invert`); new `use_full_chain` option for simple direct connections
- VRayMtl prerequisites now support color/list values (e.g. `reflectionColor: [1, 1, 1]`) via `core/prerequisites.py`
- `config/builder_naming.json`: shorter suffix abbreviations for new builder channels

### Changed
- Tab order in main window: Converter → Material Builder → Batch Builder → Node Tools
- Replaced the isolated "Unparsed Files" panel with an in-table `UNPARSED` status and a `Materials to Build` preview list
- Auto Match Selected (`ui/tabs/node_tools_tab.py`): when filename match and channel match both succeed but return different roles, the file node is treated as ambiguous — skipped (color space unchanged), kept selected, and the conflict is printed to Script Editor for manual review

## 2026-08-17

### Removed
- `ui/tabs/transform_tab.py`, `attr_modifier_tab.py`, `locator_tab.py` (and their tabs): Remove Transform Tools / Attr Modifier / Locator panels

### Refactoring
- **Unified Builder config into Convert pipeline**: delete `config/builder_specs.json`; Builder now reads renderer specs from `config/material/*.json` (`node_type`/`plugin`/attribute maps) + `bumpNormal.json` + `colorCorrection.json` + material JSON `displacement` blocks
- New `core/material_builder.py`: build logic moved from `ui/tabs/builder_tab.py` into core, fully config-driven
- `ui/tabs/builder_tab.py`: material type dropdown driven by all material JSONs (new materials appear automatically); full-width BUILD button; optional "Add To Quick Select Set" toggle
- `config/material/*.json`: add `plugin` field; displacement block extended with `file_source`/`lyr_src`/`output`; `VRayMtl` subsurface fixed (`ssColor` → `translucencyColor`, this version has no `ssColor` attribute)
- `config/bumpNormal.json`: add `file_source`/`default_scale` for Builder
- **Migrated pymel to `maya.cmds`** across `core/node_utils.py`, `core/prerequisites.py`, `core/converter.py`, `core/converters/*` (attribute/bump/cc/displacement), `ui/tabs/converter_tab.py` — pymel is no longer supported from Maya 2027; plugs are now plain `"node.attr"` strings

### Bug Fixes
- `core/converters/attribute.py`: float value → `float3` target attribute now broadcasts to `(v, v, v)` (e.g., Arnold `opacity`, V-Ray `opacityMap`, Redshift `ms_radius`)
- `core/node_utils.py`: unwrap `cmds.getAttr()` nested list format `[(1,1,1)] → (1,1,1)`, restoring color value transfer and black-color auto-zeroing (pymel migration regression)
- `config/material/VRayMtl.json`: fix `coatIor` → `coatIOR` (attribute name case error, coat IOR was never transferred)
- `core/converters/cc.py`: preserve source material CC chain during cross-renderer conversion — when the intermediate node (layeredTexture) is shared, the source attribute is reconnected to the original CC instead of being polluted with the target-renderer CC
- Hue mapping: `config/colorCorrection.json` adds `hue_center` per renderer; `core/node_utils.py` converts hue to a universal offset angle [-180, 180] (`0` = no change) — fixes Redshift `hue=0` mapping to Arnold `hueShift=-1` instead of `0`

### Enhancements
- Auto color space matching (`ui/tabs/node_tools_tab.py`, `core/config_loader.py`): channel matching now BFS-traces **all** downstream connections (single-channel `outColorR/G/B`, `outAlpha`, intermediate nodes like colorCorrect/layeredTexture/multiplyDivide/bump) instead of only `outColor`; attribute names are normalized (lowercase, `_`/`-` removed) before matching; Maya default render-list containers are skipped during tracing

### Documentation
- `README.md` / `README_zh.md` / `CONVERSION_SPEC.md` / `CONVERSION_SPEC_zh.md` / `AGENTS.md`: remove removed panels, update Builder config source, pymel → cmds, project structure

## 2026-08-13

### Enhancements
- `copy_launch.bat` (new): Double-click to copy Maya launch command to clipboard, eliminating manual path configuration
- `README.md` / `README_zh.md` / `AGENTS.md`: Add "Option 3: Use bat file" installation method

## 2026-07-14

### Enhancements
- `config/colorSpace.json`: Add `commonAttributeRoles` section defining generic attribute-to-color-space-role mapping
- `core/config_loader.py`: Add `get_expanded_attribute_keywords()` method for dynamic attribute mapping
- `ui/tabs/node_tools_tab.py`: `_match_by_channel()` uses expanded mapping covering all renderer-specific attributes
- Auto match color space now supports all material types without manual maintenance

## 2026-07-05

### Bug Fixes
- Fix Redshift CC node type name error in `node_utils.py` `is_cc_node()` (`rsColorCorrection` → `RedshiftColorCorrection`), causing Redshift color correction chain detection failure
- Fix missing V-Ray mapping in `cc.py` `renderer_map` (added `"vray": "vray"`), consistent with `bump.py` and `displacement.py`

### Code Cleanup
- Extract `renderer_short` mapping as shared constant `RENDERER_SHORT` in `node_utils.py`, eliminating duplicate definitions in `bump.py`, `cc.py`, and `displacement.py`
- Extract `_load_renderer_config` method in `config_loader.py`, eliminating duplicate logic in `_load_bump_normal` and `_load_color_correction`
- Extract `p2d_attrs` list as `BuilderTab.P2D_ATTRS` class constant in `builder_tab.py`, eliminating duplicate definition
- Reuse existing `self.config` instance in `node_tools_tab.py` instead of creating redundant `ConfigLoader()` instances

### Documentation
- `CONVERSION_SPEC.md` / `CONVERSION_SPEC_zh.md`: Add missing `RedshiftStandardMaterial` column to mapping table
- `CONVERSION_SPEC.md` / `CONVERSION_SPEC_zh.md`: Add missing `RedshiftStandardMaterial.json` and `colorSpace.json` to project structure
- `CONVERSION_SPEC.md` / `CONVERSION_SPEC_zh.md`: Fix project structure tree formatting

## 2026-07-02

### Documentation
- `README.md` / `README_zh.md`: Clarify Maya 2024+ support, add PyMEL dependency notes with official documentation links

## 2026-07-01

### Bug Fixes
- Fix `CONVERSION_SPEC.md` mapping table VRayMtl `specularWeight` typo (`reflectionColorAmoun` → `reflectionColorAmount`)
- Remove circular import `show` function at end of `ui/__init__.py`, eliminating circular import risk
- Remove redundant `sys.path` operation in `converter_tab.py` (already handled by `main.py`)
- Fix float3 value to float attribute type incompatibility (e.g., V-Ray opacityMap → Arnold geometryOpacity)
- Fix `attribute.py` missing `import pymel.core as pm` causing conversion to hang
- Fix `_fix_alpha_luminance` detection logic: scan target material actual connections, resolving alphaIsLuminance not enabled after `smart_connect` switches outColor to outAlpha

### Architecture Refactoring
- `core/node_utils.py`: Convert from static method class (`NodeUtils`) to module-level functions, using `import core.node_utils as node_utils`
- `core/converter.py`: Accept optional `logger` parameter, use `node_utils` module internally
- `core/builder_context.py`: Change PySide import to `from ui import QtWidgets`, remove independent try/except
- `core/__init__.py`: Remove silent try/except wrapper, use direct imports
- `ui/tabs/converter_tab.py`: Eliminate duplicate `ConfigLoader`/`NodeUtils` instances, reuse `node_utils` module

### Code Cleanup
- `core/logger.py` (new): Unified logging module with callback support, UI layer registers callbacks to update log panel
- `ui/tabs/node_tools_tab.py`: Bump node types and CC node types now read from config instead of hardcoded
- `core/config_loader.py`: Add `get_all_cc_types()` method
- `core/converters/bump.py`, `displacement.py`: Add `pm.warning()` logging to critical exception paths
- `core/node_utils.py`: Add logging to `set_cc_params`, `transfer_connection_to_plug`, `connect_plug_to_plug`, `delete_node_safe` exceptions
- `core/converters/cc.py`: Add logging to CC connection failures
- `core/converter.py`: Add logging to SG connection failures
- `core/converters/attribute.py`: Add logging to value setting failures and emission weight setting failures
- `core/prerequisites.py`: Add logging to prerequisite attribute setting failures

### UI/UX Improvements
- `ui/tabs/converter_tab.py`: Add `QProgressBar` to batch conversion, call `processEvents()` during conversion to keep UI responsive
- `ui/tabs/builder_tab.py`: Renderer buttons dynamically generated from `builder_specs.json`, adding new renderers only requires config changes
- `core/converter.py`: Wrap `convert_all()` with `cmds.undoInfo(openChunk/closeChunk)`, entire batch conversion can be undone in one step
- `ui/tabs/node_tools_tab.py`: Add "Auto Match Selected" feature, auto-match file node color space based on filename (priority) and connection channel (secondary)
- `config/colorSpace.json`: Refactor to colorSpaces.{role}.{aliases/filenameKeywords/attributeKeywords} structure, support multiple OCIO configurations

### Documentation
- `README.md`: Update feature descriptions and project structure
- `AGENTS.md`: Update architecture notes (NodeUtils changed to module, new logger module)
- `CONVERSION_SPEC.md`: Update project structure, fix mapping table typo
