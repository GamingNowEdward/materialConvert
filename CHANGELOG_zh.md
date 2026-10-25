# 更新日志

## 2026-10-25

### 修复（静默正确性，P0）
- **Builder 完整链的 ramp 是死的**：`_build_scalar_chain` 建出裸 `ramp` 却没有 `colorEntryList`，输出恒定、贴图驱动 `vCoord` 无效，却仍报成功。现由 `MaterialBuilder._configure_ramp()` 写入配置的停靠点（`builder_naming.json` → `ramp_stops`，缺省黑→白），且 ramp→材质改用 `smart_connect`，目标非 float 时回退到 ramp 的 `outColor`
- **CC 直连 + 非材质下游时目标通道未接线**：`cc.py` 只在 `else` 分支连 `target_plug`，于是"CC 同时驱动非材质节点"的场景产出的材质通道为空却报 `converted=True`。现目标通道**始终**单独接线，`_external_cc_destinations` 将其排除
- **Full chain 开关覆盖哪些通道不明确**：`_build_scalar_chain` 的 `use_full_chain` 改为**必填**（将来漏传会在调用点报错），且**只作用于 `specularRoughness`**——`metallic` / `opacity` 显式传 `False` 保持直连，因为经 ramp 只是插入一个无意义的恒等重映射节点（opacity 在多个渲染器上还是 color 属性）
- **ramp 配置失败现在进入构建结果**：`_configure_ramp()` 返回失败清单（`ramp_stops` 无效/缺失、停靠点写入失败），`_build_scalar_chain` 将其记入 `last_build_issues`，构建结果计为 `with_issues`（批次 WARN + 警告横幅），不再出现"报成功但 ramp 输出不符配置"的静默失真

### 修复（结果语义与事务）
- **`summary["unwired"]` 恒为 0**：`summarize_results` 先把接线失败归入普通失败，永远到不了 `unwired` 分支，且 `unwired` 未要求真的提交失败。现 `unwired = total_sgs > 0 and wired == 0 and bool(sg_failures)` 并**优先**判定
- **回滚误报**：`_restore_sg_wiring` 会恢复快照里的**每一个** SG，导致"从未被改写（其接线本就失败）"的 SG 在锁定插槽上恢复失败、误置 `restored=False`。现只恢复本次提交**实际改写**过的 SG
- **部分接线诊断被丢弃**：`ConversionResult.wired_before_rollback` 记录回滚前已接线的 SG 数，批次日志与转换页会报告它；`docs/AGENTS.md` 明确"部分接线按铁律 11 回滚、`partially_wired` 为保留能力"
- **`disconnectAttr` 误用**：`_restore_sg_wiring` 只传一个参数（Maya 会抛错），`_disconnect_upstream` 传反了 `(dest, src)`。现统一为 `(source, destination)`；`tests/test_converter.py` / `tests/test_cc_topology.py` 的 fake 签名同步改为真实 API
- **CC 驱动标量通道必然失败**：`cc.py` 一律用配置输出（`outColor`，float3）。现优先使用源链实际使用的输出插槽（`outAlpha`），并经 `smart_connect` 回退；`_cache` 记录该插槽
- **`last_build_issues` 跨材质串味**：重置点提到 `_build()` 第一行（任何 `raise` 之前）
- **SG 快照不完整不再有"半接线"风险**：`_snapshot_sg_wiring()` 返回 `(snapshot, unreadable)`，任一槽读取失败时 `_commit_shading_engines` **在改接前中止**（`reason = "failed to snapshot shading engine wiring"`、不可读槽记入 `sg_failures`、场景零改动、结果计入 `unwired`）；同时删除已不可达的 `_UNKNOWN_WIRING` 哨兵及其回滚分支

### 修复（上报、配置、UI、启动）
- **`NaN` 被静默写入**：非有限浮点值被拒写并记为 `issue`
- **`TransferReport.ok` 恒为 True**：`transfer_all` 返回前 `ok = not critical`
- **非 opacity 通道开启 Alpha Is Luminance 不可见**：现在会记一条 `issue`
- **删除无消费方的配置键**：`texture_channels.json:use_alpha` 与 `colorSpace.json:default` 从未被读取，直接删除而非保留成"假旋钮"
- **`ssOn` 硬编码**：搬进 `VRayMtl.json` 的 `material.builder_prerequisites`，由 builder 经 `apply_prerequisite_dict()` 消费
- **V-Ray SSS 实际并未开启**：Builder 从未设置过 `translucencyMode`，而 `VRayMtl` 上并不存在 `ssOn`。真实属性 `sssOn` 按其 AE 标签是 **Legacy SSS** 开关（默认状态下该控件被隐藏），**不是**通用 SSS 总开关——置 1 会隐藏/忽略 `translucencyAmount`。现 `builder_prerequisites.subsurfaceColor` 启用**新版** SSS（`translucencyMode = 6`），与 Convert 路径一致；`sssOn` 保持默认关闭。builder prerequisite 改为**按通道**查表（去掉硬编码的 `subsurfaceColor` 分支）
- **删除 `MatchResult.stale`；`evidence_complete` 接入 UI**：Colorspace 诊断列追加 `[channel evidence incomplete]`
- **整套贴图共用"通道词后缀"时 Batch Builder 全部判错**：若一套贴图每个文件都以 `_METALNESS` 结尾，会被整体判成 metallic，且每个文件被拆成独立材质。`TextureScanner` 现在统计每个**别名 token** 出现在多少个文件里：在 ≥3 个贴图文件的目录中，被 ≥60% 文件共有的别名 token 视为**整套共有后缀**——匹配时忽略、并从材质名中剔除；同时支持粘在通道词后的数字/分辨率（`nrm16`→`nrm`、`rough4k`→`rough`）。若忽略共有 token 后没有任何文件能解析出通道（如只放 `*_METALNESS.png` 的单通道目录），整目录回退到原始行为；只有别名 token 参与该判定，资源名永不被剥离
- **重复通道原先只按文件名字典序取第一个**：现改为**位深/分辨率高者优先**（`NRM16` 胜 `NRM`、`nrm4k` 胜 `nrm`；独立 token 或粘在通道词后均可，且只做相对比较，整套共有的数字会抵消），平手时才回退到名字序第一个；`_record_conflict()` 始终重算 `dropped = candidates − kept`，UI 展示与最终采用者一致
- **Batch Builder 表格把所有异常都涂成同一种红**：现按严重度分色——`CONFLICT (kept)` 琥珀色（被采用的那个文件）、被丢弃的重复文件保持红色、`UNPARSED` 灰蓝色，并在表格下方加一行图例说明三种状态
- **Colorspace 对整套贴图误报冲突**：Name Driver 把整套共有的 `_METALNESS` 当作每个文件的证据，于是 `COL`/`SSS` 文件与 channel 证据冲突（raw vs srgb）而停在 `CONFLICT`。现 `ColorSpaceMatcher.scan()` 按**文件所在目录**分组，用共用的 `TextureScanner.shared_keywords()` 规则求出被 ≥60%（且该目录 ≥3 个 file 节点）文件共有的关键词，并通过 `NameDriver.match(..., ignore_keywords=...)` 忽略它们；若过滤后**没有任何节点**得到文件名证据（如目录里只有 metallic 贴图），则整场景重跑一次不过滤（兜底）
- **文件名匹配改为单一实现**：`core/filename_match.py` 集中 `normalize_stem` / `find_alias` / `quality_key` / `shared_keywords` 与 `ChannelMatcher`（返回一个名字命中的**全部**通道，最长别名优先）；Batch Builder 扫描器只保留扫描职责，`NameDriver` 把命中的通道按 `texture_channels.json` 的 `type` 映射为 colorspace role（`color`→`srgb`、数据类→`raw`）并对 role 去重——同 role 多通道是一个结论，不同 role 保留 `AMBIGUOUS`。短别名（`col`/`sss`/`nrm`/`disp`/`mask`…）现在也提供文件名证据，但仍只按完整 token 匹配（`school` 不会命中 `col`）。`ConfigLoader.get_filename_role_keywords()` 由 `get_texture_channels()` 取代
- **`del exc` 吞掉横幅失败**：`show_warning_banner` / `show_result_banner` 失败回落到 `report_terminal`（stderr），失败可观测
- **Log 页校验无防护**：改用 `set_enabled`（窗口销毁不再抛 `RuntimeError`），忙状态提升为**窗口级**、覆盖全部 6 个页
- **`nodes=` 快照无上限**：`_normalize_nodes` 对已规范化元组短路，并以 `MAX_NODES`（50）截断、追加 `...(+N more)`
- **`_evict_for` 退化为 O(n²)**：新增扫描游标，不再重走已知 critical 记录
- **启动提示被 traceback 淹没**：`main.py` 解析不到项目根时不再 import `ui.main_window`
- **符号链接根目录识别失败**：模块归属判定改用 `os.path.realpath`
- **置换 / 配置 / bump 清理**：`DisplacementConverter.convert()` 注明为非事务便捷入口；`attr_map` 不再吸收 `displacement` 段的元键；`_collect` 对共享 bump/normal 节点只采集一次；删除不可达的 `_detect_bn_modes` path 分支；嵌套转换记 WARN；材质输出属性可配置（`material.output`，缺省 `outColor`）；`_restore_shared_source_chain` 限定只查下游；`_TRACE_SKIP_NODES` 改为按类型匹配纹理源节点；`_record_conflict` 删除语义模糊的 `new`；`_StateItem.__lt__` 与状态查表加防护；Colorspace 表格限制 `MAX_TABLE_ROWS`；`colorSpace.json:commonAttributeRoles` 不再重复渲染器属性名

### 变更（守卫脚本）
- `scripts/check_no_silent_pass.py` 升级为 **AST 结构检查**：每个 `except` 处理块必须记录日志、`raise`、调用 `report_terminal`，或带显式 `# noqa: silent-fallback <原因>` 标记；`print` / `cmds.warning` 也改为 AST 检测

### 测试
- 纯套件：**337 passed**（原 289）。新增：CC 拓扑、ramp 与完整链、ramp 配置失败、提交语义、快照中止、builder prerequisite、V-Ray SSS 开关、共享文件名匹配、整套共有 token、重复通道优先规则、Batch Builder 表格分色、colorspace 整套共有关键词、节点上限、淘汰、横幅回落
- mayapy 套件：**92 passed, 3 skipped**（原 88）。新增：目标侧 CC 断言、outAlpha 标量通道、ramp 随 `vCoord` 响应、full chain 只作用于 roughness、V-Ray SSS 开关

### 已知限制与后续项
- **Full chain 的适用范围**：`Full chain` 开关**只作用于 `specularRoughness`**；`metallic` / `opacity` 恒为直连（有意为之）
- **CC 驱动标量通道**：若**目标**渲染器的 CC 节点没有 `outAlpha`（如 `RedshiftColorCorrection`），该通道无法表示，转换仍会关键失败
- **`partially_wired`** 为保留的模型能力：因 SG 提交失败即回滚（铁律 11），`wired` 只会是 `0` 或 `total_sgs`；回滚前的成功接线数由 `wired_before_rollback` 上报
- **符号链接根目录**（`os.path.realpath` 处理）未在本机实测（Windows 创建符号链接需要特权）
- **仅 GUI 路径**（跨页重入、窗口销毁、超大 Colorspace 表格）由代码路径分析 + 单元测试覆盖，未做端到端 GUI 运行
- **`nodes=` 内存数据**来自 `tracemalloc`（纯 Python），非真实 Maya 场景占用

## 2026-10-18

### 修复（可靠性：成功判定可信）
- **置换失败被当成成功**：`core/converters/displacement.py` 的 `_create_node` 在贴图连接失败/强度写入失败后只记 WARN 仍返回节点。现拆为 `prepare()`（建节点 + 校验输出 + 写强度，不改 SG）与 `apply()`（提交 SG），返回 `TransferOutcome`：建节点、贴图接入、输出缺失、源数据读取失败为**关键失败**，强度写入失败为 `issues`；"无源置换"与"读取失败"不再混为一谈
- **Builder 丢弃前置条件失败**：`apply_prerequisites()` 现返回 `PrerequisiteOutcome(ok, failures)`（`__bool__` 兼容旧调用），`MaterialBuilder._build()` 在失败时把具体失败项写入 `last_build_issues` 后抛 `RuntimeError`，`BatchBuilder` 把它们记入 `BuildResult.failures`，不再产生 `built=True` 且无告警的结果
- **Legacy Normal 的 P2D 失败未上报**：`_create_place2d` 失败现为关键失败（不再跳过 UV 接线后返回成功）；物化出的 `file` 节点打 `mcEmbeddedSource` 标记，复用前三路判定（标记匹配 + UV 链完整 / 标记匹配但可修补 / 无标记时要求名称+路径+UV 完整），同名同路径但无 UV 链的手工节点不再被复用
- **部分 SG 接线不出现在横幅**：`show_result_banner()` 新增 `partial` 参数，`failed > partial > with_issues > success`；转换页传入 `summary["partial_wired"]`
- **Alpha Is Luminance 判断刷屏并占用日志缓冲**：`_fix_alpha_luminance` 对每个映射属性各记一条 `No alpha source traced for <plug>` DEBUG，单个材质可达 ~30 条（同一目标插槽还会因多个通用属性重复追踪）。现按目标 plug 去重，逐属性提示改为每个材质一条汇总 DEBUG（`no alpha source on N checked plug(s)`），只在真正找到 alpha 源时才记 `Alpha source found` / `Enabled Alpha Is Luminance`（启用列表同样去重）

### 修复（场景一致性）
- **置换先提交、surface 后提交**：`core/converter.py` 改为事务提交——先 `_snapshot_sg_wiring()` 快照每个 SG 的 surface/displacement 上游，再依次提交；任一失败即 `_restore_sg_wiring()` 回滚已改写连接，`result.restored` / `result.sg_failures` 记录恢复情况，`converted` 保持 False。快照读取失败记 `_UNKNOWN_WIRING`，回滚时不猜测（记 ERROR），未提交过的插槽不会被误断开
- **共享 CC 链绕过中间节点**：`core/converters/cc.py` 按拓扑分流——`direct`（CC 直连材质）保留原有共享恢复逻辑；`single_hop`（CC → layeredTexture/ramp → 材质）**复制中间节点**、新 CC 接副本、副本输出接目标材质，源网络零改写；`unsupported`（多级链）不创建节点、不触碰源连接，记入结果 `unsupported/issues`。移除了 `attribute.py` 中把中间节点输出直连目标材质的分支
- **UI 批处理可重入**：新增 `ui/operation_state.py:OperationGuard`（Qt-free），三个操作页在入口拒绝重入并在 `finally` 解锁；`ui/main_window.py:_set_busy()` 通过 `ui/widgets.py:set_enabled()` 禁用提交控件；`processEvents` 回调对已销毁窗口的访问降级为 DEBUG

### 新增（语义与交互）
- **法线空间保留**：`config/bumpNormal.json` 的 maya/redshift/vray `normal` 段新增 `normal_space`（`{"tangent": 1, "object": 2}`），`NodeMapping` 新增 `supported_spaces` / `space_for_value()` / `mode_value_for_space()`；采集侧携带 `normal_space`，写入侧按源空间取值，目标无法表达时记 `issues` 而不是写入默认值。`bump.py` / `reuse_existing()` 统一返回 `TransferOutcome`
- **贴图冲突可见**：`TextureScanner` 冲突记录新增 `kept` / `candidates` / `dropped`，结果新增 `conflict_materials`；Batch Builder 表格新增 `CONFLICT` / `CONFLICT (kept)` 行与 `Skip Materials With Conflicts` 开关，Materials to Build 列表标注冲突数
- **启动不再依赖 `__file__`**：`main.py` 新增 `_resolve_root()`——校验 `__file__` 目录确属本项目，否则从 `sys.path` 解析；两者都失败时仅写 stderr 并跳过接管，不再静默使用错误根
- **颜色空间证据完整性**：`ChannelDriver.trace_channel_targets()` 返回 `TraceResult`（`complete`/`truncated`/`depth_limited`/`errors`），`MatchResult` 新增 `evidence_complete`；仅有 channel 证据且不完整时降级为 `AMBIGUOUS`；`apply_matched(..., revalidate=True)` 应用前重新匹配，过期建议计入 `stale` 且不写入；NameDriver 改用与 Scanner 共用的 token/边界匹配

### 新增（工程化与性能）
- **统一通道结果**：`core/results.py` 新增 `TransferOutcome`（`ok`/`issues`/`critical`/`unsupported`），`TransferReport` 继承它；`ConversionResult` 新增 `sg_failures`/`restored`，`BuildResult` 新增 `failures`
- **离线配置结构校验**：新增 `core/config_schema.py`（纯 Python）校验必需字段/类型、重复 `node_type`、段结构、`prerequisites`/`invert`、`is_normal`/`is_normal_value` 成对、`normal_space` 值域、`extra_nodes`、跨配置引用与 `builder_naming` 数组长度；`ConfigValidator.validate_all()` 先跑离线校验再进 Maya；`ConfigLoader` 按文件名排序加载、重复 `node_type` 保留首个并记 ERROR，`MaterialConfig` 对非对象段记 ERROR 后跳过
- **批次级场景索引**：`BumpConverter.reset_index()` 管理 `file` / bump-normal 节点索引（生命周期 = 一次批次或一次独立转换，由 `MaterialConverter._in_batch` 控制），`_find_bn_node` / `_find_existing_embedded_file` 不再反复全场景 `cmds.ls()`；`TextureScanner` 初始化时预编译并排序 alias 表
- **测试矩阵**：CI 保持 Ubuntu + Python 3.11 + PySide6（单平台，不做多平台矩阵），依赖改用 `requirements-dev.txt`；mayapy 套件启动打印 `support.describe_environment()`；新增 `tests/mayapy/test_perf_baseline.py` 记录 cmds 调用次数与耗时

### 测试
- 纯套件新增：`test_displacement_converter.py`（置换 6 类失败）、`test_bump_legacy.py`（P2D 关键失败与复用判定矩阵）、`test_bump_converter.py`（object/tangent 空间传递）、`test_cc_topology.py`（direct/single_hop/unsupported）、`test_busy_guard.py`、`test_config_schema.py`（含损坏配置）、`test_main_entry.py`（4 种启动场景）；`test_converter.py` 新增提交/回滚、`test_conversion_results.py`/`test_feedback.py`/`test_material_builder.py`/`test_batch_builder.py`/`test_colorspace.py`/`test_texture_scanner.py`/`test_config_loader.py` 扩充对应断言。纯套件 **285 passed**
- mayapy 新增/扩展：置换失败注入、Legacy P2D 失败/修补/手工同名、法线空间保留与 Arnold 上报、共享 layeredTexture 复制、多级链上报、场景保存重开后的接线断言、性能基线。mayapy 套件 **88 passed, 3 skipped**（Maya 2024 + mtoa/redshift4maya/vrayformaya/lookdevKit）

### 文档
- `docs/AGENTS.md`：启动契约、CC 拓扑分流、事务提交、结果模型语义、法线空间 schema、颜色空间证据完整性、离线配置校验、操作状态、性能缓存生命周期、CI 运行方式
- `docs/CONVERSION_SPEC.md` / `_zh`：3.6 连接链保留改写为 direct/single_hop/unsupported 三态与复制策略
- `docs/CONFIG_GUIDE.md` / `_zh`：`bumpNormal.json` schema 新增 `normal_space` 行
- `README.md` / `docs/README_zh.md`：启动说明、法线空间与事务提交、Batch Builder 冲突列与跳过开关、Colorspace 证据完整性/复核
- `tests/README.md`：CI 运行平台、环境行、新增测试文件、手动 UI 验证清单

## 2026-10-16

### 新增
- **兼容 Redshift 旧 Normal Map 节点（`RedshiftNormalMap`）**：Redshift 除 `RedshiftBumpMap` 外还有一个已弃用的 `RedshiftNormalMap`（贴图路径内嵌在 `tex0`，输出为 `outDisplacementVector`）。`config/bumpNormal.json` 的 `redshift.normal` 新增 `extra_nodes` 声明该节点；`core/config_loader.py` 新增 `NodeMapping.path`、`BumpNormalConfig.normal_extras`，`get_all_bn_types()` / `find_bn_renderer()` 纳入该类型
- 转换采集（`core/converters/bump.py`）：带内嵌路径的节点读取 `path` → 复用旧节点已连的 `place2dTexture`（无则新建 `p2d_{节点名}`）→ 补建 `file` 节点（`tex_{节点名}`）→ 以 `file.<file_source>` 作为通用 `input_plug`，**下游 `_do_convert` / `_convert_to_node` / `_convert_to_material` 不变**；`file_source` 从合并后的 normal 段继承，`tex0` 为空时按跳过处理；重复采集/重复转换复用同名且路径一致的 file
- 同渲染器复用（`reuse_existing`）：按源节点实际类型取 `output` 重连（旧节点用 `outDisplacementVector`），标准/共享类型行为不变
- P2D 连接定义（`P2D_ATTRS` / `P2D_CONNECTIONS`）下沉到 `core/node_utils.py` 作为单一来源，`MaterialBuilder.make_tex` 与 bump 转换器共用；Builder 仍保留 `ctx.connect(quiet=True)` 的失败抛出语义
- 配置校验（`core/config_validator.py`）：遍历 `normal.extra_nodes`，用临时节点校验 `node_type` / `path` / `output` / `scale`，`file_source` 复用现有 file 节点校验分支

### 修复
- **legacy 贴图物化失败被静默当作成功/跳过**：`core/converters/bump.py` 的 `_build_file_from_path` 在 `fileTextureName` 写入失败、或任一 `place2dTexture → file` 连接失败时只记 WARN 仍返回节点，目标材质会拿到不完整的法线链路而转换仍报成功。现改为关键失败返回 `(None, False)`：`_collect_embedded_path_node` / `_collect_node` / `_collect` 逐层传递 `ok`，`convert()` 收到失败即记 ERROR 并返回 False（计为失败）；失败时新建的 file/p2d 节点保留在场景（不删除）

### 测试
- `tests/test_config_loader.py` 新增 `extra_nodes` 解析、`file_source` 继承、缺 `node_type` 健壮性用例
- `tests/mayapy/test_conversion_bump_normal_live.py` 新增 legacy 用例：转 Arnold、转 V-Ray、P2D 复用/新建、空路径 skip、同渲染器重连、重复转换不重复建 file、物化失败计失败、p2d 连接失败计失败

### 文档
- `docs/AGENTS.md` / `docs/CONFIG_GUIDE_zh.md` / `docs/CONFIG_GUIDE.md`：bumpNormal schema 新增 `path` 字段与 `normal.extra_nodes` 说明（含不搬运属性与色彩空间限制）
- `docs/CONVERSION_SPEC_zh.md` / `docs/CONVERSION_SPEC.md`：新增 2.7 Redshift 旧 Normal Map 兼容小节

## 2026-10-06

### 修复
- **`alphaIsLuminance` 自动追踪可能跨材质网络串到错误贴图**：`core/converters/attribute.py:_trace_alpha_plug` 的 `cmds.listConnections(start, plugs=True, source=True)` 漏了 `destination=False`，按节点名递归时会把 `*.message` / `defaultRenderUtilityList` 等注册表连线以及下游连线也当成上游，追踪会跳到无关材质并把 `alphaIsLuminance` 开在错误的 file 上（新增 `reverse` 反相节点后更易触发）。补上 `destination=False` 后只沿真正上游遍历
- **Builder 构建的 V-Ray 法线材质实际是 bump**：`core/material_builder.py:_build_bump_normal` 的材质内嵌分支漏设模式属性（`bumpMapType`），导致 `channel_options={"normal_bump": {"mode": "normal"}}` 构建 V-Ray 时仍为 bump（值 0）。补齐后与节点分支一致
- **ShadingEngine 枚举失败被静默当作「浮动材质」成功**：`core/converter.py:_find_shading_engines` 在 `cmds.listConnections` 抛异常时返回 `[]`，与「真的没有 SG」不可区分 → `total_sgs=0`、`unwired` 恒为 False、`summarize_results` 计入 converted，而场景实际仍使用旧材质（位移也被静默跳过）。现改为枚举在**创建目标材质之前**进行，失败即记 ERROR、设 `reason` 并**中止转换**（`created`/`converted` 均为 False → 计入 failed）
- **通道级内部失败被静默当作成功**：`cc.transfer` 无返回值、`_transfer_one` 的 CC 分支无条件 `return True`、`bump`/`displacement` 连接失败仅记 WARN 仍写 "converted"、`apply_prerequisites` 失败被忽略。现按严重程度分流：**关键失败**（前置条件、CC 链、bump/normal、displacement）→ 设 `reason`、`converted=False`（计为失败并中止）；**非关键通道失败**（单个属性 / emission / alphaIsLuminance / reverse）→ 记入新增的 `ConversionResult.issues`（`converted` 仍 True，汇总计入 `with_issues` 并输出 WARN）；Builder 单通道失败记入 `BuildResult.issues`
- **Redshift / V-Ray 的 Object-Space Normal 被误判为 bump**：`config/bumpNormal.json` 的 `redshift.normal.is_normal_value` 与 `vray.normal.is_normal_value` 由 `1` 改为 `[1, 2]`（对齐 Maya `bumpInterp`，`inputType`/`bumpMapType` = 2 才是物体法线）；Builder 回写仍取首值 1（切线法线）。文档 `CONFIG_GUIDE*.md` / `docs/AGENTS.md` / `CONVERSION_SPEC*.md` 同步修正（此前自相矛盾）
- **`get_materials_from_selection` 材质识别过宽**：原用 `outColor` 存在性判定，把 `file` / `layeredTexture` / `ramp` 也当材质（选中后转换必得 "unknown source material type"）。改用 `cmds.ls(selection, materials=True)`，保留 shape→SG 回退
- **非 V-Ray 源转 VRayMtl 时 `translucencyMode` 没开，SSS 参数无效**：`config/material/VRayMtl.json` 的 `subsurface` 段新增属性级 prerequisite —— 处理 `subsurfaceWeight` 时先设 `translucencyMode = 6`（SSS），否则 `translucencyAmount` / `translucencyColor` 传了也不生效（与已有 `useRoughness` 同类遗漏）。源权重为 0 时 `translucencyAmount` 传 0，视觉无变化
- **Material Builder 手动构建没有 undo chunk**：`core/material_builder.py` 的 `build()` 现在内部包裹 `undoInfo` open/close（实际实现在 `_build()`），单次构建可**一步撤销**；`BatchBuilder` 已有的外层 chunk 与内层嵌套合并，批量仍为一步
- **启动时配置 JSON 损坏直接抛异常、窗口不出现**：`ui/main_window.py:show()` 捕获 `MainWindow()` 构造异常 → `log.error` + best-effort 错误对话框，随后**重新抛出**（不吞异常）
- **属性传递失败路径的日志级别与结果不一致**：目标插槽缺失 / 不支持值类型由 `SKIP` 升为 `WARN`（因为它们会记入 `issues`），并在 `transfer_all` 末尾汇总一条带 `nodes` 的 WARN 列出 issues / critical
- **mayapy 转换矩阵对缺失目标属性静默 `continue`**：`test_conversion_matrix_live.py` 改为断言目标插槽存在（缺失即测试失败），不再跳过

### 测试
- `tests/test_attribute_converter.py` 新增 `test_trace_alpha_plug_follows_only_upstream`：构造「source=True-only 会串到 otherFile」的假图，断言只沿上游解析到 `realFile`

### 测试（新增 mayapy 集成套件）
- 新增 Maya 集成测试骨架：`pytest.ini`（`--ignore=tests/mayapy`，纯套件仍进 CI）、`tests/support.py`（`maya.standalone` 初始化、每例新场景、按可用插件加载渲染器、建材质/取值辅助、材质对数据驱动）、`tests/mayapy/__init__.py`、`tests/README.md`
- 首批 mayapy 用例（本地 `mayapy -m unittest discover -s tests/mayapy -t tests -v`）：`test_config_validator_live.py`（真实节点 `validate_all` **0 ERROR/0 WARN**，含 `invert`）、`test_node_utils_live.py`（identify/create/CC/collect/selection）、`test_conversion_matrix_live.py`（**全部可用材质交叉转换** × 每个通用属性映射）
- 渲染器插件缺失时按**通用规则**过滤（非 Redshift 专属），装上后矩阵自动扩展；mayapy 套件不进 CI
- 第二批 mayapy 用例：`test_cc_conversion_live.py`（CC 链转换/复用/源链还原）、`test_conversion_texture_live.py`（贴图驱动连接 + `reverse` 接线）、`test_conversion_complex_live.py`（Builder 复杂链转换）、`test_conversion_bump_normal_live.py`（bump/normal 双向跨渲染器）、`test_conversion_special_live.py`（glossiness 反转/黑归零/V-Ray emission/同渲染器复用）、`test_conversion_alpha_luminance_live.py`（开启/豁免/跨网络回归）、`test_conversion_displacement_live.py`（哨兵 no-op；真实节点待 Redshift）、`test_converter_flow_live.py`（结果语义/批次/进度/失败隔离）
- 第三批 mayapy 用例：`test_prerequisites_live.py`、`test_builder_context_live.py`、`test_material_builder_live.py`（全通道 × 渲染器、full/simple、QSS、prereq）、`test_batch_builder_live.py`、`test_colorspace_live.py`（随 OCIO 配置的通用断言）、`test_node_tools_live.py`、`test_scene_roundtrip_live.py`
- `pytest.ini` 不再被 `.gitignore` 忽略并纳入版本控制，CI 只收集纯套件（此前会额外收集 `tests/mayapy` 的跳过用例）；`MaterialBuilder.build` 新增单步 undo 用例

### 文档
- `README.md` / `docs/README_zh.md`：结构树与 Development 小节补充 `tests/mayapy/`、`pytest.ini` 与 mayapy 运行命令
- `docs/AGENTS.md`：架构新增「测试」说明（纯套件进 CI / mayapy 本地两半布局）
- `docs/CONFIG_GUIDE_zh.md` / `docs/CONFIG_GUIDE.md`：功能回归与新增材质 Checklist 补充 mayapy 套件
- `docs/CONVERSION_SPEC_zh.md` / `docs/CONVERSION_SPEC.md`：标注负值各向异性在无符号目标（Arnold / RedshiftOpenPBR）上不可映射（记入 `issues`），旋转不参与转换；bump/normal 模式判定补充 Object-Space Normal；1.5 prerequisite 表新增 VRayMtl（subsurface）→ `translucencyMode` = `6`

### 验证
- 本机装齐 `mtoa` / `vrayformaya` / `lookdevKit` / `redshift4maya` 后跑完整 mayapy 套件：`mayapy -m unittest discover -s tests/mayapy -t tests -v` → **56 passed, 0 skipped**（6 种材质 × 30 个跨材质对全覆盖，含 bump/normal、CC、displacement、alphaIsLuminance、同渲染器复用等）；纯套件 192 passed

## 2026-10-05

### 修复
- **V-Ray 源材质处于 glossiness 模式（`useRoughness=0`）时，转换输出的 roughness 被反转**：`config/material/VRayMtl.json` 新增 `material.invert` 声明 —— `reflectionGlossiness` / `coatGlossiness` / `sheenGlossiness`（分别映射到 `specularRoughness` / `coatRoughness` / `fuzzRoughness`）在源开关为 glossiness 模式时按 `1 - x` 反转。数值直接反转；贴图/CC 链则在连向目标插槽的边上串入 Maya `reverse` 节点（不改动源链，`alphaIsLuminance` 追踪可穿透该节点）。`roughness`（`roughnessAmount`，漫反射粗糙度）是真实 roughness，不反转

### 重构
- `MaterialConverter._resolve_inverted_attrs()` 按源配置 `material.invert` 解析需反转的通用属性（读取开关失败时按 glossiness 默认保守反转并记 WARN）；`AttributeConverter.transfer_all()` / `_transfer_one()` 增加 `invert` 通道，代码中不含任何渲染器专用属性名，渲染器语义全部保留在 JSON
- `ConfigValidator` 新增对 `material.invert` 引用属性的拼写校验（与 prerequisites 同层）
- 转换结果模型扩展 `issues`/`with_issues`：`ConversionResult`/`BuildResult` 新增 `issues`（非关键通道失败）；`prerequisites.apply_prerequisites`/`apply_attr_prerequisites`、`cc.transfer`、`bump.convert`/`reuse_existing`、`displacement.convert` 返回成败；`attribute.transfer_all` 返回 `TransferReport(issues, critical)`；`material_builder` 记录 `last_build_issues`；`summarize_results`/`summarize_build_results` 增列 `with_issues`；`convert_all`/`build_all` 汇总输出 `with_issues` WARN
- **UI 暴露非关键通道失败**：`ui/feedback.py` 新增 `show_warning_banner`，`qt_maya_logger` 支持 `self._last_operation_warnings`（>0 时输出警告横幅 + WARN，替代 Success）；`converter_tab`/`builder_tab`/`batch_builder_tab` 汇总 `has_issues` 并警告（带 `nodes`，可右键选中）
- **转换 / 批量构建的彻底失败也会上屏**：`ConverterTab` / `BatchBuilderTab` 用 `summarize_results` / `summarize_build_results` 汇总 —— `failed` 时输出**红色警告横幅** + 带 `nodes` 的 ERROR 日志（此前只有 core 日志、UI 无提示），`with_issues` 时橙色横幅，全成功绿色横幅；统一经 `ui/feedback.py:show_result_banner`（best-effort）

### 文档
- `docs/CONFIG_GUIDE_zh.md` / `docs/CONFIG_GUIDE.md`：新增 `invert` 字段说明
- `docs/CONVERSION_SPEC_zh.md` / `docs/CONVERSION_SPEC.md`：映射表与值传递规则补充 glossiness→roughness 反转
- `docs/AGENTS.md`：更新 `attribute.py` / `converter.py` 职责与配置字段
- `README.md` / `docs/README_zh.md`：Converter 功能列表补充语义反转

### 测试
- 新增 `tests/test_converter.py`（反转集合解析）；`tests/test_config_loader.py` / `tests/test_attribute_converter.py` 增加 `invert` 解析与数值/连接反转用例

### 验证
- Maya 2024（mayapy standalone，加载 `mtoa` / `vrayformaya` / `lookdevKit`）跑 `ConfigValidator`：177 项检查 **0 ERROR / 0 WARN**（7 项 SKIP 为未安装 Redshift 的组）
- V-Ray ↔ Arnold 转换实测：glossiness 模式数值按 `1 - x` 反转、roughness 模式不反转；贴图连接与 Builder 全链（file→ramp）均在目标插槽前正确插入 `reverse` 节点且源链复用；Arnold → V-Ray 目标强制 `useRoughness=1`

## 2026-10-04

### 修复
- **CI 不再因阻塞的对话框挂起六小时**：`tests/test_feedback.py::test_show_error_dialog_uses_none_parent` 现在直接 monkeypatch `feedback.QtWidgets`；自 `7b971d9` 把 `from ui import QtWidgets` 提到 `ui/feedback.py` 模块顶部后，替换 `sys.modules["ui"]` 已无法命中已绑定的引用，测试实际调用了真实的模态 `QMessageBox.critical`，在 `QT_QPA_PLATFORM=offscreen` 下永久阻塞，最终在 6 小时上限处被取消

### CI
- `.github/workflows/test.yml`：新增 job 级 `timeout-minutes: 15` 与 `pytest-timeout`（`--timeout=120`），任何挂死的测试最多两分钟即失败，而不再耗尽 6 小时上限

## 2026-09-11

### 修复
- **同一 Maya 会话中其它扁平结构工具占用 `core` / `ui` 时启动不再失败**：`main.py` 接管时现在会释放 foreign 顶层模块**及其缓存的子模块**；此前只删顶层名，残留的 foreign `core.results`（例如 Batch Attribute Editor 留下的）会遮蔽本项目导入，导致启动报 `ImportError: cannot import name 'ConversionResult'`

### 重构
- `main.py` 启动加固：项目根始终移到 `sys.path` 最前（不再只在缺失时插入），并在本项目导入前释放 `core` / `ui` / `main` 下所有 foreign 模块；路径判断内联实现（`_owned_by_root`），因为为此 import `core.module_reload` 恰恰会被 foreign `core` 截胡
- 运行时延迟导入提到模块顶部（消除接管后延迟导入命中其它工具包的情形）：`ui/feedback.py`（`from ui import QtWidgets`）、`core/builder_context.py`（`ConfigLoader`，并删除局部 sys.path hack）、`core/material_builder.py`（`apply_prerequisites`）

### 文档
- `README.md` / `docs/README_zh.md`：六个功能小节各新增一张 UI 预览截图（`docs/images/*.webp`），并在项目结构树中补充 `docs/images/` 目录
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
