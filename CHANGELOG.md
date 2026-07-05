# Changelog

## 2026-07-05

### Bug Fixes
- Fix Redshift CC node type name error in `node_utils.py` `is_cc_node()` (`rsColorCorrection` → `RedshiftColorCorrection`), causing Redshift color correction chain detection failure
- Fix missing V-Ray mapping in `cc.py` `renderer_map` (added `"vray": "vray"`), consistent with `bump.py` and `displacement.py`

### Code Cleanup
- Extract `renderer_short` mapping as shared constant `RENDERER_SHORT` in `node_utils.py`, eliminating duplicate definitions in `bump.py`, `cc.py`, and `displacement.py`
- Extract `_load_renderer_config` method in `config_loader.py`, eliminating duplicate logic in `_load_bump_normal` and `_load_color_correction`

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
