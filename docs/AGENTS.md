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

本项目**零外部依赖**，不需要 pip install。分发给他人时只需拷贝文件夹并告诉对方改 shelf 按钮路径即可。

如果修改代码后没生效，关掉窗口重新点击按钮即可。

## 架构

**数据流：`源材质属性 → [源 JSON 配置] → 通用格式 → [目标 JSON 配置] → 目标材质属性`**

- 所有渲染器映射定义在 `config/*.json` 中，Python 代码中**零硬编码渲染器类型名**
- 新增渲染器支持：**只需添加 JSON 文件，不需要改业务代码**
- 四个转换模块位于 `core/converters/` 目录下：
  - `attribute.py` — 材质属性收集与传递 + 黑色颜色自动归零 + Alpha Is Luminance 修复
  - `bump.py` — 凹凸/法线节点检测与转换（独立节点 / 共享类型 / 材质内嵌）
  - `cc.py` — 颜色校正链检测（通过 `listHistory`）、转换、跨通道复用
  - `displacement.py` — 置换节点转换（Redshift ↔ 原生 `displacementShader`）
  - `locator_tab.py` — Layout Locator 创建（包围盒缩放 + 覆盖色）
- 调度器：`core/converter.py`（约 90 行）
- 工具函数：`core/node_utils.py`（全部为静态方法 — 使用 `NodeUtils`，不要 `NodeUtils()`）
- 配置读取：`core/config_loader.py`（读取 JSON，提供公开查询方法）
- 界面：`ui/converter_ui.py`（QTabWidget，6 个标签页，约 40 行）
- 样式：`ui/styles.py`（QSS 暗色主题）
- Builder：`core/builder_context.py`（`BuilderContext` 状态管理 + 工具方法）
- Builder 配置：`config/builder_specs.json`（渲染器规格） + `config/builder_naming.json`（命名约定）

### 统一导入
所有 UI 模块从 `ui` 包统一导入 PySide 和 Maya 模块，避免重复的 `try/except`：
```python
from ui import QtWidgets, QtCore, QtGui, cmds       # tabs
from ui import QtWidgets, QtCore, QtGui, shiboken    # converter_ui.py
```
PySide 版本探测集中在 `ui/__init__.py` 一处，新增 tab 时只需一行 import。

### 新增渲染器材质
只需在 `config/material/` 目录下添加对应的 JSON 文件，包含 `node_type`、`uiPanel_display_name`、`renderer` 和属性映射。无需修改任何 Python 代码，UI 下拉框和转换逻辑自动支持。

## 关键规则

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
禁止使用 `pm.createNode()` — 它不会注册到 Hypershade，会导致"转换成功但 Hypershade 里看不到"的 bug。

### JSON node_type 必须与 Maya 精确一致
Maya 节点类型名区分大小写。添加前必须验证：
```python
n = pm.createNode("RedshiftOpenPBRMaterial")  # 测试确切的类型名
```
如果 Maya 警告 "Unrecognized node type"，说明 JSON 中的 key 写错了。

### `displacementShader` 哨兵值
在置换 JSON 配置中，`node_type: "displacementShader"` **不是真正的节点类型名**。它表示"将纹理直接连接到 `SG.displacementShader`"。真正需要创建节点的类型（如 `RedshiftDisplacement`）才会触发节点创建。

### 旧节点永不删除
转换后的材质、凹凸、CC 和置换节点**保留在场景中**，只是从 shadingEngine 上断开连接。不要添加删除逻辑。

### 属性传递循环中跳过的属性
`normal_bump`、`displacementScale`、`displacementTexture` 由专门的转换模块处理，主属性循环会跳过它们。永远不要从跳过列表中移除这些属性。

### `renderer_map` 命名约定
```python
renderer_map = {"arnold": "ai", "redshift": "rs"}  # 仅在需要缩写时使用
renderer_short = renderer_map.get(target_renderer, target_renderer)  # 回退为原名
```

## 开发工作流

1. 直接在 `C:\opencode\materialConvert\` 下编辑代码
2. 在 Maya Script Editor 中重新 `exec()` 加载
3. 如果模块缓存问题持续存在，关闭窗口后重新运行
4. 无测试框架 — 在 Hypershade 中手动验证，或编写诊断脚本

## 常见陷阱

| 症状 | 根因 |
|---|---|
| 转换没有任何反应 | JSON 的 `node_type` 与 Maya 实际节点类型名不匹配 |
| 新节点在 Hypershade 中不可见 | 使用了 `pm.createNode` 而非 `cmds.shadingNode` |
| CC 节点检测不到 | CC 前面有中间节点 — 使用 `listHistory` 搜索，而非直连检查 |
| 凹凸和法线混淆 | 共享类型节点（`bump2d` / `RedshiftBumpMap`）需要检查 `inputType`/`bumpInterp` |
| V-Ray 凹凸类型属性设置失败 | 属性名是 `bumpMapType`，不是 `bumpType` |
| `outAlpha` → `input` 连接失败 | 类型不兼容：float → color。使用 `smart_connect` 回退到 `outColor` |
| 材质转换后消失 | ShadingEngine 未重新绑定。检查 SG 替换逻辑 |
| V-Ray specularWeight 未传递 | JSON 中拼写错误：`reflectionColorAmoun`（缺少字母 `t`） |
