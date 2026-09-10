import time

import maya.cmds as cmds

from core.builder_context import BuilderContext
from core.logger import get_logger
from core.material_builder import MaterialBuilder
from core.results import BuildResult, summarize_build_results

_SOURCE = "BatchBuilder"


class BatchBuilder:

    def __init__(self, ctx: BuilderContext, logger=None):
        self.ctx = ctx
        self.log = logger or get_logger()
        self.builder = MaterialBuilder(ctx, logger=self.log)

    def build_material(self, node_type, material, use_full_chain=True, use_qss=True):
        """Build one material from a scanner material dict.

        material = {
            "name": str,
            "channels": {
                common_attr: {
                    "channel": str,
                    "path": str,
                    "options": dict,
                }
            }
        }
        """
        input_paths = {}
        channel_options = {}

        for common_attr, data in material.get("channels", {}).items():
            input_paths[common_attr] = data["path"]
            if data.get("options"):
                channel_options[common_attr] = dict(data["options"])

        self.log.debug(
            f"Batch-building {material['name']}: {len(input_paths)} channel(s), "
            f"full_chain={use_full_chain}, qss={use_qss}",
            source=_SOURCE,
        )

        return self.builder.build(
            node_type,
            material["name"],
            input_paths,
            use_qss=use_qss,
            use_full_chain=use_full_chain,
            channel_options=channel_options,
        )

    def _build_one_safe(self, node_type, material, use_full_chain, use_qss):
        """Batch item wrapper: never raises, always returns a BuildResult."""
        name = material.get("name", "")
        try:
            new_mat = self.build_material(
                node_type,
                material,
                use_full_chain=use_full_chain,
                use_qss=use_qss,
            )
        except Exception as exc:
            self.log.error(f"Failed to build {name}: {exc}", source=_SOURCE)
            return BuildResult(material=name, reason=str(exc))

        self.log.info(f"Built {name} -> {new_mat}", source=_SOURCE, nodes=(new_mat,))
        return BuildResult(material=name, new_material=new_mat, built=True)

    def build_all(self, materials, node_type, use_full_chain=True, use_qss=True,
                  on_progress=None):
        """Batch build with an optional per-material progress callback.

        ``on_progress(done, total, result)`` is invoked after each material on
        the calling thread.  Exceptions raised by the callback are logged and
        ignored so that feedback can never abort or change the batch.  Undo
        chunking and per-item failure isolation live here in core; the UI only
        displays progress and the returned results.  Returns the list of
        BuildResult in input order.
        """
        materials = list(materials)
        total = len(materials)
        self.log.info(
            f"=== Batch build started: {total} material(s) -> {node_type} ===",
            source=_SOURCE,
        )
        results = []
        started = time.perf_counter()

        try:
            cmds.undoInfo(openChunk=True)
        except Exception as exc:
            self.log.warn(f"Failed to open undo chunk: {exc}", source=_SOURCE)

        try:
            for index, material in enumerate(materials, start=1):
                with self.log.scope(source=_SOURCE, material=material.get("name"),
                                    target=node_type):
                    result = self._build_one_safe(
                        node_type, material, use_full_chain, use_qss
                    )
                results.append(result)
                if on_progress is not None:
                    try:
                        on_progress(index, total, result)
                    except Exception as exc:
                        self.log.warn(
                            f"Progress callback failed after {index}/{total}: {exc}",
                            source=_SOURCE,
                        )
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception as exc:
                self.log.warn(f"Failed to close undo chunk: {exc}", source=_SOURCE)

        elapsed = time.perf_counter() - started
        summary = summarize_build_results(results)
        avg_ms = (elapsed * 1000.0 / total) if total else 0.0

        self.log.info(
            f"=== Batch build finished: {summary['built']} built, "
            f"{summary['failed']} failed in {elapsed:.3f}s "
            f"({avg_ms:.2f} ms/material) ===",
            source=_SOURCE,
        )
        if summary["failed"]:
            self.log.warn(
                f"{summary['failed']} material(s) failed during batch build",
                source=_SOURCE,
            )

        return results
