import json
import os

class NodeMapping:
    def __init__(self, data, renderer):
        self.renderer = renderer
        self.is_material_attribute = data.get("is_material_attribute", False)
        self.node_type = data.get("node_type", "")
        self.target_connection = data.get("target_connection", "")
        self.source_connection = data.get("source_connection", "")
        self.scale = data.get("scale", "")
        self.input = data.get("input", "")
        self.isNormal = data.get("isNormal", "")
        self.isNormal_value = data.get("isNormal_value", None)
        self.input_type = data.get("input_type", "")
        self.input_type_value = data.get("input_type_value", None)


class BumpNormalConfig:
    def __init__(self, data, renderer):
        self.renderer = renderer
        bump_data = data.get("bump", {})
        normal_data = data.get("normal", {})
        self.bump = NodeMapping(bump_data, renderer) if bump_data else None
        self.normal = NodeMapping(normal_data, renderer) if normal_data else None


class ColorCorrectionConfig:
    def __init__(self, data, renderer):
        self.renderer = renderer
        mat_data = data.get("material", {})
        base_data = data.get("base", {})
        color_data = data.get("color", {})

        self.node_type = mat_data.get("node_type", "")
        self.target_connection = mat_data.get("target_connection", "")
        self.source_connection = mat_data.get("source_connection", "")

        self.gamma = base_data.get("gamma", "")
        self.contrast = base_data.get("contrast", "")
        self.gain = base_data.get("gain", "")

        self.hue = color_data.get("hue", "")
        self.saturation = color_data.get("saturation", "")
        self.hue_range = color_data.get("hue_range", None)


class MaterialConfig:
    def __init__(self, data, filename):
        mat_data = data.get("material", {})
        self.filename = filename
        self.node_type = mat_data.get("node_type", "")
        self.target_connection = mat_data.get("target_connection", "")
        self.short_name = mat_data.get("short_name", "")
        self.uiPanel_display_name = mat_data.get("uiPanel_display_name", self.node_type)
        self.renderer = mat_data.get("renderer", "unknown")

        self.attr_map = {}
        self.prerequisites = {}
        self.attr_prerequisites = {}

        prereq_section = mat_data.get("prerequisites", {})
        if prereq_section:
            if isinstance(prereq_section, dict):
                self.prerequisites = dict(prereq_section)

        for section_name, section_data in data.items():
            if section_name in ("material",):
                continue

            section_prereqs = {}
            if isinstance(section_data, dict):
                if "prerequisites" in section_data:
                    section_prereqs = dict(section_data["prerequisites"])

            for common_attr, maya_attr in section_data.items():
                if common_attr == "prerequisites":
                    continue
                if isinstance(maya_attr, str):
                    self.attr_map[common_attr] = maya_attr

            for attr_key, prereq_val in section_prereqs.items():
                self.attr_prerequisites[attr_key] = prereq_val

        self._build_displacement_info(data)

    def _build_displacement_info(self, data):
        disp_data = data.get("displacement", {})
        self.displacement_node_type = disp_data.get("node_type", "")
        self.displacement_scale = disp_data.get("displacementScale", "")
        self.displacement_texture = disp_data.get("displacementTexture", "")

    def get_maya_attr(self, common_attr):
        return self.attr_map.get(common_attr, "")

    def has_attr(self, common_attr):
        val = self.attr_map.get(common_attr, "")
        return bool(val)

    def get_prerequisites(self):
        return self.prerequisites

    def get_attr_prerequisites(self, common_attr):
        return self.attr_prerequisites.get(common_attr)


class ConfigLoader:
    _CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")

    def __init__(self):
        self._material_configs = {}
        self._common_attrs = {}
        self._bump_normal_configs = {}
        self._color_correction_configs = {}
        self._builder_specs = {}
        self._builder_naming = {}
        self._color_weight_pairs = []
        self._color_space_config = {}
        self._load_all()

    def _load_all(self):
        self._load_common()
        self._load_materials()
        self._load_bump_normal()
        self._load_color_correction()
        self._load_builder_specs()
        self._load_builder_naming()
        self._load_color_space()

    def _load_common(self):
        path = os.path.join(self._CONFIG_DIR, "material", "common.json")
        raw = self._read_json(path)
        self._color_weight_pairs = raw.get("color_weight_pairs", [])

        common_attr_groups = {}
        for group_name, group_data in raw.items():
            if isinstance(group_data, dict):
                common_attr_groups[group_name] = list(group_data.keys())

        all_attrs = []
        for attrs in common_attr_groups.values():
            all_attrs.extend(attrs)
        self._common_attrs = all_attrs

    def _load_materials(self):
        mat_dir = os.path.join(self._CONFIG_DIR, "material")
        for fname in os.listdir(mat_dir):
            if fname == "common.json" or not fname.endswith(".json"):
                continue
            path = os.path.join(mat_dir, fname)
            raw = self._read_json(path)
            config = MaterialConfig(raw, fname)
            self._material_configs[config.node_type] = config

    def _load_bump_normal(self):
        self._bump_normal_configs = self._load_renderer_config(
            "bumpNormal.json", BumpNormalConfig
        )

    def _load_color_correction(self):
        self._color_correction_configs = self._load_renderer_config(
            "colorCorrection.json", ColorCorrectionConfig
        )

    def _load_renderer_config(self, filename, config_class):
        path = os.path.join(self._CONFIG_DIR, filename)
        raw = self._read_json(path)

        common_data = raw.get("common", {})
        result = {}
        for renderer in raw:
            if renderer == "common":
                continue
            renderer_data = dict(raw[renderer])
            for section_name, section_defaults in common_data.items():
                if section_name not in renderer_data:
                    renderer_data[section_name] = {}
                for k, v in section_defaults.items():
                    if k not in renderer_data[section_name]:
                        renderer_data[section_name][k] = v

            result[renderer] = config_class(renderer_data, renderer)
        return result

    @staticmethod
    def _read_json(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"ConfigLoader: failed to load {path}: {e}")
            raise

    def get_material_config(self, node_type):
        return self._material_configs.get(node_type)

    def get_all_material_node_types(self):
        return list(self._material_configs.keys())

    def get_all_material_configs(self):
        return dict(self._material_configs)

    def get_color_weight_pairs(self):
        return list(self._color_weight_pairs)

    def get_common_attrs(self):
        return list(self._common_attrs)

    def get_bump_normal_config(self, renderer):
        return self._bump_normal_configs.get(renderer)

    def get_all_bn_types(self):
        types = set()
        for bn in self._bump_normal_configs.values():
            if bn.bump and bn.bump.node_type:
                types.add(bn.bump.node_type)
            if bn.normal and bn.normal.node_type:
                types.add(bn.normal.node_type)
        return types

    def find_bn_renderer(self, node_type):
        for r, bn in self._bump_normal_configs.items():
            if bn.bump and bn.bump.node_type == node_type:
                return r, bn.bump
            if bn.normal and bn.normal.node_type == node_type:
                return r, bn.normal
        return None, None

    def get_color_correction_config(self, renderer):
        return self._color_correction_configs.get(renderer)

    def get_builder_spec(self, renderer):
        return self._builder_specs.get(renderer)

    def get_builder_naming(self):
        return dict(self._builder_naming)

    def _load_builder_naming(self):
        path = os.path.join(self._CONFIG_DIR, "builder_naming.json")
        if not os.path.exists(path):
            return
        self._builder_naming = self._read_json(path)

    def _load_builder_specs(self):
        path = os.path.join(self._CONFIG_DIR, "builder_specs.json")
        if not os.path.exists(path):
            return
        self._builder_specs = self._read_json(path)

    def identify_cc_renderer(self, node_type):
        for renderer, cc in self._color_correction_configs.items():
            if cc.node_type == node_type:
                return renderer
        return None

    def identify_renderer(self, node_type):
        config = self._material_configs.get(node_type)
        if not config:
            for nt, cfg in self._material_configs.items():
                if nt.lower() == node_type.lower():
                    return nt
            return None
        return config.node_type

    def get_display_name(self, node_type):
        config = self._material_configs.get(node_type)
        return config.uiPanel_display_name if config else node_type

    def get_renderer_name(self, node_type):
        config = self._material_configs.get(node_type)
        return config.renderer if config else "unknown"

    def get_all_cc_types(self):
        types = set()
        for cc in self._color_correction_configs.values():
            if cc.node_type:
                types.add(cc.node_type)
        return types

    def _load_color_space(self):
        path = os.path.join(self._CONFIG_DIR, "colorSpace.json")
        if not os.path.exists(path):
            return
        self._color_space_config = self._read_json(path)

    def get_color_space_config(self):
        return dict(self._color_space_config)

    def get_expanded_attribute_keywords(self):
        common_roles = self._color_space_config.get("commonAttributeRoles", {})
        expanded = {role: list(keywords) for role, keywords in common_roles.items()}

        for node_type, mat_config in self._material_configs.items():
            for common_attr, maya_attr in mat_config.attr_map.items():
                if not maya_attr:
                    continue
                for role, common_attrs in common_roles.items():
                    if common_attr in common_attrs and maya_attr not in expanded[role]:
                        expanded[role].append(maya_attr)

        return expanded
