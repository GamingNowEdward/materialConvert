# Renderer JSON Authoring Guide

**English** | [简体中文](CONFIG_GUIDE_zh.md)

## Overview

The tool's **attribute mapping is config-driven**: all renderer attribute mappings are defined in JSON files under `config/`, with zero hardcoded attribute names in Python code (conversion behavior itself is implemented in code). Adding support for a new renderer material = **adding JSON files, no business code changes required**.

**Data flow:**

```
Source material attributes → [Source JSON config] → Universal format → [Target JSON config] → Target material attributes
```

### The Three Files Involved

| File | Required | Purpose | Behavior When Missing |
|---|---|---|---|
| `config/material/<NodeType>.json` | **Required** | Material node metadata + attribute mapping + displacement config | The tool does not recognize the material at all |
| `config/bumpNormal.json` | Strongly recommended | Bump/normal node mappings (looked up by `renderer` key) | Bump/normal conversion is skipped |
| `config/colorCorrection.json` | Strongly recommended | Color correction (CC) node mapping (looked up by `renderer` key) | CC chain not converted; texture connects directly to target attributes |

> The `renderer` key is the link between the three configs: the value declared in the material JSON (e.g. `"vray"`) is used to look up the same-named section in `bumpNormal.json` and `colorCorrection.json`.

---

## The Universal Attribute System

All renderer attribute mappings use the **universal attribute names** defined in `config/material/common.json` as keys. This is the intermediate format of conversion: the source config translates Maya attributes into universal names, and the target config translates them back into the target renderer's Maya attributes.

### Universal Attribute Table

| Section | Universal Attributes |
|---|---|
| `base` | `baseColor`, `baseColorWeight`, `metallic`, `roughness` |
| `specular` | `specularWeight`, `specularColor`, `specularRoughness`, `specularAnisotropy`, `ior` |
| `transmission` | `transmissionWeight`, `transmissionColor` |
| `geometry` | `normal_bump`, `opacity`, `thinWalled` |
| `subsurface` | `subsurfaceWeight`, `subsurfaceColor`, `subsurfaceRadius`, `subsurfaceScale` |
| `coat` | `coatWeight`, `coatColor`, `coatRoughness`, `coatIor` |
| `fuzz` | `fuzzWeight`, `fuzzColor`, `fuzzRoughness` |
| `emission` | `emissionWeight`, `emissionColor` |
| `displacement` (dedicated block) | `displacementScale`, `displacementTexture` |

Notes:

- `normal_bump`, `displacementScale`, and `displacementTexture` are handled by dedicated conversion modules; the main attribute loop skips them
- Section names and keys in a new material JSON **must match the table above exactly** — extra keys are ignored, missing keys count as unsupported
- Color-weight pairings live in the `color_weight_pairs` array of `common.json` (e.g. `["baseColor", "baseColorWeight"]`) for logic such as black-color auto-zeroing; only modify it when introducing new universal attributes

---

## Step 1: Material Mapping JSON

### File Location and Naming

Create a new JSON file under `config/material/`. **The file name is not used for identification** (the program keys configs by `material.node_type`), but keeping it identical to `node_type` is strongly recommended for maintainability.

> The only reserved name is `common.json`, which the loader skips.

### The `material` Metadata Block

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

| Field | Required | Description |
|---|---|---|
| `node_type` | ✅ | Maya node type name, **must exactly match the real type (case-sensitive)**. It is also the primary key of the whole config system: conversion target selection, material identification, and the Builder dropdown all rely on it |
| `renderer` | ✅ | Renderer lookup key. Built-in values are `"arnold"`, `"redshift"`, and `"vray"`; custom renderer keys are allowed. Looks up sections in `bumpNormal.json` / `colorCorrection.json` and drives per-renderer logic such as Alpha Is Luminance |
| `uiPanel_display_name` | ✅ | Display name in UI dropdowns (falls back to `node_type` if absent) |
| `short_name` | Recommended | Naming suffix for converted materials: `{source_material}_{short_name}` (defaults to `"converted"`). Existing conventions: `aiStd` / `aiPBR` / `rsStd` / `rsPBR` / `rsStdMat` / `vray` |
| `plugin` | Recommended | Renderer plugin module name (e.g. `mtoa` / `redshift4maya` / `vrayformaya`). Used only by Debug validation: checks plugin load state; if not installed, the whole renderer group is SKIPped instead of misreported as spelling errors |
| `prerequisites` | Optional | Material-level prerequisites, see below |

### Attribute Mapping Sections

Every top-level object other than `material` is an attribute mapping section (`base` / `specular` / `transmission` / `geometry` / `subsurface` / `coat` / `fuzz` / `emission`):

```json
"base": {
  "baseColor": "color",
  "baseColorWeight": "diffuseColorAmount",
  "metallic": "metalness",
  "roughness": "roughnessAmount"
}
```

- **Key** = universal attribute name (see table above)
- **Value** = the real Maya attribute name on this material node
- **Empty string `""` as value** means the renderer does not support this attribute — the transfer loop skips it automatically (e.g. VRayMtl has no `emissionWeight`)

You may also **omit an entire section**, which is equivalent to writing `""` for every attribute in it.

### Prerequisites

Some renderers require toggles or default values before attribute mapping makes sense. Two levels are supported:

**1. Material-level** — inside the `material` block, applied every time a material converts to this type:

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

**2. Attribute-level** — inside an attribute mapping section, keyed by universal attribute name; executed only when that universal attribute is actually processed in the main loop:

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

> Example meaning: on RedshiftMaterial metallic only takes effect with `refl_fresnel_mode=2` (metal mode), so it is attached to the `metallic` attribute.

Format rules:

| Rule | Description |
|---|---|
| Format | `{ "descriptive_key": { "attribute": "...", "value": ... } }` |
| `value` as array | Set via multi-argument setAttr (broadcast to three channels, float3) |
| Empty `attribute` or null `value` | Silently skipped |
| Failure | Logged as WARN only; conversion continues |

### The `displacement` Block

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

| Field | Default | Description |
|---|---|---|
| `node_type` | `""` | Displacement node type. **Sentinel semantics**: `"displacementShader"` means "connect the texture directly to the SG's `displacementShader`", no new node created; any other type name triggers real node creation; empty means displacement unsupported |
| `displacementScale` | `""` | Strength attribute on the displacement node |
| `displacementTexture` | `""` | Input attribute receiving the texture on the displacement node |
| `file_source` | `outAlpha` | File node output used when connecting directly to the displacement node (grayscale maps usually take alpha) |
| `lyr_src` | `outAlpha` | Connection attribute from layeredTexture output to the displacement node in Builder full-chain mode. If the displacement input accepts color (e.g. Redshift `texMap`), set `outColor` |
| `output` | `displacement` | Output attribute from the displacement node to the shading engine (SG) |

Existing references: Arnold / V-Ray use the native `displacementShader` (sentinel path); Redshift uses a real `RedshiftDisplacement` node.

### Full Template

Copy and modify this template directly; placeholders are marked `<...>`:

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

### Real Example Excerpt

V-Ray's base/specular sections (note attribute name differences and handling of unsupported entries):

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

## Step 2: `bumpNormal.json` Renderer Section

Each renderer's `bump` / `normal` sections share one **unified field schema** (ordered by data-flow direction):

| Field | Description |
|---|---|
| `is_material_attribute` | `false` = standalone node mode (maya/arnold/redshift); `true` = material-embedded mode; no dedicated bump/normal node is created (V-Ray) |
| `node_type` | Node type for standalone mode; omitted in embedded mode |
| `input` | Input attribute receiving the upstream texture |
| `output` | Output attribute connecting downstream to the material; omitted in embedded mode |
| `scale` | Strength attribute |
| `is_normal` / `is_normal_value` | Optional, **must appear as a pair**; mode-switch attribute and its value in normal mode (Maya `bumpInterp`, Redshift `inputType`, V-Ray `bumpMapType` are all 0=bump / 1=normal) |
| `file_source` | Texture node output attribute (default `outColor`) |
| `default_scale` | Default strength applied by the Builder |

### The Three Modes

| Mode | Representative Renderer | Detection |
|---|---|---|
| Standalone nodes, different types | Arnold (`aiBump2d` / `aiNormalMap`) | Node type directly determines bump vs normal |
| Shared type | Maya (`bump2d`), Redshift (`RedshiftBumpMap`) | Same node type for both; distinguished by the `is_normal` switch value |
| Embedded in material | V-Ray (`bumpMap` + `bumpMult` + `bumpMapType`) | `is_material_attribute: true`; no separate node — read/write material attributes directly |

### Authoring Example

Redshift section (shared type — bump and normal are the same node type, differing only in `is_normal_value`):

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

### Notes

- The top-level `common` section only backfills missing fields as defaults; write out every field explicitly in new renderer sections instead of relying on fallbacks
- **Never add custom fields without consumers** — fields must be consumed by conversion/build code (the validator checks attribute spelling, not whether fields are used)
- Without a renderer section, bump/normal conversion involving that renderer is skipped entirely (source state preserved)
- The `maya` section matters too: native Maya bump nodes connected to materials in cross-renderer scenes rely on it for detection

---

## Step 3: `colorCorrection.json` Renderer Section

Each renderer section contains three sub-blocks:

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

| Sub-block | Fields | Description |
|---|---|---|
| `material` | `node_type` / `input` / `output` | CC node type, texture input attribute, output attribute |
| `base` | `gamma` / `contrast` / `gain` | Brightness-family controls; use empty strings for unsupported controls (e.g. V-Ray has no gamma control) |
| `color` | `hue` / `saturation` | Hue/saturation control attributes |
| `color` | `hue_range` / `hue_center` | Hue normalization parameters, see below |

### Hue Normalization Semantics

Hue attributes have different scales across renderers; conversion goes through a **universal offset angle [-180, 180]** (0 = no change):

- `hue_range`: legal value interval of the renderer's hue attribute
- `hue_center`: neutral point ("no change") in raw units. Offset-type attributes (Arnold/V-Ray) center at 0; absolute-type attributes (Maya [0,360]) center at 180

Conversion example: Redshift `hue=90` → universal offset 90 → Arnold `hueShift=0.5`.

### Fallback Behavior

Without a renderer section (or with empty `node_type`): the CC chain is not converted; textures connect directly to the target material attribute via `_smart_connect()`; all other attributes transfer normally.

---

## Verification Workflow

### 1. Manually Verify node_type

Maya node type names are case-sensitive; always verify before authoring:

```python
import maya.cmds as cmds
n = cmds.createNode("YourMaterialType")   # A warning "Unrecognized node type" means the name is wrong
cmds.delete(n)                             # Delete immediately after verification
```

### 2. Debug Config Validation (Recommended)

Run **Config Validation** from the Log tab: the validator creates temporary nodes in Maya and checks every JSON's `node_type` and all mapped attributes (including prerequisites and displacement) against real spelling, then cleans up the temporary nodes.

- Plugin not installed / fails to load → the entire renderer group is SKIPped, **never misreported as spelling errors**
- Results go into the unified log stream, filterable by level/source

### 3. Functional Regression

Pure Python tests run without Maya:

```
python -m pytest tests/ -v
```

Finally reload the tool in Maya and do a round-trip conversion test (materials with bump, CC, and displacement chains are the most representative).

---

## Boundaries & Notes

### Builder Auto-registration and Limitations

- New material JSON files **appear automatically in the Material Builder / Batch Builder dropdowns** — no registration needed
- However, the Builder only supports implemented channel strategies: `color` / `float` / `roughness` / `normal_bump` / `displacement`. New plain attributes still require extending Python chain-building functions; JSON alone is not enough
- Weight attributes for color channels derive from `color_weight_pairs` in `common.json` — no extra configuration needed

### colorSpace Auto-expansion

Attribute keywords used by color-space auto matching (Auto Match Selected) expand **dynamically** from all material JSON mappings; new renderers need no manual edits to `config/colorSpace.json`.

### Naming Suffix Conventions

Internally, code uses a fixed abbreviation map for naming new nodes:

```
arnold → ai    redshift → rs    vray → vray
```

E.g. bump nodes `{source}_{short}{Bump|Nrm}`, CC nodes `{sourceCC}_{short}`, displacement nodes `{sourceMaterial}_{short}Disp`. Driven by the `renderer` key; no configuration needed.

### Other Rules

- All nodes are created via `cmds.shadingNode(asShader=True/asUtility=True)` to guarantee Hypershade registration — this is code behavior, irrelevant while authoring JSON, but useful when debugging "new nodes invisible in Hypershade"
- Old nodes are never deleted after conversion, only disconnected from the shading engine

---

## Checklist

Complete list for adding a new renderer material type:

- [ ] Verified the real Maya node type name via `cmds.createNode` (case-sensitive)
- [ ] `config/material/<NodeType>.json`: `material` block contains `node_type` / `renderer` (built-in: arnold/redshift/vray) / `uiPanel_display_name`
- [ ] Attribute section keys match the universal attribute table exactly; unsupported entries use `""` or omit the section
- [ ] Attributes needing toggles/defaults have prerequisites configured (material-level or attribute-level)
- [ ] `displacement` block filled correctly per sentinel semantics (or confirmed unsupported)
- [ ] `bumpNormal.json` has a same-named `renderer` section (bump + normal), with the correct mode among the three
- [ ] `colorCorrection.json` has a same-named `renderer` section with `hue_range` / `hue_center` matching the renderer's scale
- [ ] Ran Log-tab Config Validation: no ERROR/WARN (whole-group SKIP due to missing plugins is normal)
- [ ] `python -m pytest tests/ -v` passes
- [ ] Round-trip conversion tested inside Maya (covering bump/CC/displacement chains)

---

## Troubleshooting

| Symptom | Root Cause |
|---|---|
| Conversion does nothing | `material.node_type` mismatches the real Maya type name (case-sensitive) |
| New material missing from dropdowns | JSON parse failure (check ConfigLoader ERROR logs); or file not under `config/material/` |
| Some attributes arrive empty | Value is `""` (treated as unsupported); or key mismatches the universal attribute table |
| Bump/normal not converted | Missing renderer section in `bumpNormal.json`, or its key differs from the material JSON's `renderer` value |
| CC chain not converted, texture direct-connected | Target renderer unconfigured in `colorCorrection.json` (expected degradation), or `node_type` empty |
| Validation reports attribute not existing | Mapped Maya attribute name misspelled; whole-group SKIP means the plugin isn't installed (normally ignored) |
| Hue conversion results off | `hue_range` / `hue_center` mismatch the renderer's actual scale |
| No displacement node created | `node_type` is the sentinel `displacementShader` (expected direct-to-SG); or `displacementTexture` empty (treated as unsupported) |
