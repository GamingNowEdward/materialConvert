import pymel.core as pm

from core.config_loader import ConfigLoader
from core.node_utils import NodeUtils
from core.prerequisites import apply_prerequisites
from core.converters import AttributeConverter, CCConverter, BumpConverter, DisplacementConverter


class MaterialConverter:

    def __init__(self):
        self.config = ConfigLoader()
        self.utils = NodeUtils
        self.cc_converter = CCConverter(self.config, self.utils)
        self.attr_converter = AttributeConverter(self.config, self.utils, self.cc_converter)
        self.bump_converter = BumpConverter(self.config, self.utils)
        self.disp_converter = DisplacementConverter(self.config, self.utils)

    def convert(self, source_mat, target_node_type):
        log = []

        self.cc_converter.reset()

        source_node_type = self.utils.identify_node_type(source_mat)
        source_config = self.config.get_material_config(source_node_type)
        target_config = self.config.get_material_config(target_node_type)

        if not source_config:
            log.append(f"[ERROR] Unknown source material type: {source_node_type}")
            return None, log
        if not target_config:
            log.append(f"[ERROR] Unknown target material type: {target_node_type}")
            return None, log

        source_renderer = self.config.get_renderer_name(source_node_type)
        target_renderer = self.config.get_renderer_name(target_node_type)

        log.append(f"Converting: {source_mat.name()} ({self.config.get_display_name(source_node_type)})")
        log.append(f"       to: {self.config.get_display_name(target_node_type)}")

        attr_info = self.attr_converter.collect_attrs(source_mat, source_config)

        suffix = target_config.short_name or "converted"
        base_name = source_mat.name() + "_" + suffix
        new_mat = self.utils.create_target_material(target_node_type, base_name)
        log.append(f"Created: {new_mat.name()}")

        apply_prerequisites(new_mat, target_config)

        if source_renderer == target_renderer:
            cc_cache = {}
            self.bump_converter.reuse_existing(source_mat, new_mat, source_renderer, log)
        else:
            cc_cache = self.cc_converter.collect_chains(attr_info)
            self.bump_converter.convert(source_mat, new_mat, source_renderer, target_renderer, log)

        self.attr_converter.transfer_all(
            new_mat, source_config, target_config, target_renderer,
            attr_info, cc_cache, log
        )

        if source_renderer != target_renderer:
            self.disp_converter.convert(source_mat, new_mat, source_config, target_config, target_renderer, log)

        sgs = source_mat.outColor.connections(plugs=False)
        for sg in sgs:
            if pm.nodeType(sg) == "shadingEngine":
                try:
                    new_mat.outColor >> sg.surfaceShader
                except Exception:
                    pass

        log.append(f"Disconnected old material: {source_mat.name()}")

        return new_mat, log

    def convert_all(self, materials, target_node_type):
        results = []
        for mat in materials:
            try:
                source_type = self.utils.identify_node_type(mat)
            except Exception:
                results.append({
                    "material": mat,
                    "skipped": True,
                    "log": [f"Skipped {mat}: node no longer valid"],
                })
                continue
            if source_type == target_node_type:
                results.append({
                    "material": mat,
                    "skipped": True,
                    "log": [f"Skipped {mat.name()}: already {self.config.get_display_name(target_node_type)}"],
                })
                continue

            new_mat, log = self.convert(mat, target_node_type)
            results.append({
                "material": mat,
                "new_material": new_mat,
                "success": new_mat is not None,
                "log": log,
            })

        return results
