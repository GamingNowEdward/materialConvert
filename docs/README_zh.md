# PBR Material Converter

[English](../README.md) | **简体中文**

Maya 工具包，支持 Arnold / Redshift / V-Ray 之间的 PBR 材质转换、构建和场景管理。

## 安装

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

**支持版本**: Maya 2024+
**依赖**: [PyMEL](https://help.autodesk.com/view/MAYAUL/2027/CHS/?guid=GUID-2AA5EFCE-53B1-46A0-8E43-4CD0B2C72FB4)（随 Maya 自带，确认已安装于 Maya 环境中）

## 功能

### Material Converter
- 在 Arnold / Redshift / V-Ray 间批量转换 PBR 材质
- 自动识别材质类型，一键全部转换
- 支持 bump/normal 节点、颜色校正节点、置换节点的连带转换
- 批量转换带进度条，支持单步撤销（Ctrl+Z）
- 支持 6 种材质类型：`aiStandardSurface` / `aiOpenPBRSurface` / `RedshiftMaterial` / `RedshiftOpenPBRMaterial` / `RedshiftStandardMaterial` / `VRayMtl`

### Material Builder
- 从纹理路径一键构建完整 PBR 材质
- 支持 Color / Roughness / Normal / Bump / Displacement 通道
- SSS 通道支持（colorCorrect + layeredTexture + ramp）
- 置换节点链支持
- 渲染器按钮从配置动态生成
- Create File From P2D：从选中的 place2dTexture 节点创建 file 节点

### Node Tools
- **Select Nodes**：按类型批量选择（材质/文件/bump/layeredTexture/CC），排除默认材质
- **Set File Color Space**：批量设置 file 节点颜色空间
- **Auto Match Selected**：根据文件名关键词和连接通道自动匹配色彩空间（参考 `config/colorSpace.json`）
- **Color Management**：批量设置 file 节点的 ignoreColorSpaceFileRules
- **Rename Shading Engine**：批量重命名 SG 以匹配材质名称

### Transform Tools
- **Align To Floor**：将物体最低点对齐到 Y=0
- **Axis Alignment**：对齐到 X/Y/Z 轴的 min/max 边界
- **Center Pivots**：居中选中物体的轴心点
- **World Space Location**：将物体移动到指定世界坐标
- **Freeze Translations**：重置平移值为零
- **Freeze Rotations**：重置旋转值为零
- **Freeze Scale**：重置缩放值为一
- **Freeze All**：一次性重置所有变换
- **Apply All Pipeline**：居中轴心 → 设置位置 → 地面对齐 → Y轴最小对齐 → 冻结全部

### Attr Modifier
- 批量修改选中节点的指定属性值
- 支持 Boolean、Float、Integer、String 四种数据类型
- 自动检查 transform 和 shape 节点

### Locator
- 为选中物体自动创建 Layout Locator
- 根据包围盒尺寸缩放 Locator
- X/Y/Z 三轴独立缩放倍率
- 可选显示覆盖色
- 支持前缀命名

## 架构

### 数据流
```
源材质 → [源 JSON 配置] → 通用格式 → [目标 JSON 配置] → 目标材质
```

### 核心设计原则
- **配置驱动**：所有渲染器映射定义在 JSON 文件中，Python 代码中零硬编码属性名
- **易于扩展**：新增渲染器支持 = 在 `config/material/` 添加 JSON 文件，无需改代码
- **模块化转换器**：4 个独立模块分别处理属性传递、凹凸/法线、颜色校正、置换
- **统一导入**：PySide 版本探测集中在 `ui/__init__.py`
- **日志系统**：统一 Logger 类，支持回调函数与 UI 集成

## 项目结构

```
materialConvert/
├── config/                          # JSON 配置文件
│   ├── material/                    # 渲染器材质属性映射
│   │   ├── common.json              # 通用 PBR 参数
│   │   ├── aiStandardSurface.json
│   │   ├── aiOpenPBRSurface.json
│   │   ├── RedshiftMaterial.json
│   │   ├── RedshiftOpenPBRMaterial.json
│   │   ├── RedshiftStandardMaterial.json
│   │   └── VRayMtl.json
│   ├── bumpNormal.json              # 凹凸/法线节点映射
│   ├── colorCorrection.json         # 颜色校正节点映射
│   ├── colorSpace.json              # 色彩空间自动匹配规则
│   ├── builder_specs.json           # Material Builder 渲染器规格
│   └── builder_naming.json          # Material Builder 命名约定
├── core/                            # 核心引擎
│   ├── converter.py                 # MaterialConverter 调度器
│   ├── converters/                  # 业务转换模块
│   │   ├── attribute.py             # 属性收集与传递
│   │   ├── bump.py                  # 凹凸/法线转换
│   │   ├── cc.py                    # 颜色校正转换
│   │   └── displacement.py          # 置换转换
│   ├── config_loader.py             # JSON 配置解析
│   ├── node_utils.py                # Maya 节点工具函数
│   ├── prerequisites.py             # 渲染器前提条件处理
│   ├── logger.py                    # 统一日志模块
│   └── builder_context.py           # Material Builder 共享状态
├── ui/                              # 用户界面
│   ├── converter_ui.py              # 主窗口 (QTabWidget)
│   ├── styles.py                    # QSS 暗色主题
│   └── tabs/                        # 六个功能标签页
│       ├── converter_tab.py         # 材质转换
│       ├── builder_tab.py           # Material Builder
│       ├── node_tools_tab.py        # Node Tools
│       ├── transform_tab.py         # Transform Tools
│       ├── attr_modifier_tab.py     # Attr Modifier
│       └── locator_tab.py           # Locator 工具
├── docs/                            # 文档
│   ├── CONVERSION_SPEC.md           # 转换规格说明（英文）
│   ├── CONVERSION_SPEC_zh.md        # 转换规格说明（中文）
│   └── README_zh.md                 # 本文件
├── main.py                          # 入口脚本
└── CHANGELOG.md                     # 变更日志
```

## 文档

- [CONVERSION_SPEC.md](CONVERSION_SPEC.md) — 转换规格说明（英文）
- [CONVERSION_SPEC_zh.md](CONVERSION_SPEC_zh.md) — 转换规格说明（中文）

## License

MIT
