import pymel.core as pm

from core.config_loader import ConfigLoader
import core.node_utils as node_utils
from core.prerequisites import apply_prerequisites
from core.converters import AttributeConverter, CCConverter, BumpConverter, DisplacementConverter
from core.logger import Logger


class MaterialConverter:

    def __init__(self, logger=None):
        self.config = ConfigLoader()
        self.cc_converter = CCConverter(self.config, node_utils)
        self.attr_converter = AttributeConverter(self.config, node_utils, self.cc_converter)
        self.bump_converter = BumpConverter(self.config, node_utils)
        self.disp_converter = DisplacementConverter(self.config, node_utils)
        self.logger = logger or Logger()

    def convert(self, source_mat, target_node_type):
        self.cc_converter.reset()
        log = []

        source_node_type = node_utils.identify_node_type(source_mat)
        source_config = self.config.get_material_config(source_node_type)
        target_config = self.config.get_material_config(target_node_type)

        if not source_config:
            msg = f"[ERROR] Unknown source material type: {source_node_type}"
            log.append(msg)
            self.logger.log(msg, error=True)
            return None, log
        if not target_config:
            msg = f"[ERROR] Unknown target material type: {target_node_type}"
            log.append(msg)
            self.logger.log(msg, error=True)
            return None, log

        source_renderer = self.config.get_renderer_name(source_node_type)
        target_renderer = self.config.get_renderer_name(target_node_type)

        msg = f"Converting: {source_mat.name()} ({self.config.get_display_name(source_node_type)})"
        log.append(msg)
        self.logger.log(msg)
        msg = f"       to: {self.config.get_display_name(target_node_type)}"
        log.append(msg)
        self.logger.log(msg)

        attr_info = self.attr_converter.collect_attrs(source_mat, source_config)

        suffix = target_config.short_name or "converted"
        base_name = source_mat.name() + "_" + suffix
        new_mat = node_utils.create_target_material(target_node_type, base_name)
        msg = f"Created: {new_mat.name()}"
        log.append(msg)
        self.logger.log(msg)

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
                    pm.warning(f"MaterialConverter: failed to connect {new_mat.name()} to {sg.name()}.surfaceShader")

        msg = f"Disconnected old material: {source_mat.name()}"
        log.append(msg)
        self.logger.log(msg)

        return new_mat, log

    def convert_all(self, materials, target_node_type):
        self.logger.clear()
        results = []

        import maya.cmds as cmds
        cmds.undoInfo(openChunk=True)

        try:
            for mat in materials:
                try:
                    source_type = node_utils.identify_node_type(mat)
                except Exception:
                    msg = f"Skipped {mat}: node no longer valid"
                    results.append({
                        "material": mat,
                        "skipped": True,
                        "log": [msg],
                    })
                    self.logger.log(msg)
                    continue
                if source_type == target_node_type:
                    msg = f"Skipped {mat.name()}: already {self.config.get_display_name(target_node_type)}"
                    results.append({
                        "material": mat,
                        "skipped": True,
                        "log": [msg],
                    })
                    self.logger.log(msg)
                    continue

                new_mat, log = self.convert(mat, target_node_type)
                results.append({
                    "material": mat,
                    "new_material": new_mat,
                    "success": new_mat is not None,
                    "log": log,
                })
        finally:
            cmds.undoInfo(closeChunk=True)

        return results
