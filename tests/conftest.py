import sys
import types


def _dummy(*args, **kwargs):
    return None


def _dummy_attr(name):
    return _dummy


maya = types.ModuleType("maya")
maya.__path__ = []
maya_cmds = types.ModuleType("maya.cmds")
maya_cmds.__getattr__ = _dummy_attr
maya.cmds = maya_cmds

sys.modules.setdefault("maya", maya)
sys.modules.setdefault("maya.cmds", maya_cmds)
