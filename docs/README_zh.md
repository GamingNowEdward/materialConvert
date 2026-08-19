# PBR Material Converter

[English](../README.md) | **简体中文**

**转换规格说明：** [简体中文](CONVERSION_SPEC_zh.md) | [English](CONVERSION_SPEC.md)

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

**方式三：使用 bat 文件（最简单）**

双击运行 `copy_launch.bat`，启动命令会自动复制到剪贴板，直接在 Maya Script Editor 中粘贴即可。

**支持版本**: Maya 2024+
**依赖**: 无（零外部依赖，纯 `maya.cmds` API）

## 功能

### Material Converter
- 在 Arnold / Redshift / V-Ray 间批量转换 PBR 材质
- 自动识别材质类型，一键全部转换
- 支持 bump/normal 节点、颜色校正节点、置换节点的连带转换
- 批量转换带进度条，支持单步撤销（Ctrl+Z）
- 支持 6 种材质类型：`aiStandardSurface` / `aiOpenPBRSurface` / `RedshiftMaterial` / `RedshiftOpenPBRMaterial` / `RedshiftStandardMaterial` / `VRayMtl`

### Material Builder
- 从纹理路径一键构建完整 PBR 材质
- 支持 Color / Roughness / Glossiness（自动反相）/ Metallic / Normal / Bump / Displacement / Opacity / Transmission / Reflection / Sheen / SSS / Emission 通道
- SSS 通道支持（colorCorrect + layeredTexture + ramp）
- 置换节点链支持
- 材质类型下拉框由 `config/material/*.json` 驱动——新增材质自动出现
- 可选"加入快速选择集"开关
- Create File From P2D：从选中的 place2dTexture 节点创建 file 节点

### Batch Builder
- 选择目录并自动按文件名解析 PBR 贴图（规则参考 `config/texture_channels.json`）
- 将贴图分组为材质，并预览将要创建的材质列表（Materials to Build）
- 已解析通道与未解析文件合并展示在同一个表格，Status 列支持排序
- 批量构建全部 / 选中材质到任意支持的渲染器
- 可切换完整 Builder 流程（colorCorrect + layeredTexture + ramp）或简单直连
- 支持 BaseColor / Roughness / Glossiness（自动反相）/ Metallic / Normal / Bump / Displacement / Opacity / Transmission / Reflection / Sheen / SSS（Translucency + Scattering）/ Emission


### Node Tools
- **Select Nodes**：按类型批量选择（材质/文件/bump/layeredTexture/CC），排除默认材质
- **Set File Color Space**：批量设置 file 节点颜色空间
- **Auto Match Selected**：自动匹配色彩空间——文件名关键词来自 `config/texture_channels.json`（按通道 type 分组），通道匹配通过 BFS 追踪 file 全部下游连接（单通道/outAlpha/中间节点）并对 `commonAttributeRoles` + `config/material/*.json` 扩展的属性关键词规范化匹配；歧义节点（文件名角色 ≠ 通道角色）自动跳过并保留选中供手动复核
- **Color Management**：批量设置 file 节点的 ignoreColorSpaceFileRules
- **Rename Shading Engine**：批量重命名 SG 以匹配材质名称

### Debug
- 在 Maya 中校验全部 JSON 配置的拼写是否正确（材质 / `bumpNormal.json` / `colorCorrection.json`）
- 创建临时节点校验 `node_type` 与每个映射属性（含 prerequisites 与 displacement），结束后自动清理
- 未安装插件的渲染器尽可能自动加载，加载失败则整组跳过（绝不误报为拼写错误）
- 可筛选的验证日志（Errors / Warnings / Skipped / OK / Info），按类别着色

## 架构

### 数据流
```
源材质 → [源 JSON 配置] → 通用格式 → [目标 JSON 配置] → 目标材质
```

### 核心设计原则
- **配置驱动**：所有渲染器映射定义在 JSON 文件中，Python 代码中零硬编码属性名
- **CC 节点类型配置驱动**：颜色校正节点识别直接读取 `config/colorCorrection.json` 定义的节点类型；新增已配置的 CC 节点类型无需维护 Python 类型列表
- **易于扩展**：新增渲染器支持 = 在 `config/material/` 添加 JSON 文件，无需改代码
- **模块化转换器**：4 个独立模块分别处理属性传递、凹凸/法线、颜色校正、置换
- **统一导入**：PySide 版本探测集中在 `ui/__init__.py`
- **日志系统**：统一 Logger 类，支持回调函数与 UI 集成

## 项目结构

```
materialConvert/
├── config/                          # JSON 配置文件
│   ├── material/                    # 渲染器材质属性映射
│   │   ├── common.json              # 通用 PBR 参数及颜色-权重关系
│   │   ├── aiStandardSurface.json
│   │   ├── aiOpenPBRSurface.json
│   │   ├── RedshiftMaterial.json
│   │   ├── RedshiftOpenPBRMaterial.json
│   │   ├── RedshiftStandardMaterial.json
│   │   └── VRayMtl.json
│   ├── bumpNormal.json              # 凹凸/法线节点映射
│   ├── colorCorrection.json         # 颜色校正节点映射
│   ├── colorSpace.json              # 色彩空间自动匹配规则
│   ├── texture_channels.json       # Batch Builder 文件名→通道规则
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
│   ├── builder_context.py           # Material Builder 共享状态
│   ├── texture_scanner.py           # 目录扫描 / 文件名→通道解析
│   ├── batch_builder.py             # 批量构建编排
│   ├── material_builder.py          # Material Builder 核心逻辑
│   └── config_validator.py          # JSON 配置校验（Debug 标签页）
├── ui/                              # 用户界面
│   ├── converter_ui.py              # 主窗口 (QTabWidget)
│   ├── styles.py                    # QSS 暗色主题
│   └── tabs/                        # 五个功能标签页
│       ├── converter_tab.py         # 材质转换
│       ├── builder_tab.py           # Material Builder
│       ├── batch_builder_tab.py    # Batch Builder
│       ├── node_tools_tab.py        # Node Tools
│       └── debug_tab.py             # Debug（配置校验）
├── docs/                            # 文档
│   ├── AGENTS.md                    # AI Agent 开发指南
│   ├── CONVERSION_SPEC.md           # 转换规格说明（英文）
│   ├── CONVERSION_SPEC_zh.md        # 转换规格说明（中文）
│   └── README_zh.md                 # 本文件
├── main.py                          # 入口脚本
├── copy_launch.bat                  # 双击复制启动命令
├── LICENSE
├── CHANGELOG.md                     # 变更日志
└── CHANGELOG_zh.md                  # 中文版更新日志
```

## 文档

- [CONVERSION_SPEC.md](CONVERSION_SPEC.md) — 转换规格说明（英文）
- [CONVERSION_SPEC_zh.md](CONVERSION_SPEC_zh.md) — 转换规格说明（中文）

## License

MIT
