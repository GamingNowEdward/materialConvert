# Changelog

## 2026-09-10

### Refactored
- **Batch Builder batch orchestration moved into core**: added `BatchBuilder.build_all(materials, ..., on_progress=...)` (`core/batch_builder.py`) — undo chunk, per-material failure isolation (`_build_one_safe`, errors logged without aborting the batch), progress-callback protection and batch summary logging now live in core; `BatchBuilderTab._build_materials` keeps only selection filtering, the progress bar and result presentation, and no longer calls `cmds.undoInfo` directly
- Added the pure-stdlib result model `BuildResult` + `summarize_build_results()` (`core/results.py`), alongside `ConversionResult`, shared by core and UI
- **Colorspace matcher API no longer depends on UI row dicts**: `ColorSpaceMatcher.apply_matched()` now accepts `MatchResult` entries (the `scan()` return value); `ColorspaceTab` caches scan results and drives selection / apply / status counts directly from `MatchResult`, storing the result object in the table's UserRole
- **Shared ConfigLoader instance**: `ConverterWindow` creates the single `ConfigLoader` and injects it into `BuilderContext` / `ConverterTab` / `ColorspaceTab`; `MaterialBuilder` / `MaterialConverter` / `ColorSpaceMatcher` accept injected config (defaults unchanged), avoiding repeated JSON loads per tab
- Target material combo population deduplicated into `ui/widgets.py:populate_material_targets()` (shared by Converter / Builder / Batch Builder)
- `MaterialBuilder.build()` dropped the redundant `use_nrm` / `use_disp` parameters: normal/bump mode is derived from `channel_options` (default normal) and displacement from `input_paths` containing `displacementTexture`; the UI no longer recomputes them
- Removed duplicate scan summary / conflict warning logs from `BatchBuilderTab._scan_directory` (`TextureScanner` already logs them)
- Moved `Create File From P2D` from Material Builder to Node Tools (new `Texture Tools` group); feedback now follows the Node Tools logging style (no dialog/banner), behavior otherwise unchanged
- `NodeToolsTab` now accepts an optional injected `ConfigLoader` (`ConverterWindow` passes the shared instance), completing the single-loader policy; a self-created `ConfigLoader()` remains the fallback when none is injected

### Added
- Tests: `build_all` cases in `test_batch_builder.py` (result order, undo wrapping, failure isolation, callback exception never aborts, empty batch), `summarize_build_results` cases in `test_conversion_results.py`, core `apply_matched` cases in `test_colorspace.py` (only MATCHED applied / failures reported), injected-loader case in `test_builder_context.py`, injected-config case for `NodeToolsTab` in `test_colorspace_tab.py`

### Documentation
- `README.md` / `docs/README_zh.md`: project-structure tree synced with the codebase — added `core/results.py`, `core/module_reload.py`, `ui/feedback.py`, `ui/widgets.py`, `ui/log_panel.py` (zh version), `tests/`, `scripts/check_no_silent_pass.py`, `.github/workflows/test.yml`
- `docs/AGENTS.md`: corrected the ConfigLoader injection targets (now incl. `NodeToolsTab`), the tab name (`Builder` → `Material Builder`) and the progress-throttle description (every 5 materials incl. the last; removed stale "or 150ms")

## 2026-09-07

### Refactored
- **Colorspace 功能从 Node Tools 迁移为独立标签页**：`Node Tools` 删除全部 colorspace UI 与操作（Set File Color Space / Auto Match Selected / Color Management），只保留 Select Nodes 与 Rename Shading Engine；colorspace 功能唯一入口迁移到新 **Colorspace** 标签页（`ui/tabs/colorspace_tab.py`），`ignoreColorSpaceFileRules` 工具同步迁入
- **主窗口标签页顺序调整**：Converter → Material Builder → Batch Builder → **Colorspace** → Node Tools → Log（Colorspace 为第 4 个标签页）
- **Further centralized Colorspace responsibilities**: `ColorspaceTab` now only handles presentation, table selection, and interaction; scene scanning, automatic/manual color-space assignment, `ignoreColorSpaceFileRules`, and undo handling are centralized in `ColorSpaceMatcher`, with unified applied / failed / skipped results

### Added
- 单一 matcher 核心 `core/colorspace.py`：`NameDriver`（文件名关键词，来自 `config/texture_channels.json`）+ `ChannelDriver`（BFS 下游通道追踪，保留 depth/budget 遍历保护与材质缓存）+ `ColorSpaceResolver`（role→alias→实际 Maya colorspace，available spaces 按 Refresh 缓存）+ `ColorSpaceMatcher`（`MATCHED`/`CONFLICT`/`AMBIGUOUS`/`UNMATCHED`/`INVALID` 五态 + prematch 预测 + diagnostic）；配置仍以 `colorSpace.json` / `texture_channels.json` 为单一来源，不引入第二套规则
- Colorspace 标签页：场景 file 节点列表（File Node / File Path / Colorspace / Prematch / Diagnostic，状态词并入 Diagnostic 列并按严重度排序，去掉独立 State 列）、Refresh（只评估不改 scene）、Apply Selected / Apply All Matched（仅应用 `MATCHED`，undo chunk 包裹）、Manual Colorspace Assignment（Maya 实际 input spaces）、行选择同步 Maya 节点选择
- 行为收紧（文档要求）：Name/Channel driver 内部多角色命中显式标记 `AMBIGUOUS`（不再静默取第一个）；无匹配不再回退默认 `raw`（`UNMATCHED` 不自动应用）；role 无法解析到实际 Maya colorspace 时为 `INVALID`，无静默 fallback
- 测试：`tests/test_colorspace.py`（drivers / matcher / resolver，含从 `test_node_tools_trace.py` 迁入的 BFS 预算与跳过用例）、`tests/test_colorspace_tab.py`（UI 集成：Refresh 不改 scene、Apply 仅 MATCHED、Manual 生效、Node Tools 旧 colorspace 已移除）

## 2026-09-06

### Fixed
- **SG 连接失败不再静默计为成功**：`MaterialConverter.convert()` 改为返回结构化 `ConversionResult`（`created` / `converted` / `wired` / `total_sgs` / `skipped` / `reason`）；创建成功但**所有** shadingEngine 接线均失败的材质计入 failed（unwired）——场景仍在渲染旧材质时绝不显示为成功
- **置换按"逐 shadingEngine"转换**：同一材质挂多个 SG 时不再只处理第一个（此前 `node_utils.get_shading_engine()` 只取首个 SG，导致部分模型置换缺失/错配）；源置换相同（纹理插头 + scale）的 SG 复用同一目标置换节点
- `core/module_reload.py` 通过 CI 守卫：`is_project_module` 判定改为无异常路径（isinstance 校验取代裸 `except Exception:`），不再触发 `scripts/check_no_silent_pass.py`

### Changed
- `convert_all(..., on_progress=...)` 新增可选逐材质进度回调（core 不依赖 Qt）；Converter 页注入节流回调，在批次运行期间实时推进进度条并 `processEvents()`，不再等全部完成后一次性拨动
- 结果模型提取为纯模块 `core/results.py`（`ConversionResult` + `summarize_results`），core 与 UI 共用、可在无 Maya 环境单测
- `main.py` 启动模块清理改为按文件物理路径判断（`core/module_reload.py`），不再按 `core`/`ui` 名称前缀删除，避免误伤同一 Maya 会话中同名的其他工具包；`node_utils.get_shading_engine()`（取首个 SG 的反模式）移除

### Added
- 测试：`tests/test_conversion_results.py`（结果分类语义：unwired / partial_wired / 无 SG 浮动材质等）、`tests/test_module_reload.py`（路径清理只删本项目模块）

## 2026-08-30

### Fixed
- Builder 操作失败时的错误处理链二次异常：`qt_maya_logger` 把非 QWidget 的 `BuilderTab` 实例传给 `QMessageBox.critical(parent, ...)`，必然抛 `TypeError`，且在 `raise` 之前逃逸——原始异常 traceback 被掩盖，日志与弹窗反馈全部失效
- 错误反馈重构为 best-effort：logger / 弹窗 / 横幅任一环节失败都不再改变业务控制流——logger 失败回退到 stderr（`_report_terminal`，不依赖 logger/UI/Maya），弹窗失败记录 WARN；所有路径仍重新抛出原始异常。START / SUCCESS 日志与 inViewMessage 横幅同样防护

### Refactored
- `qt_maya_logger` 从 `core/builder_context.py` 迁移到 `ui/feedback.py`（操作反馈属 UI 层职责）：`core.builder_context` 恢复零 UI 依赖，可在无 UI/PySide 环境下独立 import（新增守护测试）
- `QMessageBox.critical` parent 改为 `None`，消除对调用方实例类型的隐式依赖
- 新增测试：`tests/test_builder_context.py`（8 个）、`tests/test_feedback.py`（9 个，错误链全路径：业务异常 / 弹窗失败 / logger 失败 / START 与成功路径反馈失败）

## 2026-08-25

### Added
- 61 new unit tests (110 total, no Maya required): `config_loader` spec rules and common-section merging, `texture_scanner` alias matching (short-token only, underscore-skipping with boundary checks, long-alias priority), `node_utils` hue offset conversion across renderers and `smart_connect` fallback chain, `config_validator` plugin-failure SKIP behavior and cleanup, `attribute` converter float broadcast / color first-channel fallback / black-color zeroing, `batch_builder` channel mapping, and `MaterialBuilder` silence regression tests
- Single-consumer `Logger.drain(after_seq)` API: returns new records plus the seqs evicted since the previous drain (`evicted_seqs`); when the caller is more than one full buffer behind it returns `reset=True` with a full snapshot for wholesale resync
- `LogModel.replace_records()` / `remove_by_seqs()`: the UI log model now mirrors the logger ring buffer exactly instead of keeping stale rows already evicted by critical-record replacement
- Structured log nodes: `LogRecord.nodes` carries selectable Maya node names attached at log time; Log rows with nodes can right-click `Select Node(s)` in the Log tab

### Changed
- `MaterialBuilder` no longer logs `DEBUG` "not in input paths, skipped" for channels absent from the input texture set — a normal per-build branch, not an event worth surfacing; `SKIP` logs for missing config mappings (e.g. no target attribute mapping) are kept
- LogViewer switched from `Logger.poll()` to `Logger.drain()`: rows evicted from the ring buffer are removed from the table via proper Qt model signals; wholesale replace on reset
- Level filter checkboxes unified into a single `_LEVEL_UI` config table (label/color/default checked); OK and Debug remain unchecked by default
- "Copy" now includes a timestamp, source context key/values and level per line
- `node_utils.identify_node_type()` / `create_cc_node()` / `create_target_material()` accept an optional injected `logger`; converter/bump/cc callers pass their instance logger instead of falling back to the global one
- `MaterialBuilder` p2d → file connections use `BuilderContext.connect(..., quiet=True)` and one aggregate DEBUG per file node instead of one DEBUG per connection

### Fixed
- `node_utils.node_name_from_plug()` crashed with `AttributeError` when handed `None` (reached via the `smart_connect` empty-plug warning path); it now tolerates falsy input
- `dropped_critical` was not incremented when a non-critical write evicted a critical record from the middle of the ring buffer (and was miscounted in the reverse case)

### Refactored
- `bumpNormal.json` / `colorCorrection.json`: connection fields unified to `input`/`output` (replacing `source_connection`/`target_connection`); vray `input_type`/`input_type_value` unified to `is_normal`/`is_normal_value` and `node_type: ""` removed; dead `input`/`output` keys without consumers removed from the `common` section of `bumpNormal.json`
- Removed unconsumed field: `material.target_connection` in `config/material/*.json`
- `config/builder_naming.json`: fixed disp prefix casing (`disP_` → `disp_`)
- Synced: `config_loader.py` (NodeMapping/ColorCorrectionConfig fields), `bump.py` (removed input_type dual branch), `material_builder.py`, `config_validator.py`, `node_utils.py`, `cc.py`, `test_config_loader.py`
- Docs: `AGENTS.md` gained the unified `bumpNormal.json` schema and the renderer tex-node extension-point notes

### Fixed
- Builder banner log no longer shows a misleading `Unknown`: `qt_maya_logger` now takes a required `label` argument; call sites annotate the action name (Builder / P2D File)
- Quick select sets are now named after the uniquified material node (`QS_` + node name): no longer relies on Maya auto-renaming, the log matches the scene, and set names are deterministic across repeated builds of the same material name

## 2026-08-23

### Added
- Unified structured logger (`core/logger.py`): ERROR/WARN/SKIP/INFO/DEBUG/OK levels, bounded ring buffer, `scope()` context, `poll()` batch consumption; no callback API
- Unified Log tab (`ui/tabs/log_tab.py` + embedded `ui/log_panel.py` LogViewer) shared by all tabs: level/source/text filters, presets, search, copy, clear, auto-scroll, drop counters

### Changed
- Converter / Builder / Batch Builder / Node Tools / Debug validation now write all operational logs into the global panel
- Debug and global log viewer merged into one Log tab; Config Validation controls sit above the shared log table
- Removed all silent `except: pass`, direct `print()` and direct `cmds.warning()` calls from `core/` and `ui/`
- Batch conversion/building progress updates are throttled instead of calling `processEvents()` for every log line
- `Logger` and UI `LogModel` now share `DEFAULT_MAX_RECORDS` (20,000) and both enforce bounded retention

### Fixed
- `Logger.scope(source=...)` now applies source with lexical inheritance semantics: inner scope overrides, empty inner scope inherits, explicit per-call source wins
- `LogModel` no longer grows without bound during long Maya sessions; oldest rows are removed with proper Qt model signals
- Added regression tests for logger overflow, cursor behavior across eviction, concurrent writers, writer+poller, production-scale rollover, and bounded Qt `LogModel`
- `NodeToolsTab` Auto Match Selected no longer probes `node.outColor` on non-shader nodes; it uses cached shader node types, skips `place2dTexture`/`file` leaves, deduplicates BFS destinations, and enforces a per-trace node budget
- Tests added for logger and texture scanner; added `scripts/check_no_silent_pass.py` guard

## 2026-08-22

### Fixed
- Auto Match Selected (`ui/tabs/node_tools_tab.py`): ambiguous nodes are now selected with `replace=True` instead of `add=True` — previously the `add` flag appended nodes already present in the current selection, so the selection never visibly changed and users could not identify the nodes flagged for manual review

## 2026-08-20

### Added
- New **Debug** tab (`ui/tabs/debug_tab.py` + `core/config_validator.py`): validates all JSON config spelling against actual Maya node types (materials / `bumpNormal.json` / `colorCorrection.json`); creates temporary nodes to verify `node_type` and every mapped attribute (incl. prerequisites and displacement blocks), then cleans up
- Validation log is filterable by category (Errors / Warnings / Skipped / OK / Info), defaults to problem-only, entries sorted by priority and color-coded

### Changed
- `core/config_loader.py`: add public `get_all_bn_configs()` / `get_all_cc_configs()` getters
- Main window now has 5 tabs: Converter → Material Builder → Batch Builder → Node Tools → Debug
- Main window refactored from `QDialog` to `QMainWindow` so the title bar shows minimize/maximize buttons and the close button works reliably in Maya 2027 (PySide6/Qt6)

### Fixed
- `core/config_validator.py`: plugin detection now uses `pluginInfo(loaded)` + `loadPlugin` (previously `pluginInfo(exists)` returned false for installed-but-not-loaded plugins, wrongly skipping entire installed renderer groups); installed-but-unloaded plugins are now auto-loaded before validation
- `core/config_validator.py`: the `displacementShader` sentinel `node_type` is now created and its attributes validated (previously all skipped); removed the `COMMON_PLACEHOLDERS` false positive — explicitly defined real attributes (e.g. `RedshiftBumpMap.scale`, `aiNormalMap.input`) are no longer mis-skipped as common placeholders
- `ui/styles.py`: main window background rule now targets `QMainWindow` (previously `QDialog`), restoring the dark `#232323` background after the window refactor

### Documentation
- `CONVERSION_SPEC.md` / `CONVERSION_SPEC_zh.md`: trimmed to conversion-only content (removed Material Builder / Batch Builder / Node Tools / Debug / Project Structure sections that overlapped with README); keeps main material attributes, bump/normal, color correction, displacement, node creation, old-node handling, texture connection compatibility, and batch conversion
- `README.md` / `README_zh.md`: added jump links to both `CONVERSION_SPEC` language versions at the top
- `README.md` / `docs/README_zh.md` / `docs/AGENTS.md`: main window description updated to `QMainWindow` + `QTabWidget`; `docs/AGENTS.md` import example for `converter_ui.py` corrected to `from ui import QtWidgets, shiboken`

## 2026-08-19

### Added
- New **Batch Builder** tab (`ui/tabs/batch_builder_tab.py`) with directory scanning, filename-driven channel parsing, merged parsed/unparsed table (sortable Status), and `Materials to Build` preview list
- `config/texture_channels.json`: filename keyword → channel rules driven by `common.json` builder keys, including common PBR suffixes (Poly Haven / ambientCG / Quixel / Substance / Unity / Unreal presets)
- `core/texture_scanner.py`: non-recursive directory scanning, longest-alias-first matching, token + underscore-tolerant substring matching
- `core/batch_builder.py`: converts scanner output into `MaterialBuilder` short keys and orchestrates batch builds
- `MaterialBuilder` extended channels: Metallic, Opacity, Emission, Transmission, Reflection, Sheen, SSS, and Glossiness (inverted via `file.invert`); new `use_full_chain` option for simple direct connections
- VRayMtl prerequisites now support color/list values (e.g. `reflectionColor: [1, 1, 1]`) via `core/prerequisites.py`
- `config/builder_naming.json`: shorter suffix abbreviations for new builder channels

### Changed
- Material Builder tab UI restructured into 3 channel groups (Color / Scalar / Geometry), each channel with enable checkbox + texture path input; channels now include all 11 supported common attributes (added Metallic, Opacity, Emission, Transmission, Reflection, Sheen, SSS with independent path)
- SSS channel no longer auto-reuses baseColor texture; requires explicit path input like other channels
- Empty texture path with channel enabled now creates an unassigned file node (previously skipped), consistent with batch builder behavior
- Removed the Builder alias layer: manual Builder, Batch Builder, and `MaterialBuilder` now use canonical common attributes directly; `builder_aliases` is no longer part of `config/material/common.json`
- `texture_channels.json` now uses `common_attr` for the canonical `common.json` attribute name
- Batch Builder now passes canonical common attributes directly to Material Builder; removed the `COMMON_ATTR_TO_SHORT` conversion table while preserving existing node naming
- Color-correction node type detection is now driven by `config/colorCorrection.json`; adding a configured CC node type no longer requires updating a hardcoded Python type list
- Tab order in main window: Converter → Material Builder → Batch Builder → Node Tools
- Replaced the isolated "Unparsed Files" panel with an in-table `UNPARSED` status and a `Materials to Build` preview list
- Auto Match Selected (`ui/tabs/node_tools_tab.py`): when filename match and channel match both succeed but return different roles, the file node is treated as ambiguous — skipped (color space unchanged), kept selected, and the conflict is printed to Script Editor for manual review
- Filename color-space keywords now come from `config/texture_channels.json` as the **single source** (grouped by channel `type`: color → srgb, others → raw; aliases < 5 chars filtered); `filenameKeywords` removed from `config/colorSpace.json`
- Channel-match keywords unified: `commonAttributeRoles` in `config/colorSpace.json` is now the single source, aligned with `common.json` canonical names (`metallic`, `normal_bump`, `transmissionColor`, `displacementTexture`); removed `colorSpaces.{role}.attributeKeywords` and the `_norm_attr_keywords` fallback in `node_tools_tab.py` — fixes renderer-specific attributes that were never matched (`bump_input`, `baseMetalness`, `texMap`, `refr_color` etc.), transmission chains now correctly resolve to `srgb`

### Documentation
- `README.md` / `README_zh.md`: add missing files to project structure (`docs/AGENTS.md`, `CHANGELOG_zh.md`, `copy_launch.bat`, `LICENSE`)
- `CONVERSION_SPEC.md` / `CONVERSION_SPEC_zh.md`: fix VRayMtl subsurface mapping (`subsurfaceWeight` → `translucencyAmount`, `subsurfaceColor` → `translucencyColor` instead of `-`); remove non-existent `reflectionColorAmount` prerequisite; fix Builder description from "Converter panel's second tab" to "dedicated second tab"; add missing `copy_launch.bat` and `LICENSE` to project structure
- `AGENTS.md`: add missing `"vray": "vray"` to `renderer_map` example

### Fixed
- `core/converters/attribute.py`: rewrite `_fix_alpha_luminance` — scan by the target config's **actual attribute names** (previously queried logical `common_attr` names, silently failing for renderer-specific names like `metalness`/`opacityMap`/`reflectionGlossiness`), **recursively trace upstream** through intermediate nodes (CC/ramp/layeredTexture/bump) to find `outAlpha`, exempt the `opacity` channel, and keep Redshift skipped — fixes `alphaIsLuminance` never being enabled for float channels (roughness/metallic/bump) after `smart_connect` falls back to `outAlpha`
- `core/material_builder.py`: set `alphaIsLuminance` in `make_tex` after `fileTextureName` so the state is not reset when the file loads

### Refactoring
- `core/material_builder.py`: remove `_new` method-name residue — `_build_color_chain_new` / `_build_rough_chain_new` / `_build_bump_normal_new` / `_build_displacement_new` renamed without the suffix
- Merge the four identical color-channel builders (`_build_emission_chain` / `_build_transmission_chain` / `_build_sheen_chain` / `_build_reflection_chain`) and the baseColor/SSS branches into a parameterized `_build_color_chain(common_attr, name_key, ...)`; scalar channels (roughness/metallic/opacity) unified into `_build_scalar_chain(...)` driven by `use_full_chain` + `invert`
- Remove the dead `use_sss` parameter from `MaterialBuilder.build()` (subsurface construction is gated by `input_paths`, not this flag); update `core/batch_builder.py` and `ui/tabs/builder_tab.py` callers and drop the two `use_sss` assertions in `tests/test_batch_builder.py`
- `core/config_loader.py`: rename `NodeMapping.isNormal` / `isNormal_value` to PEP8 `is_normal` / `is_normal_value` (JSON keys in `config/bumpNormal.json` aligned); remove the dead `has_attr` method

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
