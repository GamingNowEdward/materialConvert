import time

import maya.cmds as cmds

from core.config_loader import ConfigLoader
import core.node_utils as node_utils
from core.logger import get_logger
from core.prerequisites import apply_prerequisites
from core.converters import AttributeConverter, CCConverter, BumpConverter, DisplacementConverter

_SOURCE = "MaterialConverter"


class MaterialConverter:

    def __init__(self, logger=None):
        self.logger = logger or get_logger()
        self.config = ConfigLoader()
        self.cc_converter = CCConverter(self.config, node_utils, logger=self.logger)
        self.attr_converter = AttributeConverter(self.config, node_utils, self.cc_converter, logger=self.logger)
        self.bump_converter = BumpConverter(self.config, node_utils, logger=self.logger)
        self.disp_converter = DisplacementConverter(self.config, node_utils, logger=self.logger)

    def convert(self, source_mat, target_node_type):
        """Convert one material.  Returns the new material node or None."""
        self.cc_converter.reset()

        with self.logger.scope(source=_SOURCE, material=source_mat, target=target_node_type):
            try:
                source_node_type = node_utils.identify_node_type(source_mat)
            except Exception as exc:
                self.logger.error(f"Failed to identify source material type for {source_mat}: {exc}")
                return None

            source_config = self.config.get_material_config(source_node_type)
            target_config = self.config.get_material_config(target_node_type)

            if not source_config:
                self.logger.error(f"Unknown source material type: {source_node_type}")
                return None
            if not target_config:
                self.logger.error(f"Unknown target material type: {target_node_type}")
                return None

            source_renderer = self.config.get_renderer_name(source_node_type)
            target_renderer = self.config.get_renderer_name(target_node_type)

            self.logger.info(
                f"Converting: {source_mat} ({self.config.get_display_name(source_node_type)}) "
                f"-> {self.config.get_display_name(target_node_type)}"
            )
            self.logger.debug(f"Renderer path: {source_renderer} -> {target_renderer}")

            try:
                attr_info = self.attr_converter.collect_attrs(source_mat, source_config)
            except Exception as exc:
                self.logger.error(f"Failed to collect attributes from {source_mat}: {exc}")
                return None

            suffix = target_config.short_name or "converted"
            base_name = source_mat + "_" + suffix
            try:
                new_mat = node_utils.create_target_material(target_node_type, base_name)
            except Exception as exc:
                self.logger.error(f"Failed to create target material {target_node_type} ({base_name}): {exc}")
                return None
            self.logger.info(f"Created: {new_mat}")

            try:
                apply_prerequisites(new_mat, target_config, logger=self.logger)
            except Exception as exc:
                self.logger.warn(f"Failed to apply prerequisites to {new_mat}: {exc}")

            try:
                if source_renderer == target_renderer:
                    self.logger.debug("Same renderer: reusing existing bump/normal node", source=_SOURCE)
                    cc_cache = {}
                    self.bump_converter.reuse_existing(source_mat, new_mat, source_renderer)
                else:
                    cc_cache = self.cc_converter.collect_chains(attr_info)
                    self.bump_converter.convert(source_mat, new_mat, source_renderer, target_renderer)

                self.attr_converter.transfer_all(
                    new_mat, source_config, target_config, target_renderer,
                    attr_info, cc_cache
                )

                if source_renderer != target_renderer:
                    self.disp_converter.convert(source_mat, new_mat, source_config, target_config, target_renderer)
            except Exception as exc:
                self.logger.error(f"Conversion failed for {source_mat}: {exc}")
                return None

            try:
                sgs = cmds.listConnections(f"{source_mat}.outColor", plugs=False) or []
            except Exception as exc:
                self.logger.warn(f"Failed to query shading engines for {source_mat}: {exc}")
                sgs = []

            connected_sgs = 0
            for sg in sgs:
                try:
                    if cmds.nodeType(sg) != "shadingEngine":
                        self.logger.debug(f"Ignoring non-shadingEngine connection {sg}", source=_SOURCE)
                        continue
                    cmds.connectAttr(f"{new_mat}.outColor", f"{sg}.surfaceShader", force=True)
                    connected_sgs += 1
                    self.logger.info(f"Reconnected shading engine: {new_mat}.outColor -> {sg}.surfaceShader")
                except Exception as exc:
                    self.logger.error(f"Failed to connect {new_mat} to {sg}.surfaceShader: {exc}")

            if connected_sgs:
                self.logger.info(f"Reconnected {connected_sgs} shading engine(s); old material disconnected: {source_mat}")
            else:
                self.logger.warn(f"No shading engine connected for {new_mat}")

            return new_mat

    def convert_all(self, materials, target_node_type):
        self.logger.info(
            f"=== Batch conversion started: {len(materials)} material(s) -> {target_node_type} ===",
            source=_SOURCE,
        )
        results = []
        started = time.perf_counter()

        try:
            cmds.undoInfo(openChunk=True)
        except Exception as exc:
            self.logger.warn(f"Failed to open undo chunk: {exc}", source=_SOURCE)

        try:
            for mat in materials:
                with self.logger.scope(source=_SOURCE, material=mat, target=target_node_type):
                    try:
                        source_type = node_utils.identify_node_type(mat)
                    except Exception as exc:
                        msg = f"Skipped {mat}: failed to identify node type: {exc}"
                        self.logger.warn(msg)
                        results.append({"material": mat, "skipped": True, "success": False, "new_material": None})
                        continue

                    if source_type == target_node_type:
                        self.logger.skip(
                            f"Skipped {mat}: already {self.config.get_display_name(target_node_type)}"
                        )
                        results.append({"material": mat, "skipped": True, "success": False, "new_material": None})
                        continue

                    try:
                        new_mat = self.convert(mat, target_node_type)
                    except Exception as exc:
                        self.logger.error(f"Conversion raised for {mat}: {exc}")
                        new_mat = None

                    results.append({
                        "material": mat,
                        "new_material": new_mat,
                        "success": new_mat is not None,
                        "skipped": False,
                    })
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception as exc:
                self.logger.warn(f"Failed to close undo chunk: {exc}", source=_SOURCE)

        elapsed = time.perf_counter() - started
        converted = sum(1 for r in results if r.get("success"))
        skipped = sum(1 for r in results if r.get("skipped"))
        failed = sum(1 for r in results if not r.get("success") and not r.get("skipped"))
        avg_ms = (elapsed * 1000.0 / len(materials)) if materials else 0.0

        self.logger.info(
            f"=== Batch conversion finished: {converted} converted, {skipped} skipped, "
            f"{failed} failed in {elapsed:.3f}s ({avg_ms:.2f} ms/material) ===",
            source=_SOURCE,
        )
        if failed:
            self.logger.warn(f"{failed} material(s) failed during batch conversion", source=_SOURCE)

        return results
