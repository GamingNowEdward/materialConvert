# AGENTS.md — PBR 材质转换器

## 安装与运行

将 `materialConvert` 文件夹放到任意位置，在 Maya 中建一个 Shelf 按钮粘贴以下 3 行（把路径换成你的实际路径）：

**方式一：复制到 Maya scripts 目录（推荐）**

```python
import sys
sys.path.insert(0, r"C:\Users\<用户名>\Documents\maya\<版本>\scripts\materialConvert")
exec(open(r"C:\Users\<用户名>\Documents\maya\<版本>\scripts\materialConvert\main.py").read())
```

**方式二：放在任意目录**

```python
import sys
sys.path.insert(0, r"你的路径\materialConvert")
exec(open(r"你的路径\materialConvert\main.py").read())
```

**方式三：使用 bat 文件（最简单）**

双击运行 `copy_launch.bat`，启动命令会自动复制到剪贴板，直接在 Maya Script Editor 中粘贴即可。

本项目**零外部依赖**，不需要 pip install。分发给他人时只需拷贝文件夹并告诉对方改 shelf 按钮路径即可。

**启动契约**：`main.py` **不依赖 `__file__`**。它先看 `__file__` 指向的目录是否真的是本项目（含 `core/__init__.py`），否则回退到 `sys.path` 中第一个同时含 `main.py` 与 `core/__init__.py` 的目录。因此上面两种 `exec(open(...).read())` 写法（不设置 `__file__`）与 `copy_launch.bat`（显式注入 `__file__`）都能正确解析项目根；两者都解析不到时只在 stderr 提示并跳过模块接管。

如果修改代码后没生效，关掉窗口重新点击按钮即可。重新加载时 `main.py` 分两步处理模块：

1. **接管顶层名**：把项目根置顶到 `sys.path`，并释放 `core` / `ui` / `main` 下所有**来自其它路径**的模块及其缓存的子模块（例如别的工具残留的 `core.results`，否则后续导入会命中残留对象）；路径判断内联在 `main.py`（`_owned_by_root`），不能为此 import `core.module_reload`——那一步本身就会被 foreign `core` 截胡；
2. **清理自身**：`core/module_reload.py` 按文件物理路径清理本项目的已导入模块，不会误删其它工具的包。

因此同一 Maya 会话里可以与其它扁平结构工具（如 Batch Attribute Editor）共存："后启动者赢"，先启动的工具依靠已导入的模块对象继续工作。

## 架构

**数据流：`源材质属性 → [源 JSON 配置] → 通用格式 → [目标 JSON 配置] → 目标材质属性`**

- 所有渲染器映射定义在 `config/*.json` 中，Python 代码中**零硬编码渲染器类型名**
- 新增渲染器支持：**只需添加 JSON 文件，不需要改业务代码**
- 四个转换模块位于 `core/converters/` 目录下：
  - `attribute.py` — 材质属性收集与传递 + 黑色颜色自动归零 + Alpha Is Luminance 自动开启（按目标配置实际属性名扫描、递归上游追踪、opacity 豁免、Redshift 跳过）+ 源属性反转（`material.invert` 声明的通道按 `1 - x` 反转；贴图/CC 连接在目标插槽前串入 Maya `reverse` 节点，源链不动）
  - `bump.py` — 凹凸/法线节点检测与转换（独立节点 / 共享类型 / 材质内嵌）
  - `cc.py` — 颜色校正链检测（通过 `listHistory`）、转换、跨通道复用；**按拓扑分流**：`direct`（CC 直连材质）走原逻辑（**目标材质通道始终单独接线**，不依赖既有下游列表；CC 输出插槽优先取源链实际使用的那个，如标量通道的 `outAlpha`，并经 `smart_connect` 回退），`single_hop`（CC → 中间节点 → 材质）**复制中间节点**后接入新 CC，`unsupported`（多级链）不触碰源网络并记入结果 `unsupported/issues`
  - `displacement.py` — 置换节点转换（Redshift ↔ 原生 `displacementShader`）；**逐 shadingEngine 转换**（置换挂在 SG 上），转换器一次性枚举源材质全部 SG 传入，源置换相同的 SG 复用同一目标节点
- 颜色校正节点类型以 `config/colorCorrection.json` 为单一来源；`node_utils.is_cc_node()` 通过 `ConfigLoader.get_all_cc_types()` 判断，禁止在 Python 中维护 CC 节点类型列表
- 调度器：`core/converter.py` — `MaterialConverter` 接受可选 `logger` 参数；`convert()` 返回结构化 `ConversionResult`，`convert_all(..., on_progress=...)` 提供可选逐材质进度回调（core 不依赖 Qt，回调异常只记 WARN 不中断批次）；`_resolve_inverted_attrs()` 按源配置 `material.invert` 读取开关、算出需反转的通用属性并传给属性转换器（读取失败按 glossiness 默认保守反转并记 WARN）。**提交是事务性的**：先 `_snapshot_sg_wiring()` 记录每个 SG 的 `surfaceShader`/`displacementShader` 上游（返回 `(snapshot, unreadable)`），再依次提交 surface、置换；**快照不完整（任一槽读取失败）即在改接前中止**——`reason` 设为 `failed to snapshot shading engine wiring`、不可读槽记入 `sg_failures`、`wired=0`、`converted` 保持 False（材质已创建但未接线，结果计入 `unwired`）、场景零改动；快照完整时任一提交失败 → `_restore_sg_wiring(snapshot, touched)` 只回滚本次提交**实际改写**过的 SG（从未改写的 SG 不再被误恢复、不制造假警报）、`result.restored`/`sg_failures`/`wired_before_rollback` 记录恢复情况、`converted` 保持 False，绝不留下"一半新材质"的未报告场景
- 转换结果模型：`core/results.py` — `ConversionResult`（`created`/`converted`/`wired`/`total_sgs`/`skipped`/`reason`/`sg_failures`/`restored`/`wired_before_rollback`）+ `summarize_results()`，Builder 用的 `BuildResult`（`material`/`new_material`/`built`/`reason`/`issues`/`failures`）+ `summarize_build_results()`，以及各转换器共用的 `TransferOutcome`（`ok`/`issues`/`critical`/`unsupported`，`bool(outcome) == ok`），纯 Python 可单测，core 与 UI 共用。**语义**：创建成功但全部 SG 接线失败 = `unwired`（计入失败，场景仍渲染旧材质，绝不静默报成功）；`unwired` 的判定为 `total_sgs > 0 and wired == 0 and bool(sg_failures)`，即必须真的发生过提交失败，且 `summarize_results` **优先**判定它，否则批次日志的 `unwired` 计数恒为 0；**部分 SG 接线**：按铁律 11（任一失败即回滚）`wired` 只会是 `0` 或 `total_sgs`，因此 `partially_wired` 是**保留的模型能力、当前不可达**，回滚前的成功接线数由 `ConversionResult.wired_before_rollback` 保留并由批次日志与转换页上报；`total_sgs==0` 的浮动材质不计入失败。**SG 枚举失败**（`_find_shading_engines` 查询抛异常）在**创建目标材质之前**即中止转换、设 `reason` 并计入失败。**关键通道失败**（前置条件 / CC 链 / bump-normal / displacement）同样设 `reason` 并计入失败；**非关键通道失败与显式不支持**（单个属性 / emission / alphaIsLuminance / reverse / 不支持的空间或拓扑）记入 `issues`（`converted` 仍 True，汇总计入 `with_issues`，`convert_all` 输出 WARN），绝不静默
- 工具函数：`core/node_utils.py` — **模块级函数**，使用 `import core.node_utils as node_utils`，直接调用 `node_utils.xxx()`；节点识别/创建类函数（`identify_node_type` / `create_cc_node` / `create_target_material`）接受可选 `logger` 参数，调用方应传入实例 logger，未传时回落到 `get_logger()`
- **API 约定：全部使用 `maya.cmds`（字符串式 API，plug 一律 `"node.attr"` 字符串），不依赖 pymel（Maya 2027 起不再支持）**
- 日志：`core/logger.py` — `Logger` 类，结构化级别（ERROR/WARN/SKIP/INFO/DEBUG/OK）+ 环形缓冲 + `scope()` 上下文；UI 不注册回调，而是由 `ui/log_panel.py` 中的嵌入式 `LogViewer` 在 Log 标签页可见时每 150ms 通过单消费者 API `drain(after_seq)` 拉取（返回新记录 + 上次 drain 后被逐出的 `evicted_seqs`；落后超过一个完整缓冲区时返回 `reset=True` 全量快照）
- 配置读取：`core/config_loader.py`（读取 JSON，提供公开查询方法；由 `MainWindow` 创建唯一实例并注入 `BuilderContext` / `ConverterTab` / `ColorspaceTab` / `NodeToolsTab`，其余组件经 `ctx.config` 共享）
- 界面：`ui/main_window.py`（QMainWindow + QTabWidget，6 个标签页：Converter / Material Builder / Batch Builder / Colorspace / Node Tools / Log）；目标材质下拉框统一经 `ui/widgets.py:populate_material_targets()` 从 `ConfigLoader` 填充
- 操作反馈：`ui/feedback.py` — `qt_maya_logger(label)` 操作反馈装饰器（START/成功横幅 + 错误弹窗）。**所有反馈均为 best-effort**：logger / 弹窗 / 横幅任一环节失败都不能改变业务控制流——logger 失败回退 `_report_terminal`（stderr 通道，不依赖 logger/UI/Maya），弹窗失败记录 WARN；原始异常始终重新抛出。core 层禁止 import ui 包，反馈装饰器只能放 UI 层。`show_result_banner(failed, with_issues, ok_message=..., partial=...)` 的严重级别顺序为 failed > partial（仅部分 SG 接线）> with_issues > success
- 操作状态：`ui/operation_state.py` — `OperationGuard`（Qt-free，纯 Python 可测）：`try_begin()` 拒绝重入并置 busy，`end()` 在 finally 解锁；`ui/main_window.py:_set_busy()` 据此禁用**全部 6 个标签页**注册的提交控件（`ui/widgets.py:set_enabled()` 忽略已销毁控件），保证 `processEvents()` 期间跨页重复提交不会产生第二个批次。**Maya 场景命令仍留在主线程**，不因批量而引入后台线程
- 样式：`ui/styles.py`（QSS 暗色主题）
- Builder：`core/material_builder.py` — `MaterialBuilder.build(node_type, ...)` 从纹理路径组装材质网络（不含 `use_nrm`/`use_disp` 参数：normal/bump 模式由 `channel_options` 推导、缺省 normal，置换由 `input_paths` 是否含 `displacementTexture` 决定）；`build()` 内部包裹 `undoInfo` open/close（实际实现在 `_build()`），单次构建可一步撤销，`BatchBuilder` 的外层 chunk 与之嵌套合并；`core/builder_context.py`（命名/建节点工具，持有 `config`）
- Builder 配置：**复用 Convert 配置体系**（`config/material/*.json` 的 `node_type`/`plugin`/属性映射 + `bumpNormal.json` + `colorCorrection.json`）+ `config/builder_naming.json`（命名约定 + `ramp_stops`：完整链 ramp 的黑→白停靠点）。完整链的 `ramp` 配置失败（无效/缺失 `ramp_stops`、停靠点写入失败）会记入 `last_build_issues`（非关键 issue，构建结果计为 `with_issues`），绝不静默报成功。`material.builder_prerequisites` 声明 builder 专用的逐通道前置开关（如 V-Ray 的 `ssOn`），由 `core/prerequisites.py:apply_prerequisite_dict()` 消费，禁止在 Python 中硬编码渲染器属性名；`material.output`（缺省 `outColor`）声明材质输出属性。无独立渲染器规格文件，新增材质即自动出现在 Builder 下拉框
- Builder 的手动和批量数据、内部建链一律使用通用属性名（如 `baseColor`、`specularRoughness`）；颜色通道的权重属性由 `color_weight_pairs` 推导，禁止在 `MaterialBuilder` 中维护重复字典
- **Builder 可扩展边界**：转换器（Convert）可由属性 JSON 扩展，但 Builder 只支持已实现的通道策略（color、float、roughness、normal_bump、displacement）。颜色通道经 `_build_color_chain(common_attr, name_key, ...)` 参数化构建，标量通道（roughness/metallic/opacity）经 `_build_scalar_chain(...)` 构建（`use_full_chain` 为**必填**参数，且**只作用于 `specularRoughness`**：`metallic` / `opacity` 显式传 `False` 恒直连，不插入 ramp）；新增"普通属性"仍需在 `MaterialBuilder` 中添加或扩展 Python 建链函数，不能仅靠 JSON 配置
- Batch Builder：`core/texture_scanner.py`（读取 `config/texture_channels.json`，按文件名解析通道、按材质名分组）+ `core/batch_builder.py`（`build_material` 将扫描结果按规范通用属性名传给 `MaterialBuilder`；`build_all(..., on_progress=...)` 负责批量编排——undo chunk、逐材质失败隔离、回调异常防护与汇总日志，返回 `BuildResult` 列表）+ `ui/tabs/batch_builder_tab.py`（面板只做选择过滤、进度条与结果展示）
- 通道规则：`config/texture_channels.json` — `common_attr` 使用 `common.json` 的通道名（如 `baseColor`、`specularRoughness`、`subsurfaceColor`）。文件名匹配采用「长别名优先 + token 匹配 + 忽略下划线子串（带边界检查）」，避免 `met`/`metal` 等短词误触
- 色彩空间：`config/colorSpace.json`（colorSpaces.{role}.aliases OCIO 名称 + `commonAttributeRoles` 单源属性角色映射，**只列通用属性名**，渲染器属性名由 `config/material/*.json` 动态扩展；`default` 键已移除——无消费方）+ `config/texture_channels.json`（文件名关键词按通道 type 分组为 srgb/raw，单一来源）；唯一 matcher 核心在 `core/colorspace.py`（`ColorSpaceMatcher` = `NameDriver` + `ChannelDriver` + `ColorSpaceResolver`，`MatchResult` 携带 state/prematch/diagnostic/**`evidence_complete`**；`apply_matched()` 接收 `MatchResult`，不消费 UI 表格数据结构），UI 入口为 Colorspace 标签页（`ui/tabs/colorspace_tab.py`，缓存扫描结果驱动展示/应用），Node Tools 不再提供任何 colorspace 操作；通道匹配 BFS 追踪 file 全部下游连接并规范化属性名，保留 depth/budget 遍历保护。**证据完整性**：`trace_channel_targets()` 返回 `TraceResult`（`targets`/`complete`/`truncated`/`depth_limited`/`errors`）；深度或预算截断时"没找到冲突"不等于"没有冲突"——仅有 channel 证据且不完整时状态降级为 `AMBIGUOUS`（需人工确认），文件名证据完整时仍可 `MATCHED`。`apply_matched(..., revalidate=True)` 在写入前重新匹配，结果已变化的行计入返回的 `stale` 且不应用（`MatchResult.stale` 字段已删除——恒为 False 且无消费方；`evidence_complete` 由 Colorspace 诊断列消费，证据不完整时追加 `[channel evidence incomplete]`）。文件名关键词匹配与 `TextureScanner` 共用 `normalize_stem()` / `find_alias()`（token + 边界），不再用纯 substring
- Log/Debug：`core/config_schema.py`（**纯 Python 离线结构校验**：必需字段/类型、`material.renderer` 取值、重复 `node_type`、段必须是对象、`prerequisites`/`invert` 结构、`is_normal`/`is_normal_value` 成对、`normal_space` 值域、`extra_nodes` 结构、`texture_channels`/`material` 的跨配置引用、`builder_naming` 数组长度；返回带 `filename`/`field_path` 的 `ConfigIssue`）+ `core/config_validator.py`（`validate_all()` **先跑离线校验**再进入 Maya 实体校验：前者报结构/语义问题，后者创建临时节点校验 node_type 与属性拼写，结束后清理；插件检测用 `pluginInfo(loaded)` + `loadPlugin`，加载失败（未安装/不兼容）时**整组忽略（SKIP）**，不误报为拼写错误）+ `ui/tabs/log_tab.py`（Log 标签页：顶部 Config Validation 控件 + 全局 `LogViewer`，两者共用同一日志表）。`ConfigLoader` 按文件名排序加载、重复 `node_type` 保留首个并记 ERROR（不再静默覆盖）
- 测试：**两半布局**——纯 Python 套件（`tests/*.py`，`tests/conftest.py` 把 `maya.cmds` 打成 dummy stub）由 CI 运行；Maya 集成套件在 `tests/mayapy/`（真实节点/连接/插件），本地经 `tests/support.py`（`maya.standalone` 初始化、每例新场景、按可用插件加载渲染器）用 `mayapy -m unittest discover -s tests/mayapy -t tests -v` 运行，**不进 CI**。`pytest.ini` 的 `addopts = --ignore=tests/mayapy` 保证纯 pytest 只收集前者；覆盖与运行方式见 `tests/README.md`。CI 为 **Ubuntu + Python 3.11 + PySide6**（不做多平台矩阵），依赖走 `requirements-dev.txt`（运行时仍零依赖）；mayapy 套件启动时打印 `support.describe_environment()`（Maya/Python/OCIO/插件），避免把"大量跳过"误读成"完整验证"；`tests/mayapy/test_perf_baseline.py` 记录 `cmds` 调用次数与耗时作为性能对照基线
- 性能缓存：`BumpConverter.reset_index()` 清空批次索引（`file` 节点列表、bump/normal 节点列表），生命周期 = 一次 `convert_all` 或一次独立 `convert`（由 `MaterialConverter._in_batch` 控制）；`TextureScanner` 在初始化时预编译并排序 alias 表。跨操作长期缓存**禁止**（节点改名/删除/重连会失效）

### 统一导入
所有 UI 模块从 `ui` 包统一导入 PySide 和 Maya 模块，避免重复的 `try/except`：
```python
from ui import QtWidgets, QtCore, QtGui, cmds       # tabs
from ui import QtWidgets, shiboken    # main_window.py
```
PySide 版本探测集中在 `ui/__init__.py` 一处，新增 tab 时只需一行 import。

### 新增渲染器材质
只需在 `config/material/` 目录下添加对应的 JSON 文件，包含 `node_type`、`uiPanel_display_name`、`renderer` 和属性映射。无需修改任何 Python 代码，UI 下拉框和转换逻辑自动支持。若该材质的源属性以 **glossiness**（roughness 的反值）形式存储，需额外配置 `material.invert` 声明条件反转（见 `docs/CONFIG_GUIDE_zh.md`），仍无需改 Python。

### `bumpNormal.json` 统一 Schema
每个渲染器的 bump/normal 段使用**统一字段**（按数据流方向排列）：

| 字段 | 说明 |
|---|---|
| `is_material_attribute` | `false`=独立节点模式（maya/arnold/redshift）；`true`=材质内嵌模式（V-Ray，bump 为材质自身属性） |
| `node_type` | 独立节点模式的节点类型；材质内嵌模式省略 |
| `input` | 接收上游贴图的输入属性（统一后的命名，取代旧 `source_connection`） |
| `output` | 连向下游材质的输出属性（取代旧 `target_connection`） |
| `scale` | 强度属性 |
| `is_normal` / `is_normal_value` | 可选，必须成对；模式开关属性及 normal 模式的取值。`is_normal_value` 可为标量或数组（数组表示多个取值均为 normal 模式）。Maya `bumpInterp`：0=Bump、1=Tangent Space Normals、2=Object Space Normals（normal 段配置 `[1, 2]`）；Redshift `inputType`、V-Ray `bumpMapType`：0=bump / 1=Tangent Space Normal / 2=Object Space Normal（normal 段配置 `[1, 2]`） |
| `normal_space` | 可选 `{空间名: 开关值}` 映射，如 `{"tangent": 1, "object": 2}`。写入时按**源法线空间**取值；源为 object 空间而目标无对应映射时记入结果 `issues`（不静默降级）；未声明表示目标只有切线空间（如 Arnold `aiNormalMap` 无空间开关）。声明的值必须属于该段 `is_normal_value` |
| `file_source` | 贴图节点输出属性（默认 `outColor`） |
| `default_scale` | 构建时设置的默认强度 |
| `path` | 仅 `normal.extra_nodes` 使用：节点**内嵌**贴图路径属性（如旧 `RedshiftNormalMap.tex0`）。非空表示该节点自带路径、没有上游连接，转换时会补建 `file` 节点 |

`common` 段仅作缺失字段的默认值兜底。**新增字段必须接入消费代码**，禁止添加无消费方的键（`ConfigValidator` 会校验属性拼写，但不会校验字段本身是否被消费——接入渲染器时对照上表）。

### `normal.extra_nodes`：共享 normal 模式的额外节点类型

Redshift 有第二个 normal 节点——旧的 `RedshiftNormalMap`（文档称 Normal Map (Legacy)，已弃用）。它把贴图路径**内嵌**在节点属性 `tex0` 上，而不是接收上游连接。`normal` 段可声明 `extra_nodes` 列表补充这类节点：

```json
"normal": {
  "node_type": "RedshiftBumpMap",
  "input": "input",
  "output": "out",
  "scale": "scale",
  "is_normal": "inputType",
  "is_normal_value": [1, 2],
  "file_source": "outColor",
  "extra_nodes": [
    { "node_type": "RedshiftNormalMap", "path": "tex0",
      "output": "outDisplacementVector", "scale": "scale" }
  ]
}
```

- 每个 extra 项是一个独立映射，字段与普通段一致，但用 `path` 取代 `input`（内嵌路径）。
- `file_source` 从合并后的 normal 段继承，**不要**在 extra 项里重复声明。
- 识别为 normal 模式；转换时读取 `path` → 补建 Maya `file` 节点（复用旧节点已连的 `place2dTexture`，否则新建 `p2d_{节点名}`，file 命名 `tex_{节点名}`）→ 以 `file.<file_source>` 作为通用 `input_plug`，**下游转换逻辑不变**。
- 同渲染器复用：按源节点实际类型取 `output` 重连（旧节点用 `outDisplacementVector`）。
- 不搬运旧节点的 `repeats`/`wrap`/`uvSet`/`flipY`/`unbiasedNormalMap`，也不设置色彩空间（normal 贴图需自行用 Colorspace 标签页置 Raw）。
- `path` 为空时不建 file/p2d，按跳过处理（不计失败）；但**关键物化失败**（建 `file`、写 `fileTextureName`、任一 `place2dTexture → file` 连接失败）会记 ERROR 并让整个材质转换计为失败，绝不留下"看似成功但不完整"的法线链路（失败时新建的节点保留在场景）。`_build_file_from_path` / `_collect_embedded_path_node` / `_collect_node` / `_collect` 以 `(data, ok)` 逐层传递失败状态，`convert()` 据此返回失败。

### 已知扩展点：渲染器纹理节点（tex node）
当前构建路径（`MaterialBuilder.make_tex`）固定创建 Maya `file` 节点 + p2d 连接。若未来渲染器的 bump/normal 输入要求使用其自带的 tex node（而非 file）：

- **转换方向（converter）已天然适配**：采集读取上游 `input` plug、`smart_connect` 通用回退（outColor→outAlpha），不依赖 file 节点
- **构建方向需要扩展**：给 bump/normal 段增加可选字段

| 字段 | 缺省 | 说明 |
|---|---|---|
| `texture_node` | `"file"` | 输入源节点类型（如 `RedshiftTexture`） |
| `texture_path_attr` | `"fileTextureName"` | 设置贴图路径的属性名 |
| `texture_use_p2d` | `true` | 渲染器 tex node 通常自带 UV，可设 `false` |
| `texture_out` | `"outColor"` | tex node 的输出属性，供转换回读 |

实施点：`make_tex` 参数化 `node_type`/`path_attr`/`use_p2d`；`alphaIsLuminance` 与 p2d 连接仅对 `file` 节点生效。**状态：未实施**，作为已知扩展点记录；实施后此小节应移除。

## 关键规则

### 代码与注释语言（强制）
**所有 Python 代码一律使用英文**，包括：标识符、字符串字面量、注释、docstring、测试函数名与测试说明、日志/异常/断言消息。
- `.py` 文件中**禁止出现任何中文字符**（含注释与文档串）——新增或修改代码时不得引入中文注释。
- 中文只允许出现在**面向用户的中文文档**中：`docs/*_zh.md`、`CHANGELOG_zh.md`、`docs/AGENTS.md`（本文件）以及 `README.md` 的中文链接文字。
- 提交前自检：`git grep -nP '[\x{4e00}-\x{9fff}]' -- '*.py'` 必须无输出。
- `scripts/check_no_silent_pass.py` 目前不检查语言，这条规则靠人工/上面的 grep 保证；若将来加自动化，请在 CI 中一并执行。

### 日志规则
- 所有 `except` 必须使用 `as exc` 并写入 logger（至少 WARN）；禁止 `except: pass`、静默 early return、静默 fallback。`scripts/check_no_silent_pass.py` 以 **AST 结构检查**强制这一点：每个 `except` 块必须记录日志、`raise`、调用 `report_terminal`，或带显式 `# noqa: silent-fallback <原因>` 标记（仅用于连 stderr 都不可用的场景，如 `report_terminal` 自身）；`print` / `cmds.warning` 同样按 AST 检测。
- 反馈链防护（`ui/feedback.py`）：日志/弹窗/横幅等反馈环节自身失败时不得掩盖原始异常——logger 失败回退 `_report_terminal`（stderr，永不假设 logger 可靠），弹窗失败记录 WARN（此时 logger 未失败，假设成立）；反馈永远不能改变业务控制流，`raise` 必须始终执行。
- core 业务代码禁止直接 `print()` 和 `cmds.warning()`，统一写入 `core.logger.get_logger()`。
- UI 日志只通过 `ui/log_panel.py` 的 `LogViewer.drain()` 单消费者拉取；Log 标签页隐藏时暂停拉取，切回时一次性补拉（必要时整体重同步）。
- 默认可见级别为 ERROR/WARN/SKIP/INFO；属性级细节用 DEBUG（默认隐藏，用户可勾选）。
- Logger 与 UI `LogModel` 共用 `DEFAULT_MAX_RECORDS`（20,000），两侧都必须有界；UI 通过 drain 返回的 `evicted_seqs` 同步移除 Logger 已淘汰的行，保持两侧内容一致。
- `Logger.scope(source=...)` 是词法作用域：显式 source 覆盖外层，空 source 继承外层，单条日志的 `source=` 优先级最高；退出 scope 后恢复。
- 需要右键选节点的日志，必须在写入时通过 `nodes=` 传入节点；UI 只读取 `record.nodes`，禁止解析 `message` 提取节点。`Logger` 只对节点做清洗去重（`None` 项忽略），不拆分 plug；plug 转节点名使用 `core.node_utils.node_name_from_plug()`。`nodes=` 快照有上限 `core.logger.MAX_NODES`（50），超出部分折叠为 `...(+N more)`，禁止把整个选择集原样写进环形缓冲。
- 日志节点是一次性快照，不保证时效性。右键选择直接执行 `cmds.select`，不做存在性判断。
- 高频循环连接（如 p2d → file）应在循环内使用 `BuilderContext.connect(..., quiet=True)` 静默逐条成功 DEBUG，循环后只发一条带 `nodes` 的汇总 DEBUG；`quiet` 只静默成功路径，失败仍必须写带 `nodes` 的 ERROR。
- 性能优先：日志只追加到环形缓冲，批量转换/构建期间每 5 个材质（且必定包含最后一个）才 `processEvents()` 一次。

### 材质 JSON 必须包含 `uiPanel_display_name` 和 `renderer`
每个材质 JSON 的 `material` 块中必须包含这两个字段：
```json
{
  "material": {
    "node_type": "RedshiftStandardMaterial",
    "uiPanel_display_name": "Redshift Standard Material",
    "renderer": "redshift",
    ...
  }
}
```
`uiPanel_display_name` 用于 UI 下拉框显示名称，`renderer` 用于转换逻辑识别渲染器归属（取值 `"arnold"` / `"redshift"` / `"vray"`）。

### 节点创建
**必须使用 `cmds.shadingNode(asShader=True)` 或 `shadingNode(asUtility=True)`。**  
禁止使用 `cmds.createNode()` — 它不会注册到 Hypershade，会导致"转换成功但 Hypershade 里看不到"的 bug。

### JSON node_type 必须与 Maya 精确一致
Maya 节点类型名区分大小写。添加前必须验证：
```python
n = cmds.createNode("RedshiftOpenPBRMaterial")  # 测试确切的类型名（验证后删除）
```
如果 Maya 警告 "Unrecognized node type"，说明 JSON 中的 key 写错了。

### `displacementShader` 哨兵值
在置换 JSON 配置中，`node_type: "displacementShader"` **不是真正的节点类型名**。它表示"将纹理直接连接到 `SG.displacementShader`"。真正需要创建节点的类型（如 `RedshiftDisplacement`）才会触发节点创建。

> 注：`core/config_validator.py` 的 Debug 校验不受此语义影响——它会直接创建 `displacementShader` 节点并实际校验其属性（`scale`/`displacement` 等）。

### 旧节点永不删除
转换后的材质、凹凸、CC 和置换节点**保留在场景中**，只是从 shadingEngine 上断开连接。不要添加删除逻辑。

### 属性传递循环中跳过的属性
`normal_bump`、`displacementScale`、`displacementTexture` 由专门的转换模块处理，主属性循环会跳过它们。永远不要从跳过列表中移除这些属性。

### `renderer_map` 命名约定
```python
renderer_map = {"arnold": "ai", "redshift": "rs", "vray": "vray"}  # 仅在需要缩写时使用
renderer_short = renderer_map.get(target_renderer, target_renderer)  # 回退为原名
```

### Debug 验证忽略未安装渲染器
`core/config_validator.py` 检测插件加载状态（`pluginInfo(loaded)`，未加载则 `loadPlugin` 自动加载）；当插件加载失败（未安装/不兼容）时，将**整组渲染器标记为 SKIP 并跳过**，绝不产生 ERROR/WARN，避免没有对应渲染器（如未装 V-Ray/Redshift）的用户看到一堆误报。SKIP 计入 summary 的 skip 数，不计入失败数。

## 开发工作流

1. 直接在 `C:\opencode\materialConvert\` 下编辑代码
2. 在 Maya Script Editor 中重新 `exec()` 加载
3. 如果模块缓存问题持续存在，关闭窗口后重新运行
4. 运行纯 Python 测试（无需 Maya）：`python -m pytest tests/ -v`
5. 运行 Maya 集成测试（本地，需 Maya，不进 CI）：`mayapy -m unittest discover -s tests/mayapy -t tests -v`（覆盖真实节点/连接/插件；见 `tests/README.md`）
6. 提交后由 GitHub Actions（`.github/workflows/test.yml`，Ubuntu / Python 3.11 / PySide6）自动跑 `pytest` 与守卫脚本，本地验证命令与 CI 一致

## 常见陷阱

| 症状 | 根因 |
|---|---|
| 转换没有任何反应 | JSON 的 `node_type` 与 Maya 实际节点类型名不匹配 |
| 新节点在 Hypershade 中不可见 | 使用了 `cmds.createNode` 而非 `cmds.shadingNode` |
| CC 节点检测不到 | CC 前面有中间节点 — 使用 `listHistory` 搜索，而非直连检查 |
| 凹凸和法线混淆 | 共享类型节点（`bump2d` / `RedshiftBumpMap`）需要检查 `inputType`/`bumpInterp`；法线空间靠 `normal_space` 传递 |
| V-Ray 凹凸类型属性设置失败 | 属性名是 `bumpMapType`，不是 `bumpType` |
| `outAlpha` → `input` 连接失败 | 类型不兼容：float → color。使用 `smart_connect` 回退到 `outColor` |
| float3 值设置到 float 属性报错 | 源属性为颜色（float3）但目标为标量（float）— 已自动回退取第一个通道 |
| float 值设置到 float3 属性报错 | 目标属性为颜色（float3）但源为标量（float）— 已自动广播为 (v,v,v) |
| 转换后源材质的 layeredTexture 被目标渲染器节点驱动 | 共享中间节点被改写 — 现在改为**复制中间节点**并只把副本接给目标材质；两级以上链路显式记 `issues` 不转换 |
| 转换失败后场景一半新一半旧 | 提交已事务化：SG 接线快照不可读时**在改接前中止**（`reason` + `sg_failures`，计入 `unwired`，场景零改动）；快照完整时任一 SG 接线失败只回滚**本次实际改写过的** SG（从未被改写的 SG 不会被误恢复）并在 `result.restored`/`sg_failures`/`wired_before_rollback` 中说明（锁定插槽无法恢复时记 ERROR） |
| 批处理中重复点击产生两次构建 | 已由 `OperationGuard` 拒绝重入并禁用提交控件；Maya 场景命令仍在主线程 |
| Redshift hue=0 转 Arnold 得到 -1 | 各渲染器 hue 中性点语义不同 — 已按 `hue_center` 偏移角换算（Arnold `hueShift=0`） |
| 材质转换后消失 | ShadingEngine 未重新绑定。检查 SG 替换逻辑 |
