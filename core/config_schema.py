"""Offline structural validation of the JSON configuration.

Runs before any Maya node exists, so a broken config (wrong type, missing
required field, dangling cross reference, duplicate ``node_type``) is reported
with its filename and field path instead of surfacing later as a ``KeyError`` or
a silently overwritten renderer definition.

This module is pure Python (no Maya import) and is unit-tested by the CI suite.
"""

import json
import os
from dataclasses import dataclass

VALID_RENDERERS = ("arnold", "redshift", "vray")

#: Renderer-config sections may also describe native Maya nodes (``maya``),
#: which never have a material JSON of their own.
VALID_CONFIG_RENDERERS = VALID_RENDERERS + ("maya",)


@dataclass
class ConfigIssue:
    filename: str
    field_path: str
    level: str
    message: str

    def as_text(self):
        location = f"{self.filename}:{self.field_path}" if self.field_path else self.filename
        return f"{location}: {self.message}"


def default_config_dir():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")


def _load_json(path, issues):
    filename = os.path.basename(path)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:  # noqa: silent-fallback reported as a ConfigIssue
        issues.append(ConfigIssue(filename, "", "ERROR", "file is missing"))
    except Exception as exc:  # noqa: silent-fallback reported as a ConfigIssue
        issues.append(ConfigIssue(filename, "", "ERROR", f"invalid JSON: {exc}"))
    return None


def _require_string(filename, path, data, field, issues):
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        issues.append(ConfigIssue(filename, f"{path}.{field}".strip("."), "ERROR",
                                  f"missing or empty string for '{field}'"))
        return False
    return True


# --------------------------------------------------------------------------- #
# Material configs
# --------------------------------------------------------------------------- #

def validate_material_files(config_dir=None, issues=None):
    """Validate every ``config/material/*.json`` file (structure + duplicates)."""
    config_dir = config_dir or default_config_dir()
    issues = issues if issues is not None else []
    mat_dir = os.path.join(config_dir, "material")
    if not os.path.isdir(mat_dir):
        issues.append(ConfigIssue("config/material", "", "ERROR",
                                  f"material config directory is missing: {mat_dir}"))
        return issues

    seen_node_types = {}
    for filename in sorted(os.listdir(mat_dir)):
        if not filename.endswith(".json") or filename == "common.json":
            continue
        raw = _load_json(os.path.join(mat_dir, filename), issues)
        if raw is None:
            continue
        if not isinstance(raw, dict):
            issues.append(ConfigIssue(filename, "", "ERROR", "top level must be an object"))
            continue

        material = raw.get("material")
        if not isinstance(material, dict):
            issues.append(ConfigIssue(filename, "material", "ERROR",
                                      "missing 'material' object"))
            continue

        for field in ("node_type", "uiPanel_display_name", "renderer"):
            _require_string(filename, "material", material, field, issues)

        renderer = material.get("renderer")
        if isinstance(renderer, str) and renderer and renderer not in VALID_RENDERERS:
            issues.append(ConfigIssue(filename, "material.renderer", "ERROR",
                                      f"unknown renderer '{renderer}' "
                                      f"(expected one of {VALID_RENDERERS})"))

        plugin = material.get("plugin", "")
        if plugin is not None and not isinstance(plugin, str):
            issues.append(ConfigIssue(filename, "material.plugin", "ERROR",
                                      "plugin must be a string"))

        invert = material.get("invert")
        if invert is not None and not isinstance(invert, dict):
            issues.append(ConfigIssue(filename, "material.invert", "ERROR",
                                      "invert must be an object"))

        node_type = material.get("node_type")
        if isinstance(node_type, str) and node_type:
            if node_type in seen_node_types:
                issues.append(ConfigIssue(
                    filename, "material.node_type", "ERROR",
                    f"duplicate node_type '{node_type}' "
                    f"(already defined in {seen_node_types[node_type]})"))
            else:
                seen_node_types[node_type] = filename

        for section_name, section_data in raw.items():
            if section_name == "material":
                continue
            if not isinstance(section_data, dict):
                issues.append(ConfigIssue(
                    filename, section_name, "ERROR",
                    "section must be an object of attribute mappings"))
                continue
            _validate_material_section(filename, section_name, section_data, issues)

    return issues


def _validate_material_section(filename, section_name, section_data, issues):
    for key, value in section_data.items():
        path = f"{section_name}.{key}"
        if key == "prerequisites":
            if not isinstance(value, dict):
                issues.append(ConfigIssue(filename, path, "ERROR",
                                          "prerequisites must be an object"))
                continue
            for attr_name, spec in value.items():
                _validate_prerequisite(filename, f"{path}.{attr_name}", spec, issues)
            continue

        if not isinstance(value, str):
            issues.append(ConfigIssue(filename, path, "ERROR",
                                      "attribute mapping must be a string"))


def _validate_prerequisite(filename, path, spec, issues):
    if not isinstance(spec, dict):
        issues.append(ConfigIssue(filename, path, "ERROR",
                                  "prerequisite must be an object"))
        return
    attribute = spec.get("attribute")
    if not isinstance(attribute, str) or not attribute:
        issues.append(ConfigIssue(filename, f"{path}.attribute", "ERROR",
                                  "missing attribute name"))
    if "value" not in spec:
        issues.append(ConfigIssue(filename, f"{path}.value", "ERROR", "missing value"))


# --------------------------------------------------------------------------- #
# Renderer configs (bumpNormal.json / colorCorrection.json)
# --------------------------------------------------------------------------- #

def validate_renderer_files(config_dir=None, issues=None):
    config_dir = config_dir or default_config_dir()
    issues = issues if issues is not None else []
    _validate_bump_normal(os.path.join(config_dir, "bumpNormal.json"), issues)
    _validate_color_correction(os.path.join(config_dir, "colorCorrection.json"), issues)
    return issues


def _renderer_entries(raw, filename, issues):
    for renderer, data in raw.items():
        if renderer == "common":
            continue
        if renderer not in VALID_CONFIG_RENDERERS:
            issues.append(ConfigIssue(filename, renderer, "WARN",
                                      f"unknown renderer '{renderer}'"))
        if not isinstance(data, dict):
            issues.append(ConfigIssue(filename, renderer, "ERROR",
                                      "renderer section must be an object"))
            continue
        yield renderer, data


def _validate_bump_normal(path, issues):
    filename = "bumpNormal.json"
    raw = _load_json(path, issues)
    if raw is None:
        return
    if not isinstance(raw, dict):
        issues.append(ConfigIssue(filename, "", "ERROR", "top level must be an object"))
        return

    common = raw.get("common", {})
    if not isinstance(common, dict):
        issues.append(ConfigIssue(filename, "common", "ERROR", "common must be an object"))

    for renderer, data in _renderer_entries(raw, filename, issues):
        for section in ("bump", "normal"):
            section_data = data.get(section)
            if section_data is None:
                continue
            if not isinstance(section_data, dict):
                issues.append(ConfigIssue(filename, f"{renderer}.{section}", "ERROR",
                                          "section must be an object"))
                continue
            _validate_bn_section(filename, f"{renderer}.{section}", section_data, issues)


def _validate_bn_section(filename, path, data, issues):
    is_material_attr = data.get("is_material_attribute", False)
    if not isinstance(is_material_attr, bool):
        issues.append(ConfigIssue(filename, f"{path}.is_material_attribute", "ERROR",
                                  "must be a boolean"))

    if not is_material_attr:
        for field in ("node_type", "input", "output"):
            _require_string(filename, path, data, field, issues)

    for field in ("node_type", "input", "output", "scale", "file_source",
                  "is_normal", "path"):
        if field in data and not isinstance(data[field], str):
            issues.append(ConfigIssue(filename, f"{path}.{field}", "ERROR",
                                      f"{field} must be a string"))

    has_switch = bool(data.get("is_normal"))
    has_value = "is_normal_value" in data
    if has_switch != has_value:
        issues.append(ConfigIssue(filename, path, "ERROR",
                                  "is_normal and is_normal_value must be declared together"))

    switch_value = data.get("is_normal_value")
    if has_value and not isinstance(switch_value, (int, float, str, list, tuple)):
        issues.append(ConfigIssue(filename, f"{path}.is_normal_value", "ERROR",
                                  "must be a scalar or a list of scalars"))
    if isinstance(switch_value, (list, tuple)) and not switch_value:
        issues.append(ConfigIssue(filename, f"{path}.is_normal_value", "ERROR",
                                  "must not be an empty list"))

    spaces = data.get("normal_space")
    if spaces is not None:
        if not isinstance(spaces, dict) or not spaces:
            issues.append(ConfigIssue(filename, f"{path}.normal_space", "ERROR",
                                      "must be a non-empty {space: value} object"))
        else:
            allowed = (list(switch_value) if isinstance(switch_value, (list, tuple))
                       else [switch_value])
            for space, value in spaces.items():
                if not isinstance(space, str) or not space:
                    issues.append(ConfigIssue(filename, f"{path}.normal_space", "ERROR",
                                              "space names must be non-empty strings"))
                elif value not in allowed:
                    issues.append(ConfigIssue(
                        filename, f"{path}.normal_space.{space}", "ERROR",
                        f"value {value!r} is not part of is_normal_value {allowed!r}"))

    extras = data.get("extra_nodes")
    if extras is not None:
        if not isinstance(extras, list):
            issues.append(ConfigIssue(filename, f"{path}.extra_nodes", "ERROR",
                                      "must be a list"))
        else:
            for index, extra in enumerate(extras):
                extra_path = f"{path}.extra_nodes[{index}]"
                if not isinstance(extra, dict):
                    issues.append(ConfigIssue(filename, extra_path, "ERROR",
                                              "must be an object"))
                    continue
                for field in ("node_type", "path"):
                    _require_string(filename, extra_path, extra, field, issues)
                for field in ("output", "scale", "file_source"):
                    if field in extra and not isinstance(extra[field], str):
                        issues.append(ConfigIssue(filename, f"{extra_path}.{field}", "ERROR",
                                                  f"{field} must be a string"))


def _validate_color_correction(path, issues):
    filename = "colorCorrection.json"
    raw = _load_json(path, issues)
    if raw is None:
        return
    if not isinstance(raw, dict):
        issues.append(ConfigIssue(filename, "", "ERROR", "top level must be an object"))
        return

    for renderer, data in _renderer_entries(raw, filename, issues):
        material = data.get("material")
        if not isinstance(material, dict):
            issues.append(ConfigIssue(filename, f"{renderer}.material", "ERROR",
                                      "missing 'material' object"))
            continue
        for field in ("node_type", "input", "output"):
            _require_string(filename, f"{renderer}.material", material, field, issues)

        for section in ("base", "color"):
            section_data = data.get(section)
            if section_data is None:
                continue
            if not isinstance(section_data, dict):
                issues.append(ConfigIssue(filename, f"{renderer}.{section}", "ERROR",
                                          "section must be an object"))
                continue
            for key, value in section_data.items():
                field_path = f"{renderer}.{section}.{key}"
                if key == "hue_range":
                    if not (isinstance(value, (list, tuple)) and len(value) == 2
                            and all(isinstance(v, (int, float)) for v in value)):
                        issues.append(ConfigIssue(filename, field_path, "ERROR",
                                                  "must be a two-number range"))
                elif key == "hue_center":
                    if not isinstance(value, (int, float)):
                        issues.append(ConfigIssue(filename, field_path, "ERROR",
                                                  "must be a number"))
                elif not isinstance(value, str):
                    issues.append(ConfigIssue(filename, field_path, "ERROR",
                                              "must be an attribute name string"))


# --------------------------------------------------------------------------- #
# Cross references
# --------------------------------------------------------------------------- #

def validate_cross_references(config_dir=None, issues=None):
    """Check that configs only reference attributes/roles that actually exist."""
    config_dir = config_dir or default_config_dir()
    issues = issues if issues is not None else []

    common_raw = _load_json(os.path.join(config_dir, "material", "common.json"), issues)
    common_attrs = set()
    if isinstance(common_raw, dict):
        for group, data in common_raw.items():
            if isinstance(data, dict):
                common_attrs.update(data.keys())

    mat_dir = os.path.join(config_dir, "material")
    if os.path.isdir(mat_dir):
        for filename in sorted(os.listdir(mat_dir)):
            if not filename.endswith(".json") or filename == "common.json":
                continue
            raw = _load_json(os.path.join(mat_dir, filename), issues)
            if not isinstance(raw, dict):
                continue
            for section_name, section_data in raw.items():
                if section_name == "material" or not isinstance(section_data, dict):
                    continue
                if section_name == "displacement":
                    continue
                for key, value in section_data.items():
                    if key == "prerequisites" or not isinstance(value, str) or not value:
                        continue
                    if key not in common_attrs:
                        issues.append(ConfigIssue(
                            filename, f"{section_name}.{key}", "WARN",
                            f"'{key}' is not declared in common.json"))

    texture_channels = _load_json(
        os.path.join(config_dir, "texture_channels.json"), issues)
    channels = texture_channels.get("channels") if isinstance(texture_channels, dict) else None
    if isinstance(channels, dict):
        for channel_name, data in channels.items():
            if not isinstance(data, dict):
                issues.append(ConfigIssue(
                    "texture_channels.json", f"channels.{channel_name}", "ERROR",
                    "channel must be an object"))
                continue
            common_attr = data.get("common_attr")
            if not isinstance(common_attr, str) or not common_attr:
                issues.append(ConfigIssue(
                    "texture_channels.json", f"channels.{channel_name}.common_attr",
                    "ERROR", "missing common_attr"))
            elif common_attrs and common_attr not in common_attrs:
                issues.append(ConfigIssue(
                    "texture_channels.json", f"channels.{channel_name}.common_attr",
                    "ERROR", f"unknown common attribute '{common_attr}'"))

    short_suffixes = (texture_channels.get("short_suffixes")
                      if isinstance(texture_channels, dict) else None)
    if isinstance(short_suffixes, dict) and isinstance(channels, dict):
        for letter, channel_name in short_suffixes.items():
            if channel_name not in channels:
                issues.append(ConfigIssue(
                    "texture_channels.json", f"short_suffixes.{letter}", "ERROR",
                    f"unknown channel '{channel_name}'"))

    naming = _load_json(os.path.join(config_dir, "builder_naming.json"), issues)
    if isinstance(naming, dict):
        colors = naming.get("layered_colors")
        modes = naming.get("layered_blend_modes")
        if isinstance(colors, list) and isinstance(modes, list) and len(colors) != len(modes):
            issues.append(ConfigIssue(
                "builder_naming.json", "layered_colors", "ERROR",
                f"layered_colors ({len(colors)}) and layered_blend_modes "
                f"({len(modes)}) must have the same length"))

    # Every non-native renderer section must be backed by at least one material.
    material_renderers = set()
    if os.path.isdir(mat_dir):
        for filename in sorted(os.listdir(mat_dir)):
            if not filename.endswith(".json") or filename == "common.json":
                continue
            raw = _load_json(os.path.join(mat_dir, filename), issues)
            material = raw.get("material") if isinstance(raw, dict) else None
            if isinstance(material, dict) and isinstance(material.get("renderer"), str):
                material_renderers.add(material["renderer"])

    for config_filename in ("bumpNormal.json", "colorCorrection.json"):
        raw = _load_json(os.path.join(config_dir, config_filename), issues)
        if not isinstance(raw, dict):
            continue
        for renderer in raw:
            if renderer == "common" or renderer == "maya":
                continue
            if material_renderers and renderer not in material_renderers:
                issues.append(ConfigIssue(
                    config_filename, renderer, "ERROR",
                    f"renderer '{renderer}' has no material config"))

    return issues


def run_all(config_dir=None):
    """All offline checks as a list of :class:`ConfigIssue` (errors first)."""
    config_dir = config_dir or default_config_dir()
    issues = []
    validate_material_files(config_dir, issues)
    validate_renderer_files(config_dir, issues)
    validate_cross_references(config_dir, issues)
    issues.sort(key=lambda issue: (issue.level != "ERROR", issue.filename, issue.field_path))
    return issues
