# PBR Material Converter

Maya 工具 —— 在 Arnold / Redshift / V-Ray 之间一键转换 PBR 材质，自动处理凹凸/法线、颜色校正、置换节点。

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

**零外部依赖**，不需要 pip install。

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
- 渲染器按钮从配置动态生成，新增渲染器只需改 JSON

### Node Tools
- 按类型批量选择节点
- 批量设置 file 节点颜色空间
- 批量重命名 Shading Engine

### Transform Tools
- 对齐、原点居中、冻结变换
- 世界空间定位

### Attr Modifier
- 批量修改节点属性值

### Locator
- 为选中物体自动创建 Locator
- 根据boubdingBox尺寸缩放 Locator
- 支持前缀、三轴独立缩放倍率、覆盖色

## 项目结构

```
materialConvert/
├── config/              # JSON 配置文件（渲染器材质/CC/bump 映射）
├── core/                # 核心转换引擎
│   ├── converter.py     # 调度器
│   ├── converters/      # 四个业务转换模块
│   ├── node_utils.py    # 节点操作工具函数
│   └── logger.py        # 统一日志模块
├── ui/                  # 用户界面
│   ├── converter_ui.py  # 主窗口
│   ├── styles.py        # QSS 样式
│   └── tabs/            # 六个功能标签页
├── docs/                # 文档
└── main.py              # 入口脚本
```

## 文档

- [CONVERSION_SPEC.md](docs/CONVERSION_SPEC.md) — 完整转换规格说明
- [AGENTS.md](docs/AGENTS.md) — AI Agent 开发指南

## License

MIT
