# PBR Material Converter — Conversion Specification

**English** | [简体中文](CONVERSION_SPEC_zh.md)

## Overview

Converts materials between Arnold, Redshift, and V-Ray via a **universal PBR attribute format**.
All mappings are defined in `config/` JSON files with zero hardcoded attribute names in Python code.

**Conversion Flow:**

```
Source material attributes → [Source config] → Universal format → [Target config] → Target material attributes
```

**Supported Material Types:**

| Renderer | Material Type | Naming Suffix |
|---|---|---|
| Arnold | `aiStandardSurface` | `_aiStd` |
| Arnold | `aiOpenPBRSurface` | `_aiPBR` |
| Redshift | `RedshiftMaterial` | `_rsStd` |
| Redshift | `RedshiftOpenPBRMaterial` | `_rsPBR` |
| Redshift | `RedshiftStandardMaterial` | `_rsStdMat` |
| V-Ray | `VRayMtl` | `_vray` |

---

## 1. Main Material Attributes

### 1.1 Full Mapping Table

Columns: aiOpenPBR / aiStandardSurface / RedshiftMaterial / RedshiftOpenPBRMaterial / RedshiftStandardMaterial / VRayMtl
`-` indicates unsupported by that renderer.

| Universal Attribute | aiOpenPBR | aiStd | RS Material | RS OpenPBR | RS StdMat | VRayMtl |
|---|---|---|---|---|---|---|
| **baseColor** | baseColor | baseColor | diffuse_color | base_color | base_color | color |
| **baseColorWeight** | baseWeight | base | diffuse_weight | base_weight | base_color_weight | diffuseColorAmount |
| **metallic** | baseMetalness | metalness | refl_metalness | base_metalness | metalness | metalness |
| **roughness** | baseDiffuseRoughness | diffuseRoughness | diffuse_roughness | base_diffuse_roughness | diffuse_roughness | roughnessAmount |
| **specularWeight** | specularWeight | specular | refl_weight | specular_weight | refl_weight | reflectionColorAmount |
| **specularColor** | specularColor | specularColor | refl_color | specular_color | refl_color | reflectionColor |
| **specularRoughness** | specularRoughness | specularRoughness | refl_roughness | specular_roughness | refl_roughness | reflectionGlossiness * |
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
| **coatRoughness** | coatRoughness | coatRoughness | coat_roughness | coat_roughness | coat_roughness | coatGlossiness * |
| **coatIor** | coatIOR | coatIOR | coat_ior | coat_ior | coat_ior | coatIor |
| **fuzzWeight** | fuzzWeight | sheen | sheen_weight | fuzz_weight | sheen_weight | sheenColorAmount |
| **fuzzColor** | fuzzColor | sheenColor | sheen_color | fuzz_color | sheen_color | sheenColor |
| **fuzzRoughness** | fuzzRoughness | sheenRoughness | sheen_roughness | fuzz_roughness | sheen_roughness | sheenGlossiness * |
| **emissionWeight** | emissionLuminance | emission | emission_weight | emission_luminance | emission_weight | - |
| **emissionColor** | emissionColor | emissionColor | emission_color | emission_color | emission_color | illumColor |

> `*` VRayMtl's `reflectionGlossiness` / `coatGlossiness` / `sheenGlossiness` store **glossiness** (the `1 - x` of roughness). When the source material has `useRoughness=0` (glossiness mode) they are inverted as `1 - x` before transfer; with `useRoughness=1` the attribute already holds roughness and is not inverted. Declared in `config/material/VRayMtl.json` under `material.invert` (see 1.5). `roughness` (`roughnessAmount`) is a genuine roughness and is not inverted.

### 1.2 Attributes Skipped in Transfer Loop

These universal attributes are **not** processed in the main transfer loop — they are handled by dedicated modules:

| Attribute | Handler | Reason |
|---|---|---|
| `normal_bump` | `_convert_bump_normal()` | Requires bump/normal node creation or material attribute mapping |
| `displacementScale` | `_convert_displacement()` | Requires displacement node creation |
| `displacementTexture` | `_convert_displacement()` | Requires displacement node creation |

### 1.3 Value Transfer Rules

- **Texture connections**: Migrated via `_smart_connect()` — tries direct connection first, falls back to `outColor` then `outAlpha` for type incompatibility
- **Alpha Is Luminance**: After attribute transfer, scans target material connections using the **actual attribute names** from the target config and **recursively traces upstream** (through intermediate nodes like CC/ramp/layeredTexture/bump); if an `outAlpha` output is found in the chain, automatically enables `alphaIsLuminance` on the source texture node (skipped for Redshift; `opacity` channel is exempt to avoid enabling luminance on genuine alpha maps). A **non-opacity** channel hit records an `issue`, since enabling it changes the texture's semantics and must stay visible
- **Numeric values**: Copied directly (float/int); **non-finite** values (NaN / Inf) are refused and recorded as an `issue` (Maya accepts NaN silently, producing render artefacts); if the target attribute is `float3`/`double3` (e.g., Arnold `opacity`/`subsurfaceRadius`, V-Ray `opacityMap`, Redshift `ms_radius`), the value is broadcast to all three channels `(v, v, v)`
- **Color values**: Copied directly (tuple/list, length >= 3); if target attribute is float, falls back to first channel value
- **Source inversion**: If the source config declares a common attribute under `material.invert`, it is inverted as `1 - x` — scalars in place; texture/CC connections get a Maya `reverse` node inserted on the edge into the target plug (source network untouched)
- **Failure classification**: **Critical** channel failures (prerequisites / CC chains / bump-normal / displacement) fail the whole material and abort the conversion (`reason` + `converted=False`); **non-critical** failures (single attribute / emission / alphaIsLuminance / reverse) go into `ConversionResult.issues` (`converted` stays True, summarized as `with_issues`)
- **Anisotropy sign is not mappable**: `specularAnisotropy` is unsigned `[0, 1]` on Arnold / RedshiftOpenPBR, while V-Ray / RedshiftMaterial allow `[-1, 1]` (negative stretches along the x/u axis). When the source is negative and the target unsigned the value cannot be mapped: it is handled as a non-critical failure (recorded in `issues`, `converted` stays True) and the direction is lost; `rotation` is not converted either
- **Connection chains**: If source attribute connects from a CC node, the CC node is converted and reconnected; intermediate nodes (ramp, layeredTexture, multiplyDivide, etc.) are preserved

### 1.4 Black Color Auto-Zeroing

When a source material color attribute value is `(0, 0, 0)` with **no texture connection**, the corresponding weight attribute is automatically set to 0 to prevent unintended channel activation:

| Color Attribute | Corresponding Weight |
|---|---|
| baseColor | baseColorWeight |
| specularColor | specularWeight |
| transmissionColor | transmissionWeight |
| subsurfaceColor | subsurfaceWeight |
| coatColor | coatWeight |
| fuzzColor | fuzzWeight |
| emissionColor | emissionWeight |

**Trigger conditions (all three must be met):**

1. Color value is pure black `(0, 0, 0)`
2. Color attribute has no texture connection (pure value, not a texture)
3. Corresponding weight value > 0

> Example: VRayMtl with `sheenColor=(0,0,0)` but `sheenColorAmount=1.0` — target material's `fuzzWeight` will be set to 0.

This processing runs before attribute transfer, regardless of target renderer.

> Color-weight pairings are defined in `config/material/common.json`'s `color_weight_pairs` array. Adding new pairs only requires modifying that JSON, no Python code changes.

### 1.5 Renderer-Specific Prerequisites

Automatically set on the **target material** before attribute transfer:

| Renderer | Prerequisite Attribute | Value |
|---|---|---|
| RedshiftMaterial | `refl_brdf` | `1` |
| RedshiftMaterial | `coat_brdf` | `1` |
| RedshiftMaterial (metallic) | `refl_fresnel_mode` | `2` |
| VRayMtl (roughness) | `useRoughness` | `1` |
| VRayMtl (default reflection) | `reflectionColor` | `[1, 1, 1]` |
| VRayMtl (subsurface) | `translucencyMode` | `6` (new SSS) |

> In V-Ray 7, `sssOn` is the **Legacy SSS** switch (that is its AE label, and the
> control is hidden in the default state), **not** a generic SSS toggle: turning it
> on switches to the legacy SSS implementation, where `translucencyAmount` is
> hidden/ignored (legacy uses `scatterCoeff` / `thickness` instead). The target
> therefore sets **only** `translucencyMode = 6` (new SSS) and leaves `sssOn` at
> its default off.

On the **source material** side, glossiness→roughness inversion is declared via `material.invert` (see 1.3): VRayMtl's `useRoughness` decides whether its glossiness attributes are interpreted as glossiness or roughness — the target is forced to `useRoughness=1`, while the source is inverted according to its actual value.

---

## 2. Bump/Normal Conversion

### 2.1 Conversion Flow

```
Source bump node → [Source config] → Universal format {scale, input_plug, is_normal} → [Target config] → Target bump node or material attribute
```

### 2.2 Renderer Configurations

| Renderer | Bump Mode | Bump Node | Normal Mode | Normal Node | Scale Attribute | Input Attribute |
|---|---|---|---|---|---|---|
| **Arnold** | Standalone | `aiBump2d` | Standalone | `aiNormalMap` | bump: `bumpHeight` / nrm: `strength` | bump: `bumpMap` / nrm: `input` |
| **Redshift** | Standalone | `RedshiftBumpMap` | Same node | `RedshiftBumpMap` | `scale` | `input` |
| **Maya** | Standalone | `bump2d` | Same node | `bump2d` | `bumpDepth` | `bumpValue` |
| **V-Ray** | Embedded | _none_ | Embedded | _none_ | `bumpMult` | `bumpMap` |

### 2.3 Mode Detection

- **Standalone different types** (Arnold): Node type directly determines mode (`aiBump2d` → bump, `aiNormalMap` → normal)
- **Shared type** (Redshift `RedshiftBumpMap`, Maya `bump2d`): Determined by `inputType` / `bumpInterp` attribute value (0=bump, 1=tangent-space normal, 2=object-space normal; both normal modes count as normal)
- **Embedded** (V-Ray): Determined by `bumpMapType` attribute value (0=bump, 1=tangent-space normal, 2=object-space normal; both normal modes count as normal)

### 2.4 Embedded ↔ Standalone Node Conversion

- **Embedded → Standalone**: Reads source material `bumpMap` input + `bumpMult` scale + `bumpMapType` mode. Creates target bump node with correct mode, connects to target material `normal_bump` attribute
- **Standalone → Embedded**: Reads source bump node input + scale + mode. Writes directly to target material's `bumpMap`/`bumpMult`/`bumpMapType`. Old bump node preserved (not deleted)
- **Standalone → Standalone**: Creates new target type bump node. Copies scale + input connection. Sets mode attribute. Connects to target material

### 2.5 Node Naming

New bump/normal node naming: `{source_node_name}_{renderer_short}{Bump|Nrm}`

- `bump_Material` → Redshift bump → `bump_Material_rsBump`
- `nrm_Material` → Arnold normal → `nrm_Material_aiNrm`

### 2.6 Cross-Renderer Bump Detection

The converter can detect bump/normal nodes from **all** renderers, not limited to the source material type. A Maya `bump2d` node connected to an Arnold material will be correctly detected and read using the Maya configuration.

### 2.7 Legacy Redshift Normal Map Compatibility

Besides `RedshiftBumpMap`, Redshift ships a deprecated `RedshiftNormalMap` (texture path embedded in `tex0`, output `outDisplacementVector`), declared via `redshift.normal.extra_nodes` in `config/bumpNormal.json`:

- Detected as normal mode (a mapping with an embedded path is judged normal directly)
- Collection materializes the embedded path: it reuses the legacy node's existing `place2dTexture` (or creates `p2d_{node}`) and builds a `file` node (`tex_{node}`, `fileTextureName = tex0`), using `file.<file_source>` as the generic `input_plug`; downstream logic is unchanged
- Same-renderer reuse resolves the source node's real `output` (`outDisplacementVector` for the legacy node) when reconnecting
- `repeats`/`wrap`/`uvSet`/`flipY`/`unbiasedNormalMap` are not transferred and no color space is set; an empty `tex0` creates no nodes and is treated as a skip
- **Critical materialization failures** (file creation, `fileTextureName` write, or any `place2dTexture -> file` connection) log ERROR and fail the whole conversion (never a silent skip); nodes created before the failure are left in the scene

---

## 3. Color Correction Conversion

### 3.1 Conversion Flow

```
Source CC node → [Source config] → Universal format {gamma, contrast, gain, hue, saturation} → [Target config] → Target CC node
```

### 3.2 Renderer Configurations

| Renderer | CC Node Type | Input Attribute | Output Attribute | Hue Attribute | Hue Range |
|---|---|---|---|---|---|
| **Maya** | `colorCorrect` | `inColor` | `outColor` | `hueShift` | [0, 360] |
| **Arnold** | `aiColorCorrect` | `input` | `outColor` | `hueShift` | [-1, 1] |
| **Redshift** | `RedshiftColorCorrection` | `input` | `outColor` | `hue` | [0, 360] |
| **V-Ray** | `VRayColorCorrection` | `texture_map` | `outColor` | `hue_shift` | [-180, 180] |

### 3.3 Hue Normalization

All hue values are converted to a **universal offset angle [-180, 180]** (`0` = no change), based on each renderer's neutral point (`hue_center` in `config/colorCorrection.json`):

| Renderer | Attribute | Range | Neutral (no change) | → Universal offset |
|---|---|---|---|---|
| **Maya** | `colorCorrect.hueShift` | [0, 360] | 180 | `v - 180` |
| **Arnold** | `aiColorCorrect.hueShift` | [-1, 1] | 0 (offset type) | `v * 180` |
| **Redshift** | `ColorCorrection.hue` | [0, 360] | 0 | `v` (wrapped to [-180, 180]) |
| **V-Ray** | `hue_shift` | [-180, 180] | 0 (offset type) | `v` |

Universal offset → target value:

| Target | Conversion |
|---|---|
| Maya | `(offset + 180) % 360` |
| Arnold | `offset / 180` |
| Redshift | `offset % 360` |
| V-Ray | `offset` |

Examples: Redshift `hue=0` (no change) → Arnold `hueShift=0`; Redshift `hue=90` → Arnold `hueShift=0.5`; Redshift `hue=270` → Arnold `hueShift=-0.5`.

### 3.4 CC Upstream Detection

Two detection strategies:

1. **Direct connection**: Immediately detected when material attribute is directly connected to a CC node
2. **Upstream search** (`listHistory()`): When material attribute connects through intermediate nodes (layeredTexture, ramp, multiplyDivide, etc.), scans the entire upstream history for CC nodes

### 3.5 Multi-Channel Deduplication

If the same source CC node drives multiple material channels (e.g., baseColor + subsurfaceColor), the converter creates only **one** target CC node and connects it to all downstream intermediate nodes.

### 3.6 Connection Chain Preservation

The conversion branches on the topology between the source CC and the material
attribute, and the **source network is never rewritten**:

| Topology | Structure | Handling |
|---|---|---|
| `direct` | `file → CC → material` | The new CC is **always wired to the target attribute on its own** (never left to the CC's existing downstream list); the source CC's other non-material downstream nodes follow the new CC and the source material is re-pointed at its own CC. When the source chain drives a scalar channel through `outAlpha`, the new CC uses the same output slot first and falls back through `smart_connect` |
| `single_hop` | `file → CC → layeredTexture/ramp → material` | The intermediate node is **copied** (one level only); the new CC feeds the copy and the copy feeds the target attribute. The source node and its parameters stay untouched |
| `unsupported` | two or more intermediate levels, or the CC input slot cannot be located | No target CC is created and no source connection is rewritten; reported as an explicit limitation in the result `issues` |

The copy only rewires the "new CC → copy" input; every other layer parameter
(`inputs[*].color`, `blendMode`, ...) is duplicated with the node:

```
file → originalCC → layeredTexture → source material      (unchanged)
file → newCC → layeredTexture_conv → target material
```

Without an intermediate node (CC directly on the material), the new CC is
**always wired to the target attribute on its own** (never left to the source
CC's existing downstream list); any other non-material downstream node of the
source CC follows the new CC, and the source material is re-pointed at its own
CC. When the source chain drives a scalar channel through `outAlpha`, the new CC
uses the same output slot first and falls back through `smart_connect`.

> Older versions re-pointed the source attribute straight back at the original CC
> (bypassing the layeredTexture), which silently dropped the source material's
> intermediate processing. That behaviour is gone.

### 3.7 Node Naming

New CC node naming: `{source_CC_name}_{renderer_short}`

- `cc_test_color` → Redshift → `cc_test_color_rs`
- `CC_sofa_sss` → Arnold → `CC_sofa_sss_ai`

### 3.8 No CC Support in Target Renderer

If the target renderer has no CC node configuration, CC conversion is skipped and texture connects directly to target material attribute.

---

## 4. Displacement Conversion

### 4.1 Conversion Flow

```
Source SG.displacementShader → Read texture + scale via source config → Create target displacement node or native displacementShader → Connect to SG
```

### 4.2 Renderer Configurations

| Renderer | Displacement Node Type | Texture Attribute | Scale Attribute | Output Attribute |
|---|---|---|---|---|
| **Arnold** | Native `displacementShader` | `displacement` | `scale` | `displacement` |
| **Redshift** | `RedshiftDisplacement` | `texMap` | `scale` | `out` |
| **V-Ray** | Native `displacementShader` | `displacement` | `scale` | `displacement` |

### 4.3 Conversion Rules

| Source | Target | Behavior |
|---|---|---|
| Arnold | V-Ray | **Skip** — both use native `displacementShader` (node unchanged) |
| V-Ray | Arnold | **Skip** — both use native `displacementShader` |
| Any | Redshift | Create `RedshiftDisplacement` node, connect to SG |
| Redshift | Arnold | Read `RedshiftDisplacement` texMap + scale, create native `displacementShader`, connect to SG |
| Redshift | V-Ray | Read `RedshiftDisplacement` texMap + scale, create native `displacementShader`, connect to SG |

### 4.4 Output Attribute Adaptation

Different displacement nodes use different output attribute names. The converter tries connections in priority order:

1. `outDisplacement` (Arnold displacementShader)
2. `out` (RedshiftDisplacement)
3. `outColor` (fallback)

### 4.5 Node Naming

New displacement node naming: `{source_material_name}_{renderer_short}Disp`

- `M_sofa` → Redshift → `M_sofa_rsDisp`
- `M_sofa` → Arnold/V-Ray → `M_sofa_aiDisp` / `M_sofa_vrayDisp`

Arnold ↔ V-Ray conversion does not create displacement nodes (skipped).

### 4.6 Multi-Shading-Engine Displacement

Displacement lives on the **shading engine**, not on the material. When a
material feeds several shading engines, conversion now runs **per SG**: the
converter enumerates every `shadingEngine` fed by the source material and
converts displacement on each one. SGs that share the same source displacement
(same texture plug + scale) reuse a single target displacement node; SGs with
their own displacement each get their own converted node.

---

## 5. Node Creation & Hypershade Registration

All node types are created using `cmds.shadingNode()` to ensure automatic Hypershade registration:

| Node Type | shadingNode Mode |
|---|---|
| Material | `asShader=True` |
| Bump/Normal | `asUtility=True` |
| Color Correction | `asUtility=True` |
| Displacement | `asUtility=True` |

---

## 6. Old Node Handling

Converted **materials**, **bump/normal nodes**, **color correction nodes**, and **displacement nodes** are **preserved in the scene** and disconnected from shadingEngine — **not deleted**, for manual comparison or rollback.

---

## 7. Texture Connection Compatibility

All texture connections are handled via `_smart_connect()`, trying three connection methods in order:

1. **Direct**: `cmds.connectAttr(src_plug, dst_plug, force=True)`
2. **outColor**: `src_node.outColor → dst_plug` (resolves float → color type incompatibility)
3. **outAlpha**: `src_node.outAlpha → dst_plug` (resolves alpha → float type incompatibility)

---

## 8. Batch Conversion

UI supports batch conversion of multiple materials:

1. Select materials in Hypershade or objects in viewport
2. Tool auto-detects each material's renderer type
3. Materials already in target type are automatically skipped
4. Remaining materials are converted sequentially
5. Newly created materials are automatically selected after conversion

**Result semantics** (see `core/results.py`): each material produces a
`ConversionResult` (`created` / `converted` / `wired` / `total_sgs` /
`skipped` / `reason`). A conversion whose shading-engine reconnection failed
for **every** SG is reported as failed (not a silent success), because the
scene would still render the old material. When the SG wiring **snapshot is
incomplete** (any slot failed to read) the conversion aborts **before** rewiring:
`reason` becomes `failed to snapshot shading engine wiring`, the unreadable slots
are listed in `sg_failures`, and the scene is left untouched (the result counts as
`unwired`: created but never wired). Because the commit is transactional (any
failure rolls back), `wired` is only `0` or `total_sgs`; `partial_wired` is a
reserved capability and currently unreachable, while the pre-rollback count is
reported through `wired_before_rollback`. Conversion run by `convert_all(...,
on_progress=...)` reports per-material progress to the UI, which repaints the
progress bar during the batch instead of after it completes.

---
