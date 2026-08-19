import json
import os
from dataclasses import dataclass

import maya.cmds as _cmds

from core.config_loader import ConfigLoader


class Level:
    OK = "OK"
    ERROR = "ERROR"
    WARN = "WARN"
    SKIP = "SKIP"
    INFO = "INFO"


@dataclass
class CheckResult:
    level: str
    scope: str
    detail: str


class ConfigValidator:

    VALIDATION_PREFIX = "configValidation_"
    DISPLACEMENT_KEYS = {"node_type", "displacementScale", "displacementTexture",
                         "file_source", "lyr_src", "output"}

    def __init__(self, loader=None, cmds_module=None):
        self.loader = loader or ConfigLoader()
        self.cmds = cmds_module or _cmds
        self._results = []
        self._created = []
        self._counter = 0
        self._plugin_cache = {}
        self._bn_raw = None
        self._cc_raw = None

    def _reset(self):
        self._results = []
        self._created = []
        self._counter = 0
        self._plugin_cache = {}

    def _add(self, level, scope, detail):
        self._results.append(CheckResult(level=level, scope=scope, detail=detail))

    def _make_name(self):
        self._counter += 1
        return f"{self.VALIDATION_PREFIX}{self._counter}"

    def _read_raw(self, filename):
        path = os.path.join(ConfigLoader._CONFIG_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _plugin_for_renderer(self, renderer):
        for cfg in self.loader.get_all_material_configs().values():
            if cfg.renderer == renderer and cfg.plugin:
                return cfg.plugin
        return ""

    def _check_plugin(self, plugin, scope):
        if not plugin:
            return "ok"
        if plugin in self._plugin_cache:
            return self._plugin_cache[plugin]

        cmds = self.cmds
        try:
            loaded = bool(cmds.pluginInfo(plugin, query=True, loaded=True))
        except Exception:
            loaded = False

        if not loaded:
            try:
                cmds.loadPlugin(plugin)
                loaded = True
            except Exception:
                self._plugin_cache[plugin] = "skip"
                self._add(Level.SKIP, scope,
                          f"plugin '{plugin}' failed to load (not installed or "
                          "load error), skipped")
                return "skip"

        self._plugin_cache[plugin] = "ok"
        self._add(Level.INFO, scope, f"plugin '{plugin}' loaded")
        return "ok"

    def _create_temp(self, node_type, as_type, scope):
        name = self._make_name()
        try:
            if as_type == "shader":
                node = self.cmds.shadingNode(node_type, asShader=True, name=name)
            elif as_type == "texture":
                node = self.cmds.shadingNode(node_type, asTexture=True, name=name)
            else:
                node = self.cmds.shadingNode(node_type, asUtility=True, name=name)
        except Exception as e:
            self._add(Level.ERROR, scope,
                      f"node_type '{node_type}' could not be created: {e}")
            return None
        self._created.append(node)
        self._add(Level.INFO, scope, f"node_type '{node_type}' created OK")
        return node

    def _check_attr(self, node, node_type, attr, scope, desc):
        try:
            exists = bool(self.cmds.attributeQuery(attr, node=node, exists=True))
        except Exception:
            exists = False
        if exists:
            self._add(Level.OK, scope, f"{desc} -> OK on '{node_type}'")
        else:
            self._add(Level.ERROR, scope,
                      f"{desc} -> NOT FOUND on '{node_type}'")

    def _cleanup(self):
        for node in self._created:
            try:
                if self.cmds.objExists(node):
                    self.cmds.delete(node)
            except Exception:
                pass
        self._created.clear()

    def validate_all(self):
        self._reset()
        try:
            self.validate_materials()
            self.validate_bump_normal()
            self.validate_color_correction()
        finally:
            self._cleanup()

        counts = {"OK": 0, "ERROR": 0, "WARN": 0, "SKIP": 0, "INFO": 0}
        for r in self._results:
            counts[r.level] += 1
        summary = {
            "total": len(self._results),
            "ok": counts[Level.OK],
            "error": counts[Level.ERROR],
            "warn": counts[Level.WARN],
            "skip": counts[Level.SKIP],
            "info": counts[Level.INFO],
        }
        return list(self._results), summary

    def validate_materials(self):
        for node_type in sorted(self.loader.get_all_material_configs()):
            config = self.loader.get_material_config(node_type)
            scope = f"material/{node_type}"
            renderer = config.renderer

            if config.plugin:
                if self._check_plugin(config.plugin, scope) == "skip":
                    continue

            node = self._create_temp(config.node_type, "shader", scope)
            if not node:
                continue

            for common_attr in sorted(config.attr_map):
                if common_attr in self.DISPLACEMENT_KEYS:
                    continue
                maya_attr = config.attr_map[common_attr]
                if not maya_attr:
                    self._add(Level.SKIP, scope,
                              f"attr '{common_attr}': empty mapping, skipped")
                    continue
                self._check_attr(node, config.node_type, maya_attr, scope,
                                 f"attr '{common_attr}' -> '{maya_attr}'")

            for prereq_key in sorted(config.prerequisites):
                attr = config.prerequisites[prereq_key].get("attribute", "")
                if attr:
                    self._check_attr(node, config.node_type, attr, scope,
                                     f"prerequisite '{prereq_key}' -> '{attr}'")

            for common_attr in sorted(config.attr_prerequisites):
                attr = config.attr_prerequisites[common_attr].get("attribute", "")
                if attr:
                    self._check_attr(node, config.node_type, attr, scope,
                                     f"attr prerequisite '{common_attr}' -> '{attr}'")

            self._validate_displacement(config, scope)

    def _validate_displacement(self, config, scope):
        disp_scope = f"{scope}/displacement"
        disp_type = config.displacement_node_type
        disp_in = config.displacement_texture

        if not disp_type and not disp_in:
            self._add(Level.SKIP, disp_scope, "no displacement config, skipped")
            return

        if disp_type:
            if disp_type == "displacementShader":
                self._add(Level.INFO, disp_scope,
                          f"node_type '{disp_type}' is a sentinel value, "
                          "node is still created for validation")
            disp_node = self._create_temp(disp_type, "shader", disp_scope)
            if not disp_node:
                return
        else:
            disp_node = None

        if disp_in:
            self._check_attr(disp_node, disp_type, disp_in, disp_scope,
                             f"displacementTexture -> '{disp_in}'")

        if config.displacement_scale:
            self._check_attr(disp_node, disp_type, config.displacement_scale,
                             disp_scope,
                             f"displacementScale -> '{config.displacement_scale}'")

        if config.displacement_output:
            self._check_attr(disp_node, disp_type, config.displacement_output,
                             disp_scope,
                             f"output -> '{config.displacement_output}'")

        if config.displacement_file_source:
            f_node = self._create_temp("file", "texture", disp_scope)
            if f_node:
                self._check_attr(f_node, "file", config.displacement_file_source,
                                 disp_scope,
                                 f"file_source -> '{config.displacement_file_source}'")

        if config.displacement_lyr_src:
            lyr_node = self._create_temp("layeredTexture", "texture", disp_scope)
            if lyr_node:
                self._check_attr(lyr_node, "layeredTexture",
                                 config.displacement_lyr_src, disp_scope,
                                 f"lyr_src -> '{config.displacement_lyr_src}'")

    def validate_bump_normal(self):
        for renderer in sorted(self.loader.get_all_bn_configs()):
            bn = self.loader.get_bump_normal_config(renderer)
            scope = f"bumpNormal/{renderer}"
            plugin = self._plugin_for_renderer(renderer)
            if self._check_plugin(plugin, scope) == "skip":
                continue

            for mode in ("bump", "normal"):
                mapping = getattr(bn, mode)
                if not mapping:
                    continue
                self._validate_bn_mapping(mapping, renderer, mode, scope)

    def _validate_bn_mapping(self, mapping, renderer, mode, scope):
        sub = f"{scope}.{mode}"
        raw = self._bn_raw or self._read_raw("bumpNormal.json")
        self._bn_raw = raw
        renderer_data = raw.get(renderer, {}).get(mode, {}) if isinstance(raw.get(renderer, {}), dict) else {}

        def defined(field):
            return field in renderer_data

        if mapping.is_material_attribute:
            mat_node_type = self._material_type_for_renderer(renderer)
            if not mat_node_type:
                self._add(Level.SKIP, sub,
                          "is_material_attribute but no material config for "
                          "renderer, skipped")
                return
            node = self._create_temp(mat_node_type, "shader", sub)
            if not node:
                return
            for label, attr in (("scale", mapping.scale),
                                ("input", mapping.input),
                                ("input_type", mapping.input_type)):
                if not attr:
                    continue
                if not defined(label):
                    self._add(Level.SKIP, sub,
                              f"{label} uses common default, skipped")
                    continue
                self._check_attr(node, mat_node_type, attr, sub,
                                 f"{label} -> '{attr}'")
            return

        if not mapping.node_type:
            self._add(Level.ERROR, sub,
                      "node_type is empty for standalone bump/normal mode")
            return

        node = self._create_temp(mapping.node_type, "utility", sub)
        if not node:
            return

        for label, attr in (("scale", mapping.scale),
                            ("source_connection", mapping.source_connection),
                            ("target_connection", mapping.target_connection),
                            ("is_normal", mapping.is_normal)):
            if not attr:
                continue
            if not defined(label):
                self._add(Level.SKIP, sub,
                          f"{label} uses common default, skipped")
                continue
            self._check_attr(node, mapping.node_type, attr, sub,
                             f"{label} -> '{attr}'")

        if mapping.file_source:
            f_node = self._create_temp("file", "texture", sub)
            if f_node:
                self._check_attr(f_node, "file", mapping.file_source, sub,
                                 f"file_source -> '{mapping.file_source}'")

    def _material_type_for_renderer(self, renderer):
        for node_type, cfg in self.loader.get_all_material_configs().items():
            if cfg.renderer == renderer:
                return cfg.node_type
        return ""

    def validate_color_correction(self):
        for renderer in sorted(self.loader.get_all_cc_configs()):
            cc = self.loader.get_color_correction_config(renderer)
            scope = f"colorCorrection/{renderer}"
            plugin = self._plugin_for_renderer(renderer)
            if self._check_plugin(plugin, scope) == "skip":
                continue

            if not cc.node_type:
                self._add(Level.ERROR, scope, "missing cc node_type")
                continue

            node = self._create_temp(cc.node_type, "utility", scope)
            if not node:
                continue

            raw = self._cc_raw or self._read_raw("colorCorrection.json")
            self._cc_raw = raw
            renderer_data = raw.get(renderer, {}) if isinstance(raw.get(renderer, {}), dict) else {}
            material_data = renderer_data.get("material", {}) if isinstance(renderer_data.get("material", {}), dict) else {}

            def material_defined(field):
                return field in material_data

            for label, attr in (("target_connection", cc.target_connection),
                                ("source_connection", cc.source_connection)):
                if not attr:
                    continue
                if not material_defined(label):
                    self._add(Level.SKIP, scope,
                              f"{label} uses common default, skipped")
                    continue
                self._check_attr(node, cc.node_type, attr, scope,
                                 f"{label} -> '{attr}'")

            base_data = renderer_data.get("base", {}) if isinstance(renderer_data.get("base", {}), dict) else {}
            color_data = renderer_data.get("color", {}) if isinstance(renderer_data.get("color", {}), dict) else {}

            def section_defined(section_data, field):
                return field in section_data

            for label, attr in (("gamma", cc.gamma), ("contrast", cc.contrast),
                                ("gain", cc.gain)):
                if not attr:
                    self._add(Level.SKIP, scope, f"{label}: empty, skipped")
                    continue
                if not section_defined(base_data, label):
                    self._add(Level.SKIP, scope,
                              f"{label} uses common default, skipped")
                    continue
                self._check_attr(node, cc.node_type, attr, scope,
                                 f"{label} -> '{attr}'")

            for label, attr in (("hue", cc.hue), ("saturation", cc.saturation)):
                if not attr:
                    self._add(Level.SKIP, scope, f"{label}: empty, skipped")
                    continue
                if not section_defined(color_data, label):
                    self._add(Level.SKIP, scope,
                              f"{label} uses common default, skipped")
                    continue
                self._check_attr(node, cc.node_type, attr, scope,
                                 f"{label} -> '{attr}'")