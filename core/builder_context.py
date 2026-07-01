import maya.cmds as cmds
import time
import functools


def qt_maya_logger(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        renderer = args[0] if args else "Unknown"
        start_time = time.time()
        print(f"\n# [START] Building {renderer} Material...")
        try:
            result = func(self, *args, **kwargs)
            duration = time.time() - start_time
            cmds.inViewMessage(amg=f"Success: Action completed in <color=yellow>{duration:.2f}s</color>", pos='topCenter', fade=True)
            print(f"# [SUCCESS] Execution Time: {duration:.3f}s")
            return result
        except Exception as e:
            cmds.warning(f"Action Failed: {str(e)}")
            from ui import QtWidgets
            QtWidgets.QMessageBox.critical(self, "Error", f"Operation failed:\n{str(e)}")
            raise
    return wrapper


DEFAULT_MATERIALS = ["lambert1", "standardSurface1", "particleCloud1"]


class BuilderContext:
    def __init__(self):
        import sys, os
        _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _ROOT not in sys.path:
            sys.path.insert(0, _ROOT)
        from core.config_loader import ConfigLoader
        self._config = ConfigLoader()
        self._naming = self._config.get_builder_naming()

        self._current_build_nodes = []

    def get_builder_spec(self, renderer):
        return self._config.get_builder_spec(renderer)

    def get_naming(self):
        return self._naming

    @staticmethod
    def connect(src_node, src_attr, dest_node, dest_attr):
        src, dest = f"{src_node}.{src_attr}", f"{dest_node}.{dest_attr}"
        if not cmds.isConnected(src, dest):
            cmds.connectAttr(src, dest, force=True)

    def create_node(self, node_type, prefix_key, base_name, suffix_key=None, as_type='utility'):
        p, s = self._naming["prefix"][prefix_key], self._naming["suffix"].get(suffix_key, "")
        full_name = f"{p}{base_name}{s}"
        create_modes = {'shader': {'asShader': True}, 'texture': {'asTexture': True}, 'utility': {'asUtility': True}}
        node = cmds.shadingNode(node_type, name=full_name, **create_modes.get(as_type, {'asUtility': True}))
        if hasattr(self, '_current_build_nodes'):
            self._current_build_nodes.append(node)
        return node

    def build_layered_node(self, base_name, suffix_key, layers=3):
        lyr = self.create_node('layeredTexture', 'layered', base_name, suffix_key, 'texture')
        for i in range(layers):
            if i < len(self._naming["layered_colors"]):
                cmds.setAttr(f"{lyr}.inputs[{i}].color", *self._naming["layered_colors"][i], type="double3")
                cmds.setAttr(f"{lyr}.inputs[{i}].blendMode", self._naming["layered_blend_modes"][i])
        return lyr

    @staticmethod
    def clean_path(path_str):
        path_str = path_str.strip()
        if path_str.startswith("file:///"):
            path_str = path_str.replace("file:///", "")
        return path_str
