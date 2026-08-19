# PBR 材质转换器 — 转换规格说明

[English](CONVERSION_SPEC.md) | **简体中文**

## 概述

通过**通用 PBR 属性格式**在 Arnold、Redshift、V-Ray 之间转换材质。  
所有映射定义在 `config/` JSON 文件中，Python 代码中零硬编码属性名。

**转换流程：**

```
源材质属性 → [源配置] → 通用格式 → [目标配置] → 目标材质属性
```

**支持的材质类型：**

| 渲染器 | 材质类型 | 命名后缀 |
|---|---|---|
| Arnold | `aiStandardSurface` | `_aiStd` |
| Arnold | `aiOpenPBRSurface` | `_aiPBR` |
| Redshift | `RedshiftMaterial` | `_rsStd` |
| Redshift | `RedshiftOpenPBRMaterial` | `_rsPBR` |
| Redshift | `RedshiftStandardMaterial` | `_rsStdMat` |
| V-Ray | `VRayMtl` | `_vray` |

---

## 一、主材质属性

### 1.1 完整映射表

列：aiOpenPBR / aiStandardSurface / RedshiftMaterial / RedshiftOpenPBRMaterial / RedshiftStandardMaterial / VRayMtl  
`-` 表示该渲染器不支持此属性。

| 通用属性 | aiOpenPBR | aiStd | RS Material | RS OpenPBR | RS StdMat | VRayMtl |
|---|---|---|---|---|---|---|
| **baseColor** | baseColor | baseColor | diffuse_color | base_color | base_color | color |
| **baseColorWeight** | baseWeight | base | diffuse_weight | base_weight | base_color_weight | diffuseColorAmount |
| **metallic** | baseMetalness | metalness | refl_metalness | base_metalness | metalness | metalness |
| **roughness** | baseDiffuseRoughness | diffuseRoughness | diffuse_roughness | base_diffuse_roughness | diffuse_roughness | roughnessAmount |
| **specularWeight** | specularWeight | specular | refl_weight | specular_weight | refl_weight | reflectionColorAmount |
| **specularColor** | specularColor | specularColor | refl_color | specular_color | refl_color | reflectionColor |
| **specularRoughness** | specularRoughness | specularRoughness | refl_roughness | specular_roughness | refl_roughness | reflectionGlossiness |
| **specularAnisotropy** | specularRoughnessAnisotropy | specularAnisotropy | refl_aniso | specular_roughness_anisotropy | refl_aniso | anisotropy |
| **ior** | specularIOR | specularIOR | refl_ior | specular_ior | refl_ior | refractionIOR |
| **transmissionWeight** | transmissionWeight | transmission | refr_weight | transmission_weight | refr_weight | refractionColorAmount |
| **transmissionColor** | transmissionColor | transmissionColor | refr_color | transmission_color | refr_color | refractionColor |
| **opacity** | geometryOpacity | opacity | opacity_color | geometry_opacity | opacity_color | opacityMap |
| **thinWalled** | geometryThinWalled | thinWalled | refr_thin_walled | geometry_thin_walled | refr_thin_walled | refrThinWalled |
| **subsurfaceWeight** | subsurfaceWeight | subsurface | ms_amount | subsurface_weight | ms_amount | translucencyAmount |
| **subsurfaceColor** | subsurfaceColor | subsurfaceColor | ms_color0 | subsurface_color | ms_color | translucencyColor |
| **subsurfaceRadius** | subsurfaceRadius | subsurfaceRadius | ms_radius0 | subsurface_radius | ms_radius | - |
| **subsurfaceScale** | subsurfaceRadiusScale | subsurfaceScale | ms_radius_scale | subsurface_radius_scale | ms_radius_scale | - |
| **coatWeight** | coatWeight | coat | coat_weight | coat_weight | coat_weight | coatColorAmount |
| **coatColor** | coatColor | coatColor | coat_color | coat_color | coat_color | coatColor |
| **coatRoughness** | coatRoughness | coatRoughness | coat_roughness | coat_roughness | coat_roughness | coatGlossiness |
| **coatIor** | coatIOR | coatIOR | coat_ior | coat_ior | coat_ior | coatIor |
| **fuzzWeight** | fuzzWeight | sheen | sheen_weight | fuzz_weight | sheen_weight | sheenColorAmount |
| **fuzzColor** | fuzzColor | sheenColor | sheen_color | fuzz_color | sheen_color | sheenColor |
| **fuzzRoughness** | fuzzRoughness | sheenRoughness | sheen_roughness | fuzz_roughness | sheen_roughness | sheenGlossiness |
| **emissionWeight** | emissionLuminance | emission | emission_weight | emission_luminance | emission_weight | - |
| **emissionColor** | emissionColor | emissionColor | emission_color | emission_color | emission_color | illumColor |

### 1.2 属性传递循环中跳过的属性

以下通用属性**不**经过主属性传递循环，由专门模块处理：

| 属性 | 处理模块 | 原因 |
|---|---|---|
| `normal_bump` | `_convert_bump_normal()` | 需要创建 bump/normal 节点或映射材质内联属性 |
| `displacementScale` | `_convert_displacement()` | 需要创建置换节点 |
| `displacementTexture` | `_convert_displacement()` | 需要创建置换节点 |

### 1.3 值传递规则

- **纹理连接**：通过 `_smart_connect()` 迁移，先尝试直连，失败则依次回退到 `outColor`、`outAlpha`，解决类型不兼容
- **Alpha Is Luminance**：属性传递完成后，按目标配置的**实际属性名**扫描目标材质所有连接，并**递归追踪上游**（穿越 CC/ramp/layeredTexture/bump 等中间节点），若发现链条中使用 `outAlpha` 输出，自动开启源纹理节点的 `alphaIsLuminance`（Redshift 跳过；opacity 透明度通道豁免，避免误开真实 alpha 贴图）
- **数值**：直接复制（float/int）；若目标属性为 `float3`/`double3`（如 Arnold `opacity`/`subsurfaceRadius`、V-Ray `opacityMap`、Redshift `ms_radius`），自动广播为 (v, v, v)
- **颜色值**：直接复制（tuple/list，长度 >= 3）；若目标属性为 float，自动回退取第一个通道值
- **连接链**：如果源属性连接来自 CC 节点，CC 节点会被转换并重新连接；中间节点（ramp、layeredTexture、multiplyDivide 等）保留

### 1.4 黑色颜色自动归零

当源材质中某颜色属性的值为 `(0, 0, 0)` 且**无纹理连接**时，自动将对应的权重属性置为 0，避免通道意外激活：

| 颜色属性 | 对应权重属性 |
|---|---|
| baseColor | baseColorWeight |
| specularColor | specularWeight |
| transmissionColor | transmissionWeight |
| subsurfaceColor | subsurfaceWeight |
| coatColor | coatWeight |
| fuzzColor | fuzzWeight |
| emissionColor | emissionWeight |

**触发条件（三个条件同时满足）：**

1. 颜色值为纯黑 `(0, 0, 0)`
2. 颜色属性无纹理连接（纯数值非贴图）
3. 对应权重值 > 0

> 例如：VRayMtl 的 `sheenColor=(0,0,0)` 但 `sheenColorAmount=1.0`，转换后目标材质的 `fuzzWeight` 会被置为 0。

此处理在属性传递之前执行，与目标渲染器无关。

> 颜色-权重配对关系定义在 `config/material/common.json` 的 `color_weight_pairs` 数组中，新增配对只需修改该 JSON，无需改 Python 代码。

### 1.5 渲染器特定前提条件

属性传递前自动设置：

| 渲染器 | 前提属性 | 值 |
|---|---|---|
| RedshiftMaterial | `refl_brdf` | `1` |
| RedshiftMaterial | `coat_brdf` | `1` |
| RedshiftMaterial（metallic） | `refl_fresnel_mode` | `2` |
| VRayMtl（roughness） | `useRoughness` | `1` |
| VRayMtl（默认反射） | `reflectionColor` | `[1, 1, 1]` |

---

## 二、凹凸/法线转换

### 2.1 转换流程

```
源 bump 节点 → [源配置] → 通用格式 {scale, input_plug, is_normal} → [目标配置] → 目标 bump 节点或材质属性
```

### 2.2 各渲染器配置

| 渲染器 | 凹凸模式 | 凹凸节点 | 法线模式 | 法线节点 | Scale 属性 | 输入属性 |
|---|---|---|---|---|---|---|
| **Arnold** | 独立节点 | `aiBump2d` | 独立节点 | `aiNormalMap` | bump: `bumpHeight` / nrm: `strength` | bump: `bumpMap` / nrm: `input` |
| **Redshift** | 独立节点 | `RedshiftBumpMap` | 同节点 | `RedshiftBumpMap` | `scale` | `input` |
| **Maya** | 独立节点 | `bump2d` | 同节点 | `bump2d` | `bumpDepth` | `bumpValue` |
| **V-Ray** | 材质内嵌 | _无_ | 材质内嵌 | _无_ | `bumpMult` | `bumpMap` |

### 2.3 模式判定

- **独立不同类型**（Arnold）：节点类型直接判定（`aiBump2d` → bump，`aiNormalMap` → normal）
- **共享类型**（Redshift `RedshiftBumpMap`、Maya `bump2d`）：通过 `inputType` / `bumpInterp` 属性值判定（0=bump，1=normal）
- **材质内嵌**（V-Ray）：通过 `bumpMapType` 属性值判定（0=bump，1=normal）

### 2.4 材质内嵌 ↔ 独立节点互转

- **材质内嵌 → 独立节点**：从源材质读取 `bumpMap` 输入 + `bumpMult` scale + `bumpMapType` 模式。创建目标 bump 节点，设置正确模式，连接到目标材质 `normal_bump` 属性
- **独立节点 → 材质内嵌**：读取源 bump 节点的输入 + scale + 模式。直接写入目标材质的 `bumpMap`/`bumpMult`/`bumpMapType`。旧 bump 节点保留（不删除）
- **独立节点 → 独立节点**：创建目标类型的新 bump 节点。复制 scale + 输入连接。设置模式属性。连接到目标材质

### 2.5 节点命名

新 bump/normal 节点命名：`{源节点名}_{渲染器缩写}{Bump|Nrm}`

- `bump_Material` → Redshift bump → `bump_Material_rsBump`
- `nrm_Material` → Arnold normal → `nrm_Material_aiNrm`

### 2.6 跨渲染器 Bump 识别

转换器可识别**所有**渲染器的 bump/normal 节点，不限于源材质类型。连接在 Arnold 材质上的 Maya `bump2d` 节点会被正确识别，并用 Maya 配置读取属性。

---

## 三、颜色校正转换

### 3.1 转换流程

```
源 CC 节点 → [源配置] → 通用格式 {gamma, contrast, gain, hue, saturation} → [目标配置] → 目标 CC 节点
```

### 3.2 各渲染器配置

| 渲染器 | CC 节点类型 | 输入属性 | 输出属性 | Hue 属性 | Hue 范围 |
|---|---|---|---|---|---|
| **Maya** | `colorCorrect` | `inColor` | `outColor` | `hueShift` | [0, 360] |
| **Arnold** | `aiColorCorrect` | `input` | `outColor` | `hueShift` | [-1, 1] |
| **Redshift** | `RedshiftColorCorrection` | `input` | `outColor` | `hue` | [0, 360] |
| **V-Ray** | `VRayColorCorrection` | `texture_map` | `outColor` | `hue_shift` | [-180, 180] |

### 3.3 Hue 归一化

所有 hue 值统一转换为**通用偏移角 [-180, 180]**(`0` = 无变化),基于各渲染器的中性点(`config/colorCorrection.json` 中的 `hue_center`)：

| 渲染器 | 属性 | 范围 | 中性点（无变化） | → 通用偏移角 |
|---|---|---|---|---|
| **Maya** | `colorCorrect.hueShift` | [0, 360] | 180 | `v - 180` |
| **Arnold** | `aiColorCorrect.hueShift` | [-1, 1] | 0（偏移型） | `v * 180` |
| **Redshift** | `ColorCorrection.hue` | [0, 360] | 0 | `v`（折回 [-180, 180]） |
| **V-Ray** | `hue_shift` | [-180, 180] | 0（偏移型） | `v` |

通用偏移角 → 目标值：

| 目标 | 换算 |
|---|---|
| Maya | `(offset + 180) % 360` |
| Arnold | `offset / 180` |
| Redshift | `offset % 360` |
| V-Ray | `offset` |

示例：Redshift `hue=0`（无变化）→ Arnold `hueShift=0`；Redshift `hue=90` → Arnold `hueShift=0.5`；Redshift `hue=270` → Arnold `hueShift=-0.5`。

### 3.4 CC 上游检测

两种检测策略：

1. **直连检测**：材质属性直接连接到 CC 节点时立即识别
2. **上游搜索**（`listHistory()`）：材质属性连接了中间节点（layeredTexture、ramp、multiplyDivide 等）时，扫描整条上游历史寻找 CC 节点

### 3.5 多通道共用去重

如果同一个源 CC 节点驱动多个材质通道（如 baseColor + subsurfaceColor），转换器仅创建**一个**目标 CC 节点并连接到所有下游中间节点，不会重复创建。

### 3.6 连接链保留

当 CC 节点位于纹理和中间节点之间时：

```
file → CC → layeredTexture → 材质
```

新 CC 插入到相同位置：

```
file → 新CC → layeredTexture → 材质
```

当中间节点**与源材质共享**（源材质属性仍连接 `layeredTexture.outColor`）时，新 CC 接管中间节点输入之前，先把源材质属性改接回原 CC 输出——**源材质链永不被目标渲染器节点污染**：

```
file → 原CC → 源材质        （源链保持完整）
file → 新CC → layeredTexture → 目标材质
```

无中间节点（CC 直连材质）时，新 CC 直接连接目标材质属性。

### 3.7 节点命名

新 CC 节点命名：`{源CC名}_{渲染器缩写}`

- `cc_test_color` → Redshift → `cc_test_color_rs`
- `CC_sofa_sss` → Arnold → `CC_sofa_sss_ai`

### 3.8 目标渲染器无 CC 支持

如果目标渲染器无 CC 节点配置，跳过 CC 转换，纹理直接连接到目标材质属性。

---

## 四、置换转换

### 4.1 转换流程

```
源 SG.displacementShader → 通过源配置读取纹理 + scale → 创建目标置换节点或原生 displacementShader → 连接到 SG
```

### 4.2 各渲染器配置

| 渲染器 | 置换节点类型 | 纹理属性 | Scale 属性 | 输出属性 |
|---|---|---|---|---|
| **Arnold** | 原生 `displacementShader` | `displacement` | `scale` | `displacement` |
| **Redshift** | `RedshiftDisplacement` | `texMap` | `scale` | `out` |
| **V-Ray** | 原生 `displacementShader` | `displacement` | `scale` | `displacement` |

### 4.3 转换规则

| 源 | 目标 | 行为 |
|---|---|---|
| Arnold | V-Ray | **跳过** — 双方共用原生 `displacementShader`（节点不变） |
| V-Ray | Arnold | **跳过** — 双方共用原生 `displacementShader` |
| 任意 | Redshift | 创建 `RedshiftDisplacement` 节点，连接到 SG |
| Redshift | Arnold | 读取 `RedshiftDisplacement` 的 texMap + scale，创建原生 `displacementShader`，连接到 SG |
| Redshift | V-Ray | 读取 `RedshiftDisplacement` 的 texMap + scale，创建原生 `displacementShader`，连接到 SG |

### 4.4 输出属性适配

不同置换节点使用不同输出属性名。转换器按优先级尝试连接：

1. `outDisplacement`（Arnold displacementShader）
2. `out`（RedshiftDisplacement）
3. `outColor`（回退）

### 4.5 节点命名

新置换节点命名：`{源材质名}_{渲染器缩写}Disp`

- `M_sofa` → Redshift → `M_sofa_rsDisp`
- `M_sofa` → Arnold/V-Ray → `M_sofa_aiDisp` / `M_sofa_vrayDisp`

Arnold ↔ V-Ray 互转时不创建置换节点（跳过）。

---

## 五、节点创建与 Hypershade 注册

所有节点类型均使用 `cmds.shadingNode()` 创建，确保自动注册到 Hypershade：

| 节点类型 | shadingNode 模式 |
|---|---|
| 材质 | `asShader=True` |
| 凹凸/法线 | `asUtility=True` |
| 颜色校正 | `asUtility=True` |
| 置换 | `asUtility=True` |

---

## 六、旧节点处理

转换后的**材质**、**凹凸/法线节点**、**颜色校正节点**、**置换节点**均**保留在场景中**并断开与 shadingEngine 的连接，**不会删除**，便于手动对比或回滚。

---

## 七、纹理连接兼容性

所有纹理连接均通过 `_smart_connect()` 处理，按顺序尝试三种连接方式：

1. **直连**：`cmds.connectAttr(src_plug, dst_plug, force=True)`
2. **outColor**：`src_node.outColor → dst_plug`（解决 float → color 类型不兼容）
3. **outAlpha**：`src_node.outAlpha → dst_plug`（解决 alpha → float 类型不兼容）

---

## 八、批量转换

UI 支持同时批量转换多个材质：

1. 在 Hypershade 中选中材质或在视口中选中物体
2. 工具自动识别每个材质的渲染器类型
3. 已是目标类型的材质自动跳过
4. 其余材质依次转换
5. 转换完成后自动选中新创建的材质

---
