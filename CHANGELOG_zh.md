# 更新日志

## 2026-09-11

### 修复
- **同一 Maya 会话中其它扁平结构工具占用 `core` / `ui` 时启动不再失败**：`main.py` 接管时现在会释放 foreign 顶层模块**及其缓存的子模块**；此前只删顶层名，残留的 foreign `core.results`（例如 Batch Attribute Editor 留下的）会遮蔽本项目导入，导致启动报 `ImportError: cannot import name 'ConversionResult'`

### 重构
- `main.py` 启动加固：项目根始终移到 `sys.path` 最前（不再只在缺失时插入），并在本项目导入前释放 `core` / `ui` / `main` 下所有 foreign 模块；路径判断内联实现（`_owned_by_root`），因为为此 import `core.module_reload` 恰恰会被 foreign `core` 截胡
- 运行时延迟导入提到模块顶部（消除接管后延迟导入命中其它工具包的情形）：`ui/feedback.py`（`from ui import QtWidgets`）、`core/builder_context.py`（`ConfigLoader`，并删除局部 sys.path hack）、`core/material_builder.py`（`apply_prerequisites`）

### 文档
- `docs/AGENTS.md`：重载时的模块处理更新为两步接管说明（foreign 顶层 + 缓存子模块），并补充与其它扁平结构工具（如 Batch Attribute Editor）共存的说明
- `README.md` / `docs/README_zh.md`：新增"可共存的启动"设计原则

## 2026-09-10

### 修复
- `ColorSpaceMatcher.ignore_color_space_file_rules()` 的逐节点 `setAttr` 现在包在单个 undo chunk 中（`core/colorspace.py`），与 `_set_colorspaces()` 一致；Colorspace 页"Set ignoreColorSpaceFileRules on All File Nodes"现为单步撤销

### 重构
- **Batch Builder 批量编排下沉 core**：新增 `BatchBuilder.build_all(materials, ..., on_progress=...)`（`core/batch_builder.py`），undo chunk、逐材质异常隔离（`_build_one_safe`，失败记 ERROR 不中断批次）、进度回调异常防护与批次汇总日志全部由 core 负责；`BatchBuilderTab._build_materials` 只保留选择过滤、进度条与结果展示，不再直接调用 `cmds.undoInfo`
- 新增纯 stdlib 结果模型 `BuildResult` + `summarize_build_results()`（`core/results.py`），与 `ConversionResult` 并列，core/UI 共用
- **Colorspace matcher API 不再依赖 UI 行字典**：`ColorSpaceMatcher.apply_matched()` 改为接收 `MatchResult` 列表（`scan()` 的返回值）；`ColorspaceTab` 缓存扫描结果，选择/应用/状态统计均直接基于 `MatchResult`，表格 UserRole 存结果对象
- **ConfigLoader 单例共享**：`ConverterWindow` 创建唯一 `ConfigLoader` 并注入 `BuilderContext` / `ConverterTab` / `ColorspaceTab`；`MaterialBuilder` / `MaterialConverter` / `ColorSpaceMatcher` 支持注入配置（默认行为不变），避免各 Tab 重复加载 JSON
- 目标材质下拉列表填充去重为 `ui/widgets.py:populate_material_targets()`（Converter / Builder / Batch Builder 三处共用）
- `MaterialBuilder.build()` 移除冗余 `use_nrm` / `use_disp` 参数：normal/bump 模式由 `channel_options` 推导（缺省 normal），置换由 `input_paths` 是否含 `displacementTexture` 决定，UI 不再重复计算
- `BatchBuilderTab._scan_directory` 删除与 `TextureScanner` 重复的扫描汇总与 conflict 警告日志
- `Create File From P2D` 从 Material Builder 移至 Node Tools（新增 `Texture Tools` 分组）；反馈改为 Node Tools 现有日志风格（不再弹窗/横幅），实现与行为其余不变
- `NodeToolsTab` 现在接受可选注入的 `ConfigLoader`（`ConverterWindow` 传入共享实例），补全"单例加载"约定；未注入时回退到自建 `ConfigLoader()`
- 批次开始/结束日志统一由 core 输出（`MaterialConverter.convert_all` / `BatchBuilder.build_all`）；`ConverterTab` / `BatchBuilderTab` 不再重复输出（删除 `--- Converting to ... ---`、`--- DONE: ... ---`、`--- Batch build started / finished ... ---`）

### 重命名
- 主窗口模块更名：`ui/converter_ui.py` → `ui/main_window.py`，类 `ConverterWindow` → `MainWindow`，窗口 objectName `pbrConverterWindow` → `materialConvertWindow`（该窗口现已承载 6 个标签页，旧 "converter" 命名已名不副实）；`main.py` 导入同步更新，Shelf 启动命令不变。旧版本创建的窗口在改名后热重载时不会自动关闭，手动关一次即可

### 新增
- 测试：`test_batch_builder.py` 新增 `build_all` 用例（结果顺序、undo 包裹、失败隔离、回调异常不断批、空批次）、`test_conversion_results.py` 新增 `summarize_build_results` 用例、`test_colorspace.py` 新增 `apply_matched` core 用例（仅应用 MATCHED / 失败上报）、`test_builder_context.py` 新增加载器注入用例、`test_colorspace_tab.py` 新增 `NodeToolsTab` 注入配置用例

### 文档
- `README.md` / `docs/README_zh.md`：项目结构树与代码同步——补 `core/results.py`、`core/module_reload.py`、`ui/feedback.py`、`ui/widgets.py`、`ui/log_panel.py`（中文版）、`tests/`、`scripts/check_no_silent_pass.py`、`.github/workflows/test.yml`
- `docs/AGENTS.md`：修正 ConfigLoader 注入范围（含 `NodeToolsTab`）、标签页名称（`Builder` → `Material Builder`）与进度节流描述（每 5 个材质且含最后一个；删除过时的 "或 150ms"）
- `docs/CONVERSION_SPEC.md` / `docs/CONVERSION_SPEC_zh.md`：批量转换章节补充 `partial_wired` 语义（仅接线部分 SG 仍计成功，批次汇总 WARN）
- `README.md` / `docs/README_zh.md`：新增"开发"章节（pytest 命令 + CI 守卫脚本）

## 2026-09-07

### 重构
- **Colorspace 功能从 Node Tools 迁移为独立标签页**：`Node Tools` 删除全部 colorspace UI 与操作（Set File Color Space / Auto Match Selected / Color Management），只保留 Select Nodes 与 Rename Shading Engine；colorspace 功能唯一入口迁移到新 **Colorspace** 标签页（`ui/tabs/colorspace_tab.py`），`ignoreColorSpaceFileRules` 工具同步迁入
- **主窗口标签页顺序调整**：Converter → Material Builder → Batch Builder → **Colorspace** → Node Tools → Log（Colorspace 为第 4 个标签页）
- **Colorspace UI 与核心职责进一步收敛**：`ColorspaceTab` 仅负责界面展示、表格选择与交互；场景扫描、自动匹配应用、手动设置颜色空间、`ignoreColorSpaceFileRules` 和 undo 处理统一下沉到 `ColorSpaceMatcher`，并统一返回 applied / failed / skipped 结果

### 新增
- 单一 matcher 核心 `core/colorspace.py`：`NameDriver`（文件名关键词，来自 `config/texture_channels.json`）+ `ChannelDriver`（BFS 下游通道追踪，保留 depth/budget 遍历保护与材质缓存）+ `ColorSpaceResolver`（role→alias→实际 Maya colorspace，available spaces 按 Refresh 缓存）+ `ColorSpaceMatcher`（`MATCHED`/`CONFLICT`/`AMBIGUOUS`/`UNMATCHED`/`INVALID` 五态 + prematch 预测 + diagnostic）；配置仍以 `colorSpace.json` / `texture_channels.json` 为单一来源，不引入第二套规则
- Colorspace 标签页：场景 file 节点列表（File Node / File Path / Colorspace / Prematch / Diagnostic，状态词并入 Diagnostic 列并按严重度排序，去掉独立 State 列）、Refresh（只评估不改 scene）、Apply Selected / Apply All Matched（仅应用 `MATCHED`，undo chunk 包裹）、Manual Colorspace Assignment（Maya 实际 input spaces）、行选择同步 Maya 节点选择
- 行为收紧（文档要求）：Name/Channel driver 内部多角色命中显式标记 `AMBIGUOUS`（不再静默取第一个）；无匹配不再回退默认 `raw`（`UNMATCHED` 不自动应用）；role 无法解析到实际 Maya colorspace 时为 `INVALID`，无静默 fallback
- 测试：`tests/test_colorspace.py`（drivers / matcher / resolver，含从 `test_node_tools_trace.py` 迁入的 BFS 预算与跳过用例）、`tests/test_colorspace_tab.py`（UI 集成：Refresh 不改 scene、Apply 仅 MATCHED、Manual 生效、Node Tools 旧 colorspace 已移除）

## 2026-09-06

### 修复
- **SG 连接失败不再静默计为成功**：`MaterialConverter.convert()` 改为返回结构化 `ConversionResult`（`created` / `converted` / `wired` / `total_sgs` / `skipped` / `reason`）；创建成功但**所有** shadingEngine 接线均失败的材质计入 failed（unwired）——场景仍在渲染旧材质时绝不显示为成功
- **置换按"逐 shadingEngine"转换**：同一材质挂多个 SG 时不再只处理第一个（此前 `node_utils.get_shading_engine()` 只取首个 SG，导致部分模型置换缺失/错配）；源置换相同（纹理插头 + scale）的 SG 复用同一目标置换节点
- `core/module_reload.py` 通过 CI 守卫：`is_project_module` 判定改为无异常路径（isinstance 校验取代裸 `except Exception:`），不再触发 `scripts/check_no_silent_pass.py`

### 变更
- `convert_all(..., on_progress=...)` 新增可选逐材质进度回调（core 不依赖 Qt）；Converter 页注入节流回调，在批次运行期间实时推进进度条并 `processEvents()`，不再等全部完成后一次性拨动
- 结果模型提取为纯模块 `core/results.py`（`ConversionResult` + `summarize_results`），core 与 UI 共用、可在无 Maya 环境单测
- `main.py` 启动模块清理改为按文件物理路径判断（`core/module_reload.py`），不再按 `core`/`ui` 名称前缀删除，避免误伤同一 Maya 会话中同名的其他工具包；`node_utils.get_shading_engine()`（取首个 SG 的反模式）移除

### 新增
- 测试：`tests/test_conversion_results.py`（结果分类语义：unwired / partial_wired / 无 SG 浮动材质等）、`tests/test_module_reload.py`（路径清理只删本项目模块）

## 2026-08-30

### 修复
- Builder 操作失败时的错误处理链二次异常：`qt_maya_logger` 把非 QWidget 的 `BuilderTab` 实例传给 `QMessageBox.critical(parent, ...)`，必然抛 `TypeError`，且在 `raise` 之前逃逸——原始异常 traceback 被掩盖，日志与弹窗反馈全部失效
- 错误反馈重构为 best-effort：logger / 弹窗 / 横幅任一环节失败都不再改变业务控制流——logger 失败回退到 stderr（`_report_terminal`，不依赖 logger/UI/Maya），弹窗失败记录 WARN；所有路径仍重新抛出原始异常。START / SUCCESS 日志与 inViewMessage 横幅同样防护

### 重构
- `qt_maya_logger` 从 `core/builder_context.py` 迁移到 `ui/feedback.py`（操作反馈属 UI 层职责）：`core.builder_context` 恢复零 UI 依赖，可在无 UI/PySide 环境下独立 import（新增守护测试）
- `QMessageBox.critical` parent 改为 `None`，消除对调用方实例类型的隐式依赖
- 新增测试：`tests/test_builder_context.py`（8 个）、`tests/test_feedback.py`（9 个，错误链全路径：业务异常 / 弹窗失败 / logger 失败 / START 与成功路径反馈失败）

## 2026-08-25

### 新增
- 新增 61 个单元测试（共 110 个，无需 Maya）：`config_loader` 规范硬性规则与 common 段合并、`texture_scanner` 别名匹配（短词仅 token、下划线穿插+边界、长别名优先）、`node_utils` hue 跨渲染器换算与 `smart_connect` 回退链、`config_validator` 插件失败整组 SKIP 与清理、attribute 转换器 float 广播/color 首通道回退/黑色归零、`batch_builder` 通道映射、`MaterialBuilder` 静默回归
- 单消费者拉取 API `Logger.drain(after_seq)`：返回新记录 + 上次 drain 之后被逐出的记录序号（`evicted_seqs`）；落后超过一个完整缓冲区时返回 `reset=True` 全量快照用于整体重同步
- `LogModel.replace_records()` / `remove_by_seqs()`：UI 日志模型现在精确镜像 Logger 环形缓冲区，不再保留已被关键记录替换淘汰的过期行
- 结构化日志节点：`LogRecord.nodes` 在日志写入时携带可选择的 Maya 节点名；Log 面板中带节点的日志可右键 `Select Node(s)` 直接选择

### 变更
- `MaterialBuilder` 不再为输入纹理集中缺失的通道记录 `DEBUG` "not in input paths, skipped"——这是每次构建的正常分支，不是值得展示的事件；配置缺失类 `SKIP` 日志（如 no target attribute mapping）仍保留
- LogViewer 拉取从 `Logger.poll()` 切换为 `Logger.drain()`：环形缓冲中淘汰的行通过正确的 Qt model 信号从表格移除；reset 时整体替换
- 级别过滤复选框统一为单一 `_LEVEL_UI` 配置表（标签/颜色/默认勾选）；OK 与 Debug 默认仍不勾选
- 复制到剪贴板的日志每行附带时间戳、source 上下文键值与级别
- `node_utils.identify_node_type()` / `create_cc_node()` / `create_target_material()` 接受可选注入的 `logger`；converter/bump/cc 调用方传入各自实例 logger，不再回落到全局 logger
- `MaterialBuilder` 的 p2d → file 连接使用 `BuilderContext.connect(..., quiet=True)`，每个 file 节点只发一条汇总 DEBUG，不再逐连接刷屏

### 修复
- `node_utils.node_name_from_plug()` 收到 `None` 时崩溃（`smart_connect` 空 plug 警告路径触发）；现在容忍空值输入
- 非关键写入从环形缓冲中部淘汰关键记录时 `dropped_critical` 计数未自增（反向场景误自增）

### 重构
- `bumpNormal.json` / `colorCorrection.json`：连接字段统一为 `input`/`output`（取代 `source_connection`/`target_connection`）；vray 段 `input_type`/`input_type_value` 统一为 `is_normal`/`is_normal_value` 并删除 `node_type: ""`；`bumpNormal.json` common 段删除无消费方的 `input`/`output` 死键
- 删除无消费方字段：`config/material/*.json` 的 `material.target_connection`
- `config/builder_naming.json`：修正 disp 前缀大小写（`disP_` → `disp_`）
- 同步：`config_loader.py`（NodeMapping/ColorCorrectionConfig 字段）、`bump.py`（删 input_type 双分支）、`material_builder.py`、`config_validator.py`、`node_utils.py`、`cc.py`、`test_config_loader.py`
- 文档：`AGENTS.md` 新增 `bumpNormal.json` 统一 Schema 与渲染器 tex node 扩展点说明

### 修复
- Builder 横幅日志不再显示误导性 `Unknown`：`qt_maya_logger` 改为必填 `label` 参数，调用点标注操作名（Builder / P2D File）
- 快速选择集命名改为由唯一化后的材质节点名派生（`QS_` + 节点名）：不再依赖 Maya 自动改名，日志与场景一致，重复构建同名材质时集合名确定

## 2026-08-23

### 新增
- 统一结构化日志核心（`core/logger.py`）：ERROR/WARN/SKIP/INFO/DEBUG/OK 级别、有界环形缓冲、`scope()` 上下文、`poll()` 批量拉取；不再提供 callback API
- 统一 Log 标签页（`ui/tabs/log_tab.py` + 嵌入式 `ui/log_panel.py` LogViewer）：级别/来源/文本过滤、预设、搜索、复制、清空、自动滚动、丢弃计数

### 变更
- Converter / Builder / Batch Builder / Node Tools / Debug 校验日志全部接入全局 Log 面板
- Debug 与全局日志查看器合并为同一个 Log 标签页，Config Validation 控件位于共享日志表上方
- 移除 `core/` 与 `ui/` 中所有静默 `except: pass`、直接 `print()`、直接 `cmds.warning()`
- 批量转换/构建进度更新改为节流刷新，不再为每条日志调用 `processEvents()`
- `Logger` 与 UI `LogModel` 现在共用 `DEFAULT_MAX_RECORDS`（20,000），两侧均有界保留

### 修复
- `Logger.scope(source=...)` 现在按词法作用域继承 source：内层覆盖、空内层继承、单条日志显式 source 优先
- `LogModel` 在长时间 Maya 会话中不再无限增长；最旧行通过正确的 Qt model 信号淘汰
- 新增 logger 溢出、淘汰后游标、并发写入、writer+poller、生产规模滚动、有界 Qt `LogModel` 回归测试
- `NodeToolsTab` Auto Match Selected 不再对非 shader 节点探测 `node.outColor`；改为缓存 shader 节点类型、跳过 `place2dTexture`/`file` 叶子、去重 BFS 目标，并限制单次 trace 节点预算
- 新增 logger 与纹理扫描测试，新增 `scripts/check_no_silent_pass.py` 守卫脚本

## 2026-08-22

### 修复
- Auto Match Selected（`ui/tabs/node_tools_tab.py`）：歧义节点改用 `replace=True` 选中（此前为 `add=True`）——`add` 追加的是当前选择中已存在的节点，选择不会产生任何可见变化，用户无法识别被标记为需手动复核的节点

## 2026-08-20

### 新增
- 新增 **Debug** 标签页（`ui/tabs/debug_tab.py` + `core/config_validator.py`）：在 Maya 中校验全部 JSON 配置拼写（材质 / `bumpNormal.json` / `colorCorrection.json`），创建临时节点验证 `node_type` 与每个映射属性（含 prerequisites、displacement 段），结束后自动清理临时节点
- 校验日志支持按类别筛选（Errors / Warnings / Skipped / OK / Info），默认只显示问题类，条目按优先级排序并按类别着色

### 变更
- `core/config_loader.py`：新增 `get_all_bn_configs()` / `get_all_cc_configs()` 公开 getter
- 主窗口标签页增至 5 个：Converter → Material Builder → Batch Builder → Node Tools → Debug
- 主窗口由 `QDialog` 重构为 `QMainWindow`，标题栏恢复最小化/最大化按钮，并修复 Maya 2027（PySide6/Qt6）下关闭按钮失灵

### 修复
- `core/config_validator.py`：插件检测改用 `pluginInfo(loaded)` + `loadPlugin`（此前 `pluginInfo(exists)` 对已安装但未加载的插件误判为 not found，导致已安装渲染器被整组跳过）；已安装但未加载的插件现在会先自动加载再校验
- `core/config_validator.py`：`displacementShader` 哨兵 `node_type` 现在会创建节点并实际校验其属性（此前全部跳过）；移除 `COMMON_PLACEHOLDERS` 误判——显式定义的真实属性（如 `RedshiftBumpMap.scale`、`aiNormalMap.input`）不再被误判为 common 占位符跳过
- `ui/styles.py`：主窗口背景规则改为作用于 `QMainWindow`（原为 `QDialog`），重构后恢复暗色 `#232323` 背景

### 文档
- `CONVERSION_SPEC.md` / `CONVERSION_SPEC_zh.md`：精简为仅转换相关内容（移除 Material Builder / Batch Builder / Node Tools / Debug / 项目结构章节，与 README 重叠部分删除），只保留主材质属性、凹凸/法线、颜色校正、置换、节点创建、旧节点处理、纹理连接兼容性、批量转换
- `README.md` / `README_zh.md`：顶部新增两个 `CONVERSION_SPEC` 语言的跳转链接
- `README.md` / `docs/README_zh.md` / `docs/AGENTS.md`：主窗口描述更新为 `QMainWindow` + `QTabWidget`；`docs/AGENTS.md` 中 `converter_ui.py` 的导入示例修正为 `from ui import QtWidgets, shiboken`

## 2026-08-19

### 新增
- 新增 **Batch Builder（批量构建）** 标签页（`ui/tabs/batch_builder_tab.py`）：目录扫描、按文件名解析通道、已解析/未解析合并表格（Status 可排序）、Materials to Build 待创建材质预览
- 新增 `config/texture_channels.json`：文件名关键词 → 通道规则，`common_attr` 复用 `common.json` 的通道名，并补充常见 PBR 后缀（Poly Haven / ambientCG / Quixel / Substance / Unity / Unreal 预设）
- 新增 `core/texture_scanner.py`：非递归目录扫描，长别名优先 + token 匹配 + 忽略下划线子串（带边界检查）
- 新增 `core/batch_builder.py`：把扫描结果转换为 `MaterialBuilder` 短 key 并编排批量构建
- `MaterialBuilder` 扩展通道：Metallic / Opacity / Emission / Transmission / Reflection / Sheen / SSS / Glossiness（通过 `file.invert` 自动反相）；新增 `use_full_chain` 参数支持简单直连
- VRayMtl 的 prerequisites 现在支持颜色/列表值（如 `reflectionColor: [1, 1, 1]`），通过 `core/prerequisites.py` 实现
- `config/builder_naming.json`：新增更短的通道后缀缩写

### 变更
- Material Builder 标签页 UI 重构为 3 个通道分组（Color / Scalar / Geometry），每个通道带启用复选框 + 纹理路径输入；通道现涵盖全部 11 个支持的通用属性（新增 Metallic、Opacity、Emission、Transmission、Reflection、Sheen、SSS 独立路径）
- SSS 通道不再自动复用 baseColor 纹理；需要与其他通道一样提供明确的路径输入
- 通道启用但纹理路径为空时现在会创建未指定纹理的 file 节点（此前跳过），与批量构建行为一致
- 移除 Builder 别名层：手动 Builder、Batch Builder 与 `MaterialBuilder` 现在都直接使用规范通用属性名；`builder_aliases` 不再存在于 `config/material/common.json`
- `texture_channels.json` 使用 `common_attr` 表示规范的 `common.json` 属性名
- Batch Builder 现在将通用属性名直接传入 Material Builder；移除 `COMMON_ATTR_TO_SHORT` 转换表，同时保持现有节点命名不变
- 颜色校正节点类型识别改由 `config/colorCorrection.json` 驱动；新增已配置的 CC 节点类型不再需要维护 Python 硬编码类型列表
- 主窗口标签页顺序：Converter → Material Builder → Batch Builder → Node Tools
- 将独立的 "Unparsed Files" 面板合并进表格（Status 显示 `UNPARSED`），并新增 Materials to Build 待创建材质列表
- Auto Match Selected（`ui/tabs/node_tools_tab.py`）：当文件名匹配与通道匹配均命中但返回角色不同时，该 file 节点判定为歧义——跳过自动设置（色彩空间不变）、保留选中，并在 Script Editor 打印冲突详情供手动复核
- 文件名色彩空间关键词改为以 `config/texture_channels.json` 为**唯一来源**（按通道 `type` 分组：color → srgb、其余 → raw；过滤 < 5 字符短别名）；删除 `config/colorSpace.json` 中的 `filenameKeywords`
- 通道匹配关键词统一：`config/colorSpace.json` 的 `commonAttributeRoles` 成为唯一来源，键对齐 `common.json` 规范名（`metallic`、`normal_bump`、`transmissionColor`、`displacementTexture`）；删除 `colorSpaces.{role}.attributeKeywords` 与 `node_tools_tab.py` 的 `_norm_attr_keywords` 兜底——修复此前从未被匹配的渲染器专属属性（`bump_input`、`baseMetalness`、`texMap`、`refr_color` 等），透射链现正确归类为 `srgb`

### 文档
- `README.md` / `README_zh.md`：项目结构补全遗漏文件（`docs/AGENTS.md`、`CHANGELOG_zh.md`、`copy_launch.bat`、`LICENSE`）
- `CONVERSION_SPEC.md` / `CONVERSION_SPEC_zh.md`：修正 VRayMtl subsurface 映射（`subsurfaceWeight` → `translucencyAmount`、`subsurfaceColor` → `translucencyColor`，而非 `-`）；删除不存在的 `reflectionColorAmount` 前提条件；修正 Builder 位置描述（"Converter 面板的第二个标签页" → "独立的第二个主标签页"）；项目结构补全 `copy_launch.bat` 和 `LICENSE`
- `AGENTS.md`：`renderer_map` 示例补充 `"vray": "vray"`

### 修复
- `core/converters/attribute.py`：重写 `_fix_alpha_luminance` — 改用目标配置的**实际属性名**扫描（此前用逻辑名 `common_attr` 直查目标材质属性，渲染器专属属性名如 `metalness`/`opacityMap`/`reflectionGlossiness` 静默失效）、**递归上游追踪**中间节点（CC/ramp/layeredTexture/bump）查找 `outAlpha`、豁免 opacity 透明度通道、Redshift 跳过 — 修复 `smart_connect` 回退到 `outAlpha` 后浮点通道（roughness/metallic/bump）`alphaIsLuminance` 从不开启的问题
- `core/material_builder.py`：`make_tex` 中 `alphaIsLuminance` 移到 `fileTextureName` 之后设置，避免纹理加载后状态被重置

### 重构
- `core/material_builder.py`：移除 `_new` 方法名残留 — `_build_color_chain_new` / `_build_rough_chain_new` / `_build_bump_normal_new` / `_build_displacement_new` 去掉后缀重命名
- 将 4 个完全重复的颜色通道构建方法（`_build_emission_chain` / `_build_transmission_chain` / `_build_sheen_chain` / `_build_reflection_chain`）与 baseColor/SSS 分支合并为参数化 `_build_color_chain(common_attr, name_key, ...)`；标量通道（roughness/metallic/opacity）统一为 `_build_scalar_chain(...)`，由 `use_full_chain` + `invert` 驱动
- 移除 `MaterialBuilder.build()` 的死参数 `use_sss`（subsurface 构建一直由 `input_paths` 决定，与该标志无关）；同步更新 `core/batch_builder.py`、`ui/tabs/builder_tab.py` 调用方，并删除 `tests/test_batch_builder.py` 中两个断言 `use_sss` 的用例
- `core/config_loader.py`：`NodeMapping.isNormal` / `isNormal_value` 改为 PEP8 命名 `is_normal` / `is_normal_value`（`config/bumpNormal.json` 的 JSON 键同步对齐）；删除未使用的死方法 `has_attr`

## 2026-08-17

### 移除
- `ui/tabs/transform_tab.py`、`attr_modifier_tab.py`、`locator_tab.py`（及其标签页）：移除 Transform Tools / Attr Modifier / Locator 三个面板

### 重构
- **Builder 配置统一到 Convert 体系**：删除 `config/builder_specs.json`；Builder 渲染器规格改从 `config/material/*.json`（`node_type`/`plugin`/属性映射）+ `bumpNormal.json` + `colorCorrection.json` + 材质 JSON 的 `displacement` 块读取
- 新增 `core/material_builder.py`：构建逻辑从 `ui/tabs/builder_tab.py` 下沉到 core，完全配置驱动
- `ui/tabs/builder_tab.py`：材质类型下拉框由全部材质 JSON 驱动（新增材质自动出现）；全宽 BUILD 按钮；可选"加入快速选择集"开关
- `config/material/*.json`：新增 `plugin` 字段；displacement 块扩展 `file_source`/`lyr_src`/`output`；修正 `VRayMtl` subsurface 映射（`ssColor` → `translucencyColor`，此版本 VRayMtl 无 `ssColor` 属性）
- `config/bumpNormal.json`：为 Builder 新增 `file_source`/`default_scale`
- **pymel 全面迁移至 `maya.cmds`**：`core/node_utils.py`、`core/prerequisites.py`、`core/converter.py`、`core/converters/*`（attribute/bump/cc/displacement）、`ui/tabs/converter_tab.py` —— Maya 2027 起不再支持 pymel；plug 一律改为 `"node.attr"` 字符串

### 缺陷修复
- `core/converters/attribute.py`：float 值设置到 `float3` 目标属性时自动广播为 (v, v, v)（如 Arnold `opacity`、V-Ray `opacityMap`、Redshift `ms_radius`）
- `core/node_utils.py`：解包 `cmds.getAttr()` 嵌套列表格式 `[(1,1,1)] → (1,1,1)`，恢复颜色值传递与黑色归零（pymel 迁移回归）
- `config/material/VRayMtl.json`：修正 `coatIor` → `coatIOR`（属性名大小写错误，此前 coat IOR 从未传递）
- `core/converters/cc.py`：跨渲染器转换时保持源材质 CC 链——共享中间节点（layeredTexture）场景下，源属性改接回原 CC，不再被目标渲染器 CC 污染
- Hue 映射：`config/colorCorrection.json` 各渲染器新增 `hue_center`；`core/node_utils.py` 将 hue 转换为通用偏移角 [-180, 180]（`0` = 无变化）——修复 Redshift `hue=0` 被映射为 Arnold `hueShift=-1`（应为 0）的错误

### 功能增强
- 自动色彩空间匹配（`ui/tabs/node_tools_tab.py`、`core/config_loader.py`）：通道匹配改为 BFS 追踪 file 节点**全部下游连接**（单通道 `outColorR/G/B`、`outAlpha`、穿越 colorCorrect/layeredTexture/multiplyDivide/bump 等中间节点），不再只查 `outColor`；属性名匹配前规范化（小写、去除 `_`/`-`）；追踪时跳过 Maya 默认渲染列表容器

### 文档
- `README.md` / `README_zh.md` / `CONVERSION_SPEC.md` / `CONVERSION_SPEC_zh.md` / `AGENTS.md`：移除已删除面板、更新 Builder 配置来源、pymel → cmds、项目结构

## 2026-08-13

### 功能增强
- `copy_launch.bat`（新建）：双击复制 Maya 启动命令到剪贴板，无需手动配置路径
- `README.md` / `README_zh.md` / `AGENTS.md`：新增"方式三：使用 bat 文件"安装方式

## 2026-07-14

### 功能增强
- `config/colorSpace.json`：新增 `commonAttributeRoles` 字段，定义通用属性到颜色空间角色的映射
- `core/config_loader.py`：新增 `get_expanded_attribute_keywords()` 方法，从所有材质配置动态构建属性映射
- `ui/tabs/node_tools_tab.py`：`_match_by_channel()` 使用扩展映射覆盖所有渲染器专属属性
- 自动匹配色彩空间现支持所有 `config/material/` 文件夹中的材质类型，无需手动维护

## 2026-07-05

### Bug 修复
- 修复 `node_utils.py` 中 `is_cc_node()` 的 Redshift CC 节点类型名错误（`rsColorCorrection` → `RedshiftColorCorrection`），导致 Redshift 颜色校正链检测失败
- 修复 `cc.py` 中 `renderer_map` 缺少 V-Ray 映射（补充 `"vray": "vray"`），与 `bump.py`、`displacement.py` 保持一致

### 代码清理
- 提取 `renderer_short` 映射为 `node_utils.py` 中的共享常量 `RENDERER_SHORT`，消除 `bump.py`、`cc.py`、`displacement.py` 中的重复定义
- 提取 `config_loader.py` 中的 `_load_renderer_config` 方法，消除 `_load_bump_normal` 和 `_load_color_correction` 中的重复逻辑
- 提取 `p2d_attrs` 列表为 `builder_tab.py` 中的 `BuilderTab.P2D_ATTRS` 类常量，消除重复定义
- `node_tools_tab.py` 中复用已有的 `self.config` 实例，消除冗余的 `ConfigLoader()` 创建

### 文档更新
- `CONVERSION_SPEC.md` / `CONVERSION_SPEC_zh.md`：映射表补充遗漏的 `RedshiftStandardMaterial` 列
- `CONVERSION_SPEC.md` / `CONVERSION_SPEC_zh.md`：项目结构补充遗漏的 `RedshiftStandardMaterial.json` 和 `colorSpace.json`
- `CONVERSION_SPEC.md` / `CONVERSION_SPEC_zh.md`：修复项目结构树格式错误

## 2026-07-02

### 文档更新
- `README.md` / `README_zh.md`：明确支持 Maya 2024+，补充 PyMEL 依赖说明及官方文档链接

## 2026-07-01

### Bug 修复
- 修复 `CONVERSION_SPEC.md` 映射表中 VRayMtl `specularWeight` 拼写错误（`reflectionColorAmoun` → `reflectionColorAmount`）
- 移除 `ui/__init__.py` 末尾循环导入的 `show` 函数，消除循环导入风险
- 移除 `converter_tab.py` 冗余的 `sys.path` 操作（`main.py` 已处理）
- 修复 float3 值设置到 float 属性时类型不兼容问题（如 V-Ray opacityMap → Arnold geometryOpacity）
- 修复 `attribute.py` 缺少 `import pymel.core as pm` 导致转换卡死
- 修复 `_fix_alpha_luminance` 检测逻辑：改为扫描目标材质实际连接，解决 `smart_connect` 将 outColor 切换为 outAlpha 后 alphaIsLuminance 未开启的问题

### 架构重构
- `core/node_utils.py`：从静态方法类（`NodeUtils`）改为模块级函数，使用 `import core.node_utils as node_utils`
- `core/converter.py`：接受可选 `logger` 参数，内部使用 `node_utils` 模块
- `core/builder_context.py`：PySide 导入改用 `from ui import QtWidgets`，移除独立 try/except
- `core/__init__.py`：移除静默 try/except 包裹，改为直接导入
- `ui/tabs/converter_tab.py`：消除重复的 `ConfigLoader`/`NodeUtils` 实例，复用 `node_utils` 模块

### 代码清理
- `core/logger.py`（新建）：统一日志模块，支持回调函数，UI 层注册回调更新日志面板
- `ui/tabs/node_tools_tab.py`：bump 节点类型和 CC 节点类型改为从配置读取，不再硬编码
- `core/config_loader.py`：新增 `get_all_cc_types()` 方法
- `core/converters/bump.py`、`displacement.py`：关键异常路径加入 `pm.warning()` 日志
- `core/node_utils.py`：`set_cc_params`、`transfer_connection_to_plug`、`connect_plug_to_plug`、`delete_node_safe` 异常加日志
- `core/converters/cc.py`：CC 连接失败加日志
- `core/converter.py`：SG 连接失败加日志
- `core/converters/attribute.py`：值设置失败、emission weight 设置失败加日志
- `core/prerequisites.py`：前提属性设置失败加日志

### UI/UX 改进
- `ui/tabs/converter_tab.py`：批量转换添加 `QProgressBar` 进度条，转换过程中调用 `processEvents()` 保持 UI 响应
- `ui/tabs/builder_tab.py`：渲染器按钮从 `builder_specs.json` 动态生成，新增渲染器只需改配置
- `core/converter.py`：`convert_all()` 包裹 `cmds.undoInfo(openChunk/closeChunk)`，整个批量转换可单步撤销
- `ui/tabs/node_tools_tab.py`：新增 "Auto Match Selected" 功能，根据文件名（优先）和连接通道（次选）自动匹配选中 file 节点的色彩空间
- `config/colorSpace.json`：重构为 colorSpaces.{role}.{aliases/filenameKeywords/attributeKeywords} 结构，支持多 OCIO 配置自动适配

### 文档更新
- `README.md`：更新功能描述和项目结构
- `AGENTS.md`：更新架构说明（NodeUtils 改为模块、新增 logger 模块）
- `CONVERSION_SPEC.md`：更新项目结构，修复映射表拼写错误
