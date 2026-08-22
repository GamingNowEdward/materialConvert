import functools
import time

import maya.cmds as cmds

from core.logger import get_logger

_SOURCE = "BuilderContext"


def qt_maya_logger(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        log = getattr(self, "log", get_logger())
        renderer = args[0] if args else "Unknown"
        start_time = time.time()
        log.info(f"[START] Building {renderer} Material...", source=_SOURCE)
        try:
            result = func(self, *args, **kwargs)
            duration = time.time() - start_time
            cmds.inViewMessage(
                amg=f"Success: Action completed in <color=yellow>{duration:.2f}s</color>",
                pos="topCenter",
                fade=True,
            )
            log.info(f"[SUCCESS] Execution Time: {duration:.3f}s", source=_SOURCE)
            return result
        except Exception as exc:
            log.error(f"Action Failed: {exc}", source=_SOURCE)
            from ui import QtWidgets
            QtWidgets.QMessageBox.critical(self, "Error", f"Operation failed:\n{exc}")
            raise
    return wrapper


DEFAULT_MATERIALS = ["lambert1", "standardSurface1", "particleCloud1"]


class BuilderContext:
    def __init__(self, logger=None):
        self.log = logger or get_logger()

        import sys
        import os
        _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _ROOT not in sys.path:
            sys.path.insert(0, _ROOT)
        from core.config_loader import ConfigLoader
        self._config = ConfigLoader()
        self._naming = self._config.get_builder_naming()

        self._current_build_nodes = []

    def get_naming(self):
        return self._naming

    def connect(self, src_node, src_attr, dest_node, dest_attr):
        src = f"{src_node}.{src_attr}"
        dest = f"{dest_node}.{dest_attr}"
        try:
            if cmds.isConnected(src, dest):
                self.log.debug(f"Already connected: {src} -> {dest}", source=_SOURCE)
                return
            cmds.connectAttr(src, dest, force=True)
            self.log.debug(f"Connected: {src} -> {dest}", source=_SOURCE)
        except Exception as exc:
            self.log.error(f"Failed to connect {src} -> {dest}: {exc}", source=_SOURCE)
            raise

    def create_node(self, node_type, prefix_key, base_name, suffix_key=None, as_type='utility'):
        p, s = self._naming["prefix"][prefix_key], self._naming["suffix"].get(suffix_key, "")
        full_name = f"{p}{base_name}{s}"
        create_modes = {'shader': {'asShader': True}, 'texture': {'asTexture': True}, 'utility': {'asUtility': True}}
        node = cmds.shadingNode(node_type, name=full_name, **create_modes.get(as_type, {'asUtility': True}))
        if hasattr(self, '_current_build_nodes'):
            self._current_build_nodes.append(node)
        self.log.debug(f"Created {node_type} node {node} ({as_type})", source=_SOURCE)
        return node

    def build_layered_node(self, base_name, suffix_key, layers=3):
        lyr = self.create_node('layeredTexture', 'layered', base_name, suffix_key, 'texture')
        for i in range(layers):
            if i < len(self._naming["layered_colors"]):
                cmds.setAttr(f"{lyr}.inputs[{i}].color", *self._naming["layered_colors"][i], type="double3")
                cmds.setAttr(f"{lyr}.inputs[{i}].blendMode", self._naming["layered_blend_modes"][i])
        self.log.debug(f"Built layeredTexture {lyr} with {layers} layer(s)", source=_SOURCE)
        return lyr

    @staticmethod
    def clean_path(path_str):
        path_str = path_str.strip()
        if path_str.startswith("file:///"):
            path_str = path_str.replace("file:///", "")
        return path_str
