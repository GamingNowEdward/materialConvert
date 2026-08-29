# 渲染器 JSON 配置编写指南

**简体中文** | [English](CONFIG_GUIDE.md)

## 概述

本工具的**属性映射采用配置驱动**：所有渲染器属性映射全部定义在 `config/` 目录的 JSON 文件中，Python 代码中零硬编码属性名（转换行为本身由代码实现）。新增渲染器材质支持 = **添加 JSON 文件，不需要修改任何业务代码**。

**数据流：**

```
源材质属性 → [源 JSON 配置] → 通用格式 → [目标 JSON 配置] → 目标材质属性
```

### 涉及的三个文件

| 文件 | 必要性 | 作用 | 缺失时的行为 |
|---|---|---|---|
| `config/material/<NodeType>.json` | **必选** | 材质节点元数据 + 属性映射 + 置换配置 | 工具完全不认识该材质 |
| `config/bumpNormal.json` | 强烈推荐 | 凹凸/法线节点映射（按 `renderer` 键查找） | 转换时跳过凹凸/法线处理 |
| `config/colorCorrection.json` | 强烈推荐 | 颜色校正（CC）节点映射（按 `renderer` 键查找） | CC 链不转换，贴图直接连到目标属性 |

> `renderer` 键是三份配置之间的关联纽带：材质 JSON 中声明的 `renderer` 值（如 `"vray"`）会被用于在 `bumpNormal.json` 和 `colorCorrection.json` 中查找同名的段。

---

## 通用属性体系

所有渲染器的属性映射都以 `config/material/common.json` 定义的**通用属性名**为键。这是转换的中间格式：源配置把 Maya 属性翻译成通用名，目标配置再把通用名翻译回目标渲染器的 Maya 属性。

### 通用属性总表

| 分段 | 通用属性 |
|---|---|
| `base` | `baseColor`、`baseColorWeight`、`metallic`、`roughness` |
| `specular` | `specularWeight`、`specularColor`、`specularRoughness`、`specularAnisotropy`、`ior` |
| `transmission` | `transmissionWeight`、`transmissionColor` |
| `geometry` | `normal_bump`、`opacity`、`thinWalled` |
| `subsurface` | `subsurfaceWeight`、`subsurfaceColor`、`subsurfaceRadius`、`subsurfaceScale` |
| `coat` | `coatWeight`、`coatColor`、`coatRoughness`、`coatIor` |
| `fuzz` | `fuzzWeight`、`fuzzColor`、`fuzzRoughness` |
| `emission` | `emissionWeight`、`emissionColor` |
| `displacement`（专用块） | `displacementScale`、`displacementTexture` |

注意事项：

- `normal_bump`、`displacementScale`、`displacementTexture` 由专门的转换模块处理，主属性循环会跳过它们
- 新材质 JSON 的分段名和键名**必须与上表完全一致**——多出的键不会被识别，缺失的键视为不支持
- 颜色-权重配对关系定义在 `common.json` 的 `color_weight_pairs` 数组（如 `["baseColor", "baseColorWeight"]`），用于黑色自动归零等逻辑；只有新增通用属性时才需要修改它

---

## 第一步：材质映射 JSON

### 文件位置与命名

在 `config/material/` 目录下新建 JSON 文件。**文件名不参与程序识别**（程序以 `material.node_type` 作为主键），但强烈建议与 `node_type` 保持一致，便于维护。

> 唯一的保留名是 `common.json`，加载器会跳过它。

### `material` 元数据块

```json
{
  "material": {
    "node_type": "VRayMtl",
    "plugin": "vrayformaya",
    "prerequisites": { },
    "short_name": "vray",
    "uiPanel_display_name": "V-Ray",
    "renderer": "vray"
  }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `node_type` | ✅ | Maya 节点类型名，**必须与实际类型精确一致（区分大小写）**。同时是整个配置体系的主键：转换目标选择、材质识别、Builder 下拉框都以此为准 |
| `renderer` | ✅ | 渲染器查找键。内置取值为 `"arnold"`、`"redshift"`、`"vray"`；也允许自定义键。用于在 `bumpNormal.json` / `colorCorrection.json` 中查找对应段，以及 Alpha Is Luminance 等按渲染器的特殊逻辑 |
| `uiPanel_display_name` | ✅ | UI 下拉框显示名称（缺省回落到 `node_type`） |
| `short_name` | 建议 | 转换后新材质的命名后缀：`{源材质名}_{short_name}`（缺省用 `"converted"`）。现有约定：`aiStd` / `aiPBR` / `rsStd` / `rsPBR` / `rsStdMat` / `vray` |
| `plugin` | 建议 | 渲染器插件模块名（如 `mtoa` / `redshift4maya` / `vrayformaya`）。仅 Debug 校验使用：检测插件加载状态，未安装则该渲染器整组 SKIP，不会误报拼写错误 |
| `prerequisites` | 可选 | 材质级前置条件，见下文 |

### 属性映射段

`material` 块之外的每个顶层对象都是一个属性映射段（`base` / `specular` / `transmission` / `geometry` / `subsurface` / `coat` / `fuzz` / `emission`）：

```json
"base": {
  "baseColor": "color",
  "baseColorWeight": "diffuseColorAmount",
  "metallic": "metalness",
  "roughness": "roughnessAmount"
}
```

- **键** = 通用属性名（见上文总表）
- **值** = 该材质节点上的真实 Maya 属性名
- **值为空字符串 `""`** 表示该渲染器不支持此属性，转换循环自动跳过（例如 VRayMtl 没有 `emissionWeight`）

也可以**整段省略**，效果等同该段所有属性写 `""`。

### prerequisites（前置条件）

某些渲染器的材质需要先打开开关或设置默认值，属性映射才有意义。支持两个层级：

**1. 材质级** — 放在 `material` 块内，每次向该材质转换时都会执行：

```json
"prerequisites": {
  "roughness_mode": {
    "attribute": "useRoughness",
    "value": 1
  },
  "reflection_color": {
    "attribute": "reflectionColor",
    "value": [1, 1, 1]
  }
}
```

**2. 属性级** — 放在属性映射段内，键为通用属性名；仅当该通用属性在主循环中被实际处理时执行：

```json
"base": {
  "baseColor": "diffuse_color",
  "metallic": "refl_metalness",
  "prerequisites": {
    "metallic": {
      "attribute": "refl_fresnel_mode",
      "value": 2
    }
  }
}
```

> 示例含义：RedshiftMaterial 只有在 `refl_fresnel_mode=2`（金属模式）下金属度才生效，因此把它挂到 `metallic` 属性上。

格式规则：

| 规则 | 说明 |
|---|---|
| 格式 | `{ "任意说明性键名": { "attribute": "...", "value": ... } }` |
| `value` 为数组 | 按 float3 多参数设置（广播到三个通道） |
| `attribute` 为空或 `value` 为 null | 静默跳过 |
| 设置失败 | 仅记录 WARN 日志，不中断转换 |

### `displacement` 块

```json
"displacement": {
  "node_type": "RedshiftDisplacement",
  "displacementScale": "scale",
  "displacementTexture": "texMap",
  "file_source": "outAlpha",
  "lyr_src": "outColor",
  "output": "out"
}
```

| 字段 | 默认值 | 说明 |
|---|---|---|
| `node_type` | `""` | 置换节点类型。**哨兵值语义**：`"displacementShader"` 表示"将贴图直接连接到 SG 的 `displacementShader`"，不创建新节点；其他类型名才会真正创建节点；留空表示该渲染器不支持置换 |
| `displacementScale` | `""` | 置换节点上的强度属性 |
| `displacementTexture` | `""` | 置换节点上接收贴图的输入属性 |
| `file_source` | `outAlpha` | file 节点直连置换节点时使用的输出属性（灰度图通常取 alpha） |
| `lyr_src` | `outAlpha` | Builder 全链路模式下 layeredTexture 输出到置换节点的连接属性。若置换输入接收颜色类型（如 Redshift `texMap`）应设为 `outColor` |
| `output` | `displacement` | 置换节点输出到着色引擎（SG）的属性名 |

现有参考：Arnold / V-Ray 使用原生 `displacementShader`（哨兵值路径），Redshift 使用 `RedshiftDisplacement` 真实节点。

### 完整模板

以下模板可直接复制修改，占位符用 `<...>` 标出：

```json
{
  "material": {
    "node_type": "<MayaNodeType>",
    "plugin": "<pluginModule>",
    "prerequisites": {
      "<descriptive_name>": {
        "attribute": "<mayaAttr>",
        "value": <scalar or [r, g, b]>
      }
    },
    "short_name": "<suffix>",
    "uiPanel_display_name": "<Display Name>",
    "renderer": "<rendererKey>"
  },
  "base": {
    "baseColor": "<attr or empty string>",
    "baseColorWeight": "<attr>",
    "metallic": "<attr>",
    "roughness": "<attr>"
  },
  "specular": {
    "specularWeight": "<attr>",
    "specularColor": "<attr>",
    "specularRoughness": "<attr>",
    "specularAnisotropy": "<attr>",
    "ior": "<attr>"
  },
  "transmission": {
    "transmissionWeight": "<attr>",
    "transmissionColor": "<attr>"
  },
  "geometry": {
    "normal_bump": "<bump input attr>",
    "opacity": "<attr>",
    "thinWalled": "<attr>"
  },
  "subsurface": {
    "subsurfaceWeight": "<attr>",
    "subsurfaceColor": "<attr>",
    "subsurfaceRadius": "<attr>",
    "subsurfaceScale": "<attr>"
  },
  "coat": {
    "coatWeight": "<attr>",
    "coatColor": "<attr>",
    "coatRoughness": "<attr>",
    "coatIor": "<attr>"
  },
  "fuzz": {
    "fuzzWeight": "<attr>",
    "fuzzColor": "<attr>",
    "fuzzRoughness": "<attr>"
  },
  "emission": {
    "emissionWeight": "<attr>",
    "emissionColor": "<attr>"
  },
  "displacement": {
    "node_type": "<NodeType or displacementShader>",
    "displacementScale": "<attr>",
    "displacementTexture": "<input attr>",
    "file_source": "outAlpha",
    "lyr_src": "<outAlpha or outColor>",
    "output": "<output attr>"
  }
}
```

### 真实示例节选

V-Ray 的 base/specular 段（注意属性名的差异与不支持项的处理方式）：

```json
"base": {
  "baseColor": "color",
  "baseColorWeight": "diffuseColorAmount",
  "metallic": "metalness",
  "roughness": "roughnessAmount"
},
"specular": {
  "specularWeight": "reflectionColorAmount",
  "specularColor": "reflectionColor",
  "specularRoughness": "reflectionGlossiness",
  "specularAnisotropy": "anisotropy",
  "ior": "refractionIOR"
}
```

---

## 第二步：`bumpNormal.json` 渲染器段

每个渲染器的 `bump` / `normal` 段使用**统一字段 schema**（按数据流方向排列）：

| 字段 | 说明 |
|---|---|
| `is_material_attribute` | `false` = 独立节点模式（maya/arnold/redshift）；`true` = 材质内嵌模式；不创建专用凹凸/法线节点（V-Ray） |
| `node_type` | 独立节点模式的节点类型；材质内嵌模式省略 |
| `input` | 接收上游贴图的输入属性 |
| `output` | 连向下游材质的输出属性；内嵌模式省略 |
| `scale` | 强度属性 |
| `is_normal` / `is_normal_value` | 可选，**必须成对出现**；模式开关属性及 normal 模式下的取值。`is_normal_value` 可为标量或数组（数组表示多个取值均为 normal 模式，写入时取第一个元素）。Maya `bumpInterp`：0=Bump、1=Tangent Space Normals、2=Object Space Normals（normal 段配置 `[1, 2]`）；Redshift `inputType`、V-Ray `bumpMapType`：0=bump / 1=normal |
| `file_source` | 贴图节点的输出属性（默认 `outColor`） |
| `default_scale` | Builder 构建时设置的默认强度 |

### 三种模式判别

| 模式 | 代表渲染器 | 判别方式 |
|---|---|---|
| 独立节点、不同类型 | Arnold（`aiBump2d` / `aiNormalMap`） | 节点类型直接决定 bump 或 normal |
| 共享类型 | Maya（`bump2d`）、Redshift（`RedshiftBumpMap`） | 同一节点类型，靠 `is_normal` 开关属性取值区分 |
| 材质内嵌 | V-Ray（`bumpMap` + `bumpMult` + `bumpMapType`） | `is_material_attribute: true`，无独立节点，直接读写材质属性 |

### 编写示例

Redshift 段（共享类型，bump 与 normal 是同一节点类型，仅 `is_normal_value` 不同）：

```json
"redshift": {
  "bump": {
    "is_material_attribute": false,
    "node_type": "RedshiftBumpMap",
    "input": "input",
    "output": "out",
    "scale": "scale",
    "is_normal": "inputType",
    "is_normal_value": 0,
    "file_source": "outColor",
    "default_scale": 0.1
  },
  "normal": {
    "is_material_attribute": false,
    "node_type": "RedshiftBumpMap",
    "input": "input",
    "output": "out",
    "scale": "scale",
    "is_normal": "inputType",
    "is_normal_value": 1,
    "file_source": "outColor",
    "default_scale": 1.0
  }
}
```

### 注意事项

- 文件顶部的 `common` 段仅作缺失字段的默认值兜底，建议新渲染器段写出全部字段，不要依赖兜底
- **禁止添加无消费方的自定义字段**——字段必须被转换/构建代码消费（校验器只查属性拼写，不查字段是否被使用）
- 未添加渲染器段时，涉及该渲染器的凹凸/法线转换整体跳过（源状态保留）
- `maya` 段同样重要：跨渲染器场景中连接到任意材质上的 Maya 原生 bump 节点也要靠它识别

---

## 第三步：`colorCorrection.json` 渲染器段

每个渲染器段包含三个子块：

```json
"vray": {
  "material": {
    "node_type": "VRayColorCorrection",
    "input": "texture_map",
    "output": "outColor"
  },
  "base": {
    "gamma": "",
    "contrast": "contrast",
    "gain": "brightness"
  },
  "color": {
    "hue": "hue_shift",
    "saturation": "saturation",
    "hue_range": [-180, 180],
    "hue_center": 0
  }
}
```

| 子块 | 字段 | 说明 |
|---|---|---|
| `material` | `node_type` / `input` / `output` | CC 节点类型、贴图输入属性、输出属性 |
| `base` | `gamma` / `contrast` / `gain` | 明度类控制属性；不支持的控制写空字符串（如 V-Ray 无 gamma 控制） |
| `color` | `hue` / `saturation` | 色相/饱和度控制属性 |
| `color` | `hue_range` / `hue_center` | hue 归一化参数，见下文 |

### hue 归一化语义

各渲染器的 hue 属性量纲不同，转换时统一经过**通用偏移角 [-180, 180]**（0 = 不变）：

- `hue_range`：该渲染器 hue 属性的合法取值区间
- `hue_center`：中性点（"无变化"）对应的原始值。偏移型属性（Arnold/V-Ray）中性点为 0；绝对型属性（Maya [0,360]）中性点为 180

换算示例：Redshift `hue=90` → 通用偏移 90 → Arnold `hueShift=0.5`。

### 缺省行为

未添加渲染器段（或 `node_type` 为空）时：CC 链不转换，纹理经 `_smart_connect()` 直接连接到目标材质属性，其余属性照常传递。

---

## 验证流程

### 1. 手动验证 node_type

Maya 节点类型名区分大小写，添加前必须验证：

```python
import maya.cmds as cmds
n = cmds.createNode("YourMaterialType")   # 若警告 Unrecognized node type 则名字有误
cmds.delete(n)                             # 验证后立即删除
```

### 2. Debug 配置校验（推荐）

打开 Log 标签页运行 **Config Validation**：校验器会在 Maya 中创建临时节点，逐一核对每个 JSON 的 `node_type` 和所有映射属性（含 prerequisites 与 displacement）的真实拼写，结束后清理临时节点。

- 插件未安装/无法加载 → 该渲染器整组标记 SKIP 并跳过，**不会误报为拼写错误**
- 结果进入统一日志流，可按级别/来源过滤

### 3. 功能回归

纯 Python 测试无需 Maya：

```
python -m pytest tests/ -v
```

最后在 Maya 中重新加载工具，做一次双向转换实测（含凹凸、CC、置换链路的材质最有代表性）。

---

## 边界与注意事项

### Builder 自动收录与限制

- 新材质 JSON 会**自动出现在 Material Builder / Batch Builder 的下拉框中**，无需注册
- 但 Builder 只支持已实现的通道策略：`color` / `float` / `roughness` / `normal_bump` / `displacement`。新增"普通属性"仍需扩展 Python 建链函数，不能仅靠 JSON
- 颜色通道的权重属性由 `common.json` 的 `color_weight_pairs` 推导，无需额外配置

### colorSpace 自动扩展

色彩空间自动匹配（Auto Match Selected）使用的属性关键词会根据所有材质 JSON 的属性映射**动态扩展**，新渲染器无需手动维护 `config/colorSpace.json`。

### 命名后缀约定

代码内部使用固定缩写映射为新节点命名：

```
arnold → ai    redshift → rs    vray → vray
```

例如凹凸节点命名 `{源节点}_{short}{Bump|Nrm}`、CC 节点 `{源CC}_{short}`、置换节点 `{源材质}_{short}Disp`。这些由 `renderer` 键驱动，无需配置。

### 其他规则

- 所有节点创建走 `cmds.shadingNode(asShader=True/asUtility=True)`，保证 Hypershade 注册——这是代码行为，编写 JSON 时无需关心，但排查"Hypershade 里看不到新节点"问题时要知道这一点
- 转换后的旧节点永不删除，仅从 shadingEngine 断开

---

## Checklist

新增一个渲染器材质类型的完整清单：

- [ ] 已用 `cmds.createNode` 验证 Maya 实际节点类型名（区分大小写）
- [ ] `config/material/<NodeType>.json`：`material` 块含 `node_type` / `renderer`（内置：arnold/redshift/vray）/ `uiPanel_display_name`
- [ ] 属性段的键与通用属性总表完全一致；不支持项写 `""` 或整段省略
- [ ] 需要开关/默认值的属性已配置 prerequisites（材质级或属性级）
- [ ] `displacement` 块已按哨兵值语义正确填写（或确认不支持）
- [ ] `bumpNormal.json` 已添加同名 `renderer` 段（bump + normal），三种模式判别正确
- [ ] `colorCorrection.json` 已添加同名 `renderer` 段，`hue_range` / `hue_center` 符合该渲染器量纲
- [ ] 运行 Log 标签页 Config Validation：无 ERROR/WARN（插件未装时整组 SKIP 属正常）
- [ ] `python -m pytest tests/ -v` 通过
- [ ] Maya 内实测一次双向转换（覆盖凹凸/CC/置换链路）

---

## 常见问题排查

| 症状 | 根因 |
|---|---|
| 转换没有任何反应 | `material.node_type` 与 Maya 实际类型名不一致（大小写敏感） |
| 下拉框里找不到新材质 | JSON 解析失败（查看日志中的 ConfigLoader ERROR）；或文件不在 `config/material/` 下 |
| 某些属性转过去全是空的 | 属性值为 `""`（视为不支持）；或键名与通用属性总表不一致 |
| 凹凸/法线没有被转换 | `bumpNormal.json` 缺少该渲染器的段，或 `renderer` 键与材质 JSON 中声明的不一致 |
| CC 链没有转换、贴图直连了 | 目标渲染器在 `colorCorrection.json` 中无配置（属预期降级行为），或 `node_type` 为空 |
| Debug 校验报某属性不存在 | 映射的 Maya 属性名拼写错误；若整组 SKIP 则是插件未安装（正常忽略） |
| hue 转换结果偏差 | `hue_range` / `hue_center` 与该渲染器实际量纲不符 |
| 置换没有创建节点 | `node_type` 写的是哨兵值 `displacementShader`（预期直连 SG）；或 `displacementTexture` 为空（视为不支持置换） |
