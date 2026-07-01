# Changelog

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
