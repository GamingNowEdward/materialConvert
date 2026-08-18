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
| **specularRoughness** | specularRoughness | specularRoughness | refl_roughness | specular_roughness | refl_roughness | reflectionGlossiness |
| **specularAnisotropy** | specularRoughnessAnisotropy | specularAnisotropy | refl_aniso | specular_roughness_anisotropy | refl_aniso | anisotropy |
| **ior** | specularIOR | specularIOR | refl_ior | specular_ior | refl_ior | refractionIOR |
| **transmissionWeight** | transmissionWeight | transmission | refr_weight | transmission_weight | refr_weight | refractionColorAmount |
| **transmissionColor** | transmissionColor | transmissionColor | refr_color | transmission_color | refr_color | refractionColor |
| **opacity** | geometryOpacity | opacity | opacity_color | geometry_opacity | opacity_color | opacityMap |
| **thinWalled** | geometryThinWalled | thinWalled | refr_thin_walled | geometry_thin_walled | refr_thin_walled | refrThinWalled |
| **subsurfaceWeight** | subsurfaceWeight | subsurface | ms_amount | subsurface_weight | ms_amount | - |
| **subsurfaceColor** | subsurfaceColor | subsurfaceColor | ms_color0 | subsurface_color | ms_color | - |
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

### 1.2 Attributes Skipped in Transfer Loop

These universal attributes are **not** processed in the main transfer loop — they are handled by dedicated modules:

| Attribute | Handler | Reason |
|---|---|---|
| `normal_bump` | `_convert_bump_normal()` | Requires bump/normal node creation or material attribute mapping |
| `displacementScale` | `_convert_displacement()` | Requires displacement node creation |
| `displacementTexture` | `_convert_displacement()` | Requires displacement node creation |

### 1.3 Value Transfer Rules

- **Texture connections**: Migrated via `_smart_connect()` — tries direct connection first, falls back to `outColor` then `outAlpha` for type incompatibility
- **Alpha Is Luminance**: After attribute transfer, scans all target material connections; if `outAlpha` is used, automatically enables `alphaIsLuminance` on the source texture node (skipped for Redshift)
- **Numeric values**: Copied directly (float/int); if the target attribute is `float3`/`double3` (e.g., Arnold `opacity`/`subsurfaceRadius`, V-Ray `opacityMap`, Redshift `ms_radius`), the value is broadcast to all three channels `(v, v, v)`
- **Color values**: Copied directly (tuple/list, length >= 3); if target attribute is float, falls back to first channel value
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

Automatically set before attribute transfer:

| Renderer | Prerequisite Attribute | Value |
|---|---|---|
| RedshiftMaterial | `refl_brdf` | `1` |
| RedshiftMaterial | `coat_brdf` | `1` |
| RedshiftMaterial (metallic) | `refl_fresnel_mode` | `2` |
| VRayMtl (roughness) | `useRoughness` | `1` |
| VRayMtl (default reflection) | `reflectionColor` | `[1, 1, 1]` |
| VRayMtl (default reflection) | `reflectionColorAmount` | `1` |

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
- **Shared type** (Redshift `RedshiftBumpMap`, Maya `bump2d`): Determined by `inputType` / `bumpInterp` attribute value (0=bump, 1=normal)
- **Embedded** (V-Ray): Determined by `bumpMapType` attribute value (0=bump, 1=normal)

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

When a CC node sits between texture and intermediate nodes:

```
file → CC → layeredTexture → material
```

New CC is inserted at the same position:

```
file → newCC → layeredTexture → material
```

When the intermediate node is **shared with the source material** (source attribute still connected to `layeredTexture.outColor`), the source attribute is reconnected back to the original CC output before the new CC takes over the intermediate node input — the **source material chain is never polluted** with target-renderer nodes:

```
file → originalCC → source material      (source chain preserved)
file → newCC → layeredTexture → target material
```

Without intermediate nodes (CC directly connected to material), new CC connects directly to target material attribute.

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

---

## 9. Material Builder

Integrated in the Converter panel's second tab, builds complete Arnold / Redshift / V-Ray PBR materials from texture paths.

### 9.1 Supported Features

| Feature | Description |
|---|---|
| Material Type Dropdown | Lists **all** materials from `config/material/*.json` — adding a JSON file automatically adds a buildable type |
| Texture Paths | Optional input for Color, Roughness/Glossiness, Metallic, Normal/Bump, Displacement, Opacity, Transmission, Reflection, Sheen, SSS, Emission maps |
| Normal/Bump Toggle | Checked = Normal, unchecked = Bump |
| SSS | When checked, additionally creates sss channel (colorCorrect + layeredTexture + ramp) |
| Displacement | When checked, creates displacement node chain |
| Add To Quick Select Set | When checked, wraps all built nodes in a `QS_M_*` selection set |
| Create File From P2D | Creates file node from selected place2dTexture node and auto-connects |
| Full Pipeline Mode | When enabled, color channels use `colorCorrect + layeredTexture` and roughness uses `ramp`; when disabled, textures connect directly (Normal/Bump still create bump/normal nodes) |
| Glossiness | Treated as inverted roughness via the file node's `invert` attribute |


### 9.2 Config Source

The Builder reuses the **Convert configuration system** — no separate renderer spec file:

- Material node type / attribute mappings / plugin: `config/material/*.json` (`node_type`, `plugin`, section mappings)
- CC node: `config/colorCorrection.json`
- Bump/Normal node: `config/bumpNormal.json`
- Displacement chain: material JSON `displacement` block
- Naming conventions: `config/builder_naming.json`
- Material prerequisites (`useRoughness`, `refl_brdf`, etc.) are applied automatically from JSON

### 9.3 Batch Builder

A dedicated tab that builds many materials from a texture directory:

1. `core/texture_scanner.py` scans a directory (non-recursive) using `config/texture_channels.json`
2. Filenames are normalized (lowercase, `-`/space → `_`), then channels are matched longest-alias-first with token / underscore-tolerant matching
3. `core/batch_builder.py` converts parsed channels into `MaterialBuilder` short keys and calls `MaterialBuilder.build()`
4. The UI shows parsed + unparsed rows in one table (sortable `Status` column) and a `Materials to Build` preview list with per-material channel counts
5. Options include target material type, Full Pipeline toggle, and Add To Quick Select Set
6. Unparsed files are display-only and never built


---

## 10. Node Tools

Fourth tab providing batch node operations:

- Select nodes by type (material/file/bump/layeredTexture/CC), excluding default materials
- Batch set file node color space
- Auto match color space for selected file nodes (reference `config/colorSpace.json`)
- Batch rename Shading Engine (SG)

### 10.1 Auto Match Color Space Rules

Matching priority (high to low):

1. **Filename match** (highest): Checks if filename contains keywords in `filenameKeywords` (case-insensitive)
   - Example: `wood_basecolor.jpg` contains `basecolor` → matches `srgb` type
2. **Channel match** (secondary): BFS-traces **all** downstream connections of the file node — including single-channel plugs (`outColorR/G/B`), `outAlpha`, and traversal through intermediate nodes (colorCorrect, layeredTexture, multiplyDivide, bump/normal) — and checks the material attribute names reached at chain ends against the attribute keywords
   - Attribute names are **normalized** before matching (lowercase, `_`/`-` removed): `baseColor`, `base_color`, `basecolor` are equivalent
   - Keyword pool comes from `commonAttributeRoles` dynamically expanded with every renderer's actual attribute names from `config/material/*.json` (via `get_expanded_attribute_keywords()`), plus static `attributeKeywords` as fallback
   - Maya default render-list containers (`defaultTextureList` etc.) are skipped during tracing
   - Example: file → `multiplyDivide` → `mat.metalness` matches `raw`; file → `colorCorrect` → `layeredTexture` → `mat.baseColor` matches `srgb`
3. **Default type** (lowest): When no match, uses the type specified by `default` in `config/colorSpace.json` (currently `raw`)

After matching a type, iterates through the `aliases` list and sets the first color space name available in the current OCIO configuration.

### 10.2 Ambiguous Match Handling

When both filename match and channel match succeed **but return different roles**, the file node is treated as **ambiguous** and is **skipped** (color space left unchanged):

- The node is kept in the selection (`cmds.select(..., add=True)`) so it can be reviewed manually
- Script Editor prints the conflict, e.g.:
  `[歧义] C:\tex\my_metalness_color.png (fileNode): filename→srgb vs channel→raw, 已跳过, 请手动处理`
- Typical case: filenames containing `color` (e.g. `my_metalness_color.png`) match `srgb` by substring while the connected channel (`metalness`) resolves to `raw`
- Unambiguous nodes are still auto-matched normally (filename → channel → default)

---

## 11. Project Structure

```
materialConvert/
├── config/                          # JSON configuration files
│   ├── material/                    # Renderer material attribute mappings
│   │   ├── common.json              # Universal PBR parameter definitions
│   │   ├── aiStandardSurface.json
│   │   ├── aiOpenPBRSurface.json
│   │   ├── RedshiftMaterial.json
│   │   ├── RedshiftOpenPBRMaterial.json
│   │   ├── RedshiftStandardMaterial.json
│   │   └── VRayMtl.json
│   ├── bumpNormal.json              # Bump/normal node mappings
│   ├── colorCorrection.json         # Color correction node mappings
│   ├── colorSpace.json              # Color space auto-match rules
│   ├── texture_channels.json       # Batch Builder filename-to-channel rules
│   └── builder_naming.json          # Material Builder naming conventions
├── core/                            # Core engine
│   ├── converter.py                 # MaterialConverter dispatcher
│   ├── converters/                  # Business conversion modules
│   │   ├── attribute.py             # Attribute collection & transfer
│   │   ├── bump.py                  # Bump/normal conversion
│   │   ├── cc.py                    # Color correction conversion
│   │   └── displacement.py          # Displacement conversion
│   ├── config_loader.py             # JSON config parser
│   ├── node_utils.py                # Maya node utility functions (module-level)
│   ├── prerequisites.py             # Renderer prerequisite handling
│   ├── logger.py                    # Unified logging module
│   ├── builder_context.py           # Material Builder shared state & tools
│   ├── texture_scanner.py           # Directory scanning / filename-to-channel parsing
│   ├── batch_builder.py             # Batch build orchestration
│   └── material_builder.py          # Material Builder core logic (config-driven)
├── ui/                              # User interface
│   ├── converter_ui.py              # Main window (QTabWidget)
│   ├── styles.py                    # QSS dark theme styles
│   └── tabs/                        # Four functional tabs
│       ├── converter_tab.py         # Material conversion (with progress bar)
│       ├── builder_tab.py           # Material Builder
│       ├── batch_builder_tab.py    # Batch Builder
│       └── node_tools_tab.py        # Node Tools
├── main.py                          # Entry script
├── docs/
│   ├── AGENTS.md                    # AI Agent development guide
│   ├── CONVERSION_SPEC.md           # This document
│   ├── CONVERSION_SPEC_zh.md        # 中文版转换规格说明
│   └── README_zh.md                 # 中文版 README
├── CHANGELOG.md                     # Changelog
└── CHANGELOG_zh.md                  # 中文版更新日志
```
