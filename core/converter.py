import time

import maya.cmds as cmds

from core.config_loader import ConfigLoader
import core.node_utils as node_utils
from core.logger import get_logger
from core.prerequisites import apply_prerequisites
from core.converters import AttributeConverter, CCConverter, BumpConverter, DisplacementConverter
from core.results import ConversionResult, summarize_results

_SOURCE = "MaterialConverter"


class MaterialConverter:

    def __init__(self, logger=None, config=None):
        self.logger = logger or get_logger()
        self.config = config or ConfigLoader()
        self.cc_converter = CCConverter(self.config, node_utils, logger=self.logger)
        self.attr_converter = AttributeConverter(self.config, node_utils, self.cc_converter, logger=self.logger)
        self.bump_converter = BumpConverter(self.config, node_utils, logger=self.logger)
        self.disp_converter = DisplacementConverter(self.config, node_utils, logger=self.logger)

    def convert(self, source_mat, target_node_type):
        """Convert one material.  Returns a ConversionResult; never None.

        Scene wiring is reported separately from network transfer: a material
        that was created and transferred but could not be reconnected to any of
        its shading engines ends up ``unwired`` (see core.results), so the UI
        never presents it as a plain success while the scene still renders the
        old material.
        """
        self.cc_converter.reset()
        result = ConversionResult(material=source_mat)

        with self.logger.scope(source=_SOURCE, material=source_mat, target=target_node_type):
            try:
                source_node_type = node_utils.identify_node_type(source_mat, logger=self.logger)
            except Exception as exc:
                self.logger.error(f"Failed to identify source material type for {source_mat}: {exc}", nodes=(source_mat,))
                result.reason = f"failed to identify source material type: {exc}"
                return result

            source_config = self.config.get_material_config(source_node_type)
            target_config = self.config.get_material_config(target_node_type)

            if not source_config:
                self.logger.error(f"Unknown source material type: {source_node_type}")
                result.reason = f"unknown source material type: {source_node_type}"
                return result
            if not target_config:
                self.logger.error(f"Unknown target material type: {target_node_type}")
                result.reason = f"unknown target material type: {target_node_type}"
                return result

            source_renderer = self.config.get_renderer_name(source_node_type)
            target_renderer = self.config.get_renderer_name(target_node_type)

            self.logger.info(
                f"Converting: {source_mat} ({self.config.get_display_name(source_node_type)}) "
                f"-> {self.config.get_display_name(target_node_type)}",
                nodes=(source_mat,),
            )
            self.logger.debug(f"Renderer path: {source_renderer} -> {target_renderer}")

            try:
                attr_info = self.attr_converter.collect_attrs(source_mat, source_config)
            except Exception as exc:
                self.logger.error(f"Failed to collect attributes from {source_mat}: {exc}", nodes=(source_mat,))
                result.reason = f"failed to collect attributes: {exc}"
                return result

            # Enumerate every shading engine once, BEFORE creating anything: a
            # failure here means the result cannot be wired, so abort instead of
            # silently reporting success (displacement also needs the SG list).
            sgs, sgs_ok = self._find_shading_engines(source_mat)
            if not sgs_ok:
                self.logger.error(
                    f"Failed to enumerate shading engines for {source_mat}; conversion aborted",
                    nodes=(source_mat,),
                )
                result.reason = "failed to enumerate shading engines"
                return result
            result.total_sgs = len(sgs)

            suffix = target_config.short_name or "converted"
            base_name = source_mat + "_" + suffix
            try:
                new_mat = node_utils.create_target_material(target_node_type, base_name, logger=self.logger)
            except Exception as exc:
                self.logger.error(f"Failed to create target material {target_node_type} ({base_name}): {exc}", nodes=(source_mat,))
                result.reason = f"failed to create target material: {exc}"
                return result
            result.new_material = new_mat
            result.created = True
            self.logger.info(f"Created: {new_mat}", nodes=(new_mat,))

            if not apply_prerequisites(new_mat, target_config, logger=self.logger):
                self.logger.error(
                    f"Failed to apply prerequisites to {new_mat}; conversion aborted",
                    nodes=(new_mat,),
                )
                result.reason = "failed to apply prerequisites"
                return result

            try:
                if source_renderer == target_renderer:
                    self.logger.debug("Same renderer: reusing existing bump/normal node", source=_SOURCE)
                    cc_cache = {}
                    bump_ok = self.bump_converter.reuse_existing(source_mat, new_mat, source_renderer)
                else:
                    cc_cache = self.cc_converter.collect_chains(attr_info)
                    bump_ok = self.bump_converter.convert(source_mat, new_mat, source_renderer, target_renderer)

                if not bump_ok:
                    self.logger.error(f"Bump/Normal conversion failed for {source_mat}", nodes=(source_mat, new_mat))
                    result.reason = "bump/normal conversion failed"
                    return result

                report = self.attr_converter.transfer_all(
                    new_mat, source_config, target_config, target_renderer,
                    attr_info, cc_cache,
                    invert_attrs=self._resolve_inverted_attrs(source_mat, source_config),
                )
                if report.critical:
                    self.logger.error(
                        f"Critical attribute transfer failure for {source_mat}: "
                        f"{'; '.join(report.critical)}",
                        nodes=(new_mat,),
                    )
                    result.reason = "critical attribute transfer failure"
                    return result
                result.issues.extend(report.issues)

                if source_renderer != target_renderer:
                    if not self.disp_converter.convert(
                            source_mat, new_mat, source_config, target_config,
                            target_renderer, sgs):
                        self.logger.error(f"Displacement conversion failed for {source_mat}", nodes=(source_mat, new_mat))
                        result.reason = "displacement conversion failed"
                        return result
            except Exception as exc:
                self.logger.error(f"Conversion failed for {source_mat}: {exc}", nodes=(source_mat,))
                result.reason = f"conversion failed: {exc}"
                return result

            result.converted = True

            wired_nodes = []
            for sg in sgs:
                try:
                    cmds.connectAttr(f"{new_mat}.outColor", f"{sg}.surfaceShader", force=True)
                    result.wired += 1
                    wired_nodes.append(sg)
                    self.logger.info(f"Reconnected shading engine: {new_mat}.outColor -> {sg}.surfaceShader", nodes=(new_mat, sg))
                except Exception as exc:
                    self.logger.error(f"Failed to connect {new_mat} to {sg}.surfaceShader: {exc}", nodes=(new_mat, sg))

            if wired_nodes:
                self.logger.info(
                    f"Reconnected {result.wired} shading engine(s); old material disconnected: {source_mat}",
                    nodes=(source_mat, new_mat, *wired_nodes),
                )
            elif result.total_sgs:
                self.logger.error(
                    f"No shading engine reconnected for {new_mat}: {result.total_sgs} shading engine(s) "
                    f"of {source_mat} still reference the old material",
                    nodes=(source_mat, new_mat),
                )
                result.reason = "shading engine reconnection failed"
            else:
                self.logger.warn(f"No shading engine connected for {new_mat}", nodes=(new_mat,))

            return result

    def _find_shading_engines(self, source_mat):
        """Shading engines fed by *source_mat* as ``(list, ok)``.

        ``ok`` is False when the query itself fails, so the caller can abort
        rather than treat a failed enumeration as "no shading engine" (which
        would silently report a floating material as a success).
        """
        try:
            return (cmds.listConnections(f"{source_mat}.outColor", type="shadingEngine") or [], True)
        except Exception as exc:
            self.logger.warn(f"Failed to query shading engines for {source_mat}: {exc}", nodes=(source_mat,))
            return ([], False)

    def _resolve_inverted_attrs(self, source_mat, source_config):
        """Common attributes whose source value must be inverted (1 - x) on transfer.

        Declared in the source config under ``material.invert`` as
        ``{common_attr: {attribute, value}}``: the channel inverts when the source
        material's ``attribute`` equals ``value`` (a bare ``true`` inverts always).
        Only generic attribute names are used here; renderer specifics stay in JSON.
        """
        inverted = set()
        for common_attr, spec in source_config.get_inverts().items():
            if not source_config.get_maya_attr(common_attr):
                self.logger.debug(
                    f"invert declared for unmapped common attr {common_attr}; ignored",
                    source=_SOURCE, nodes=(source_mat,),
                )
                continue

            if spec is True:
                inverted.add(common_attr)
                continue

            if not isinstance(spec, dict):
                self.logger.warn(
                    f"Invalid invert spec for {common_attr}: {spec!r}",
                    source=_SOURCE, nodes=(source_mat,),
                )
                continue

            toggle_attr = spec.get("attribute")
            toggle_value = spec.get("value")
            if not toggle_attr or toggle_value is None:
                self.logger.warn(
                    f"Incomplete invert spec for {common_attr}: {spec!r}",
                    source=_SOURCE, nodes=(source_mat,),
                )
                continue

            try:
                actual = cmds.getAttr(f"{source_mat}.{toggle_attr}")
            except Exception as exc:
                self.logger.warn(
                    f"Failed to read {source_mat}.{toggle_attr} for invert decision "
                    f"on {common_attr}: {exc}; assuming inverted (glossiness default)",
                    source=_SOURCE, nodes=(source_mat,),
                )
                inverted.add(common_attr)
                continue

            if actual == toggle_value:
                inverted.add(common_attr)
                self.logger.debug(
                    f"{common_attr}: invert enabled ({source_mat}.{toggle_attr}={actual!r})",
                    source=_SOURCE, nodes=(source_mat,),
                )

        if inverted:
            self.logger.debug(
                f"Inverted common attr(s): {sorted(inverted)}",
                source=_SOURCE, nodes=(source_mat,),
            )
        return inverted

    def _convert_one_safe(self, mat, target_node_type):
        """Batch item wrapper: never raises, always returns a ConversionResult."""
        try:
            source_type = node_utils.identify_node_type(mat, logger=self.logger)
        except Exception as exc:
            message = f"Skipped {mat}: failed to identify node type: {exc}"
            self.logger.warn(message, nodes=(mat,))
            return ConversionResult(material=mat, skipped=True, reason=message)

        if source_type == target_node_type:
            message = f"Skipped {mat}: already {self.config.get_display_name(target_node_type)}"
            self.logger.skip(message, nodes=(mat,))
            return ConversionResult(material=mat, skipped=True, reason=message)

        try:
            return self.convert(mat, target_node_type)
        except Exception as exc:
            self.logger.error(f"Conversion raised for {mat}: {exc}", nodes=(mat,))
            return ConversionResult(material=mat, reason=f"conversion raised: {exc}")

    def convert_all(self, materials, target_node_type, on_progress=None):
        """Batch conversion with an optional per-material progress callback.

        ``on_progress(done, total, result)`` is invoked after each material on
        the calling thread.  Exceptions raised by the callback are logged and
        ignored so that feedback can never abort or change the batch.  Returns
        the list of ConversionResult in input order.
        """
        total = len(materials)
        self.logger.info(
            f"=== Batch conversion started: {total} material(s) -> {target_node_type} ===",
            source=_SOURCE,
        )
        results = []
        started = time.perf_counter()

        try:
            cmds.undoInfo(openChunk=True)
        except Exception as exc:
            self.logger.warn(f"Failed to open undo chunk: {exc}", source=_SOURCE)

        try:
            for index, mat in enumerate(materials, start=1):
                with self.logger.scope(source=_SOURCE, material=mat, target=target_node_type):
                    result = self._convert_one_safe(mat, target_node_type)
                results.append(result)
                if on_progress is not None:
                    try:
                        on_progress(index, total, result)
                    except Exception as exc:
                        self.logger.warn(f"Progress callback failed after {index}/{total}: {exc}", source=_SOURCE)
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception as exc:
                self.logger.warn(f"Failed to close undo chunk: {exc}", source=_SOURCE)

        elapsed = time.perf_counter() - started
        summary = summarize_results(results)
        avg_ms = (elapsed * 1000.0 / total) if total else 0.0

        self.logger.info(
            f"=== Batch conversion finished: {summary['converted']} converted, "
            f"{summary['skipped']} skipped, {summary['failed']} failed "
            f"in {elapsed:.3f}s ({avg_ms:.2f} ms/material) ===",
            source=_SOURCE,
        )
        if summary["unwired"]:
            self.logger.warn(
                f"{summary['unwired']} material(s) were created but could not be wired to any "
                f"shading engine; the scene still uses the old materials",
                source=_SOURCE,
            )
        if summary["partial_wired"]:
            self.logger.warn(
                f"{summary['partial_wired']} material(s) were wired to only some shading engines",
                source=_SOURCE,
            )
        if summary["with_issues"]:
            self.logger.warn(
                f"{summary['with_issues']} material(s) converted with channel issue(s); "
                f"see the WARN entries above",
                source=_SOURCE,
            )
        if summary["failed"]:
            self.logger.warn(f"{summary['failed']} material(s) failed during batch conversion", source=_SOURCE)

        return results
