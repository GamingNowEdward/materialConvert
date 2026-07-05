import pymel.core as pm
import maya.cmds as cmds


def get_materials_from_selection():
    materials = []
    seen = set()
    selection = pm.ls(sl=True)

    for node in selection:
        if node.hasAttr("outColor") and node.name() not in seen:
            seen.add(node.name())
            materials.append(node)

    if not materials:
        shapes = pm.ls(sl=True, dag=True, shapes=True, noIntermediate=True)
        for shape in shapes:
            sgs = pm.listConnections(shape, type="shadingEngine")
            if not sgs:
                continue
            for sg in sgs:
                mats = sg.surfaceShader.inputs()
                if mats:
                    for mat_node in mats:
                        if mat_node.name() not in seen:
                            seen.add(mat_node.name())
                            materials.append(mat_node)

    if not materials:
        pm.warning("No materials found on selection.")

    return materials


def identify_node_type(material):
    return pm.nodeType(material)


def collect_attribute_info(material, attr_names):
    info = {}
    for attr_name in attr_names:
        value = None
        connection = None
        plug = None

        try:
            plug = material.attr(attr_name)
        except Exception:
            info[attr_name] = {"value": None, "connection": None, "plug": None}
            continue

        connections = plug.connections(plugs=True, source=True)
        if connections:
            src_plug = connections[0]
            src_node = src_plug.node()
            connection = {"node": src_node, "plug": src_plug}
        else:
            try:
                value = plug.get()
            except Exception:
                value = None

        info[attr_name] = {"value": value, "connection": connection, "plug": plug}

    return info


def is_cc_node(node):
    node_type = pm.nodeType(node)
    cc_types = {"colorCorrect", "aiColorCorrect", "RedshiftColorCorrection", "VRayColorCorrection"}
    return node_type in cc_types


def _normalize_hue(value, src_range):
    lo, hi = src_range
    return (value - lo) / (hi - lo) * 360.0


def _denormalize_hue(value, dst_range):
    lo, hi = dst_range
    return lo + (value / 360.0) * (hi - lo)


def collect_cc_chain_params(cc_node, cc_config):
    params = {}

    for common_name, attr_name in [("gamma", cc_config.gamma), ("contrast", cc_config.contrast),
                                    ("gain", cc_config.gain), ("hue", cc_config.hue),
                                    ("saturation", cc_config.saturation)]:
        if attr_name:
            try:
                val = cc_node.attr(attr_name).get()
                if common_name == "hue" and val is not None and cc_config.hue_range:
                    val = _normalize_hue(val, cc_config.hue_range)
                params[common_name] = val
            except Exception:
                params[common_name] = None

    input_plug = None
    if cc_config.source_connection:
        try:
            conns = cc_node.attr(cc_config.source_connection).connections(plugs=True, source=True)
            if conns:
                input_plug = conns[0]
        except Exception:
            pass

    return params, input_plug


def create_cc_node(cc_config, base_name=None):
    kwargs = {"asUtility": True}
    if base_name:
        kwargs["name"] = base_name
    node_name = cmds.shadingNode(cc_config.node_type, **kwargs)
    return pm.PyNode(node_name)


def set_cc_params(cc_node, params, cc_config):
    param_map = {
        "gamma": cc_config.gamma,
        "contrast": cc_config.contrast,
        "gain": cc_config.gain,
        "hue": cc_config.hue,
        "saturation": cc_config.saturation,
    }

    for common_name, target_attr in param_map.items():
        if not target_attr:
            continue
        val = params.get(common_name)
        if val is not None:
            try:
                if common_name == "hue" and cc_config.hue_range:
                    val = _denormalize_hue(val, cc_config.hue_range)
                cc_node.attr(target_attr).set(val)
            except Exception:
                pm.warning(f"set_cc_params: failed to set {target_attr} on {cc_node.name()}")


def create_target_material(node_type, base_name):
    node_name = cmds.shadingNode(node_type, asShader=True, name=base_name)
    return pm.PyNode(node_name)


def smart_connect(src_plug, dst_plug):
    try:
        src_plug >> dst_plug
        return True
    except Exception:
        pass
    src_node = src_plug.node()
    try:
        src_node.outColor >> dst_plug
        return True
    except Exception:
        pass
    try:
        src_node.outAlpha >> dst_plug
        return True
    except Exception:
        pass
    return False


def transfer_connection_to_plug(src_plug, dst_plug):
    if src_plug is None or dst_plug is None:
        return False
    try:
        connections = src_plug.connections(plugs=True, source=True)
        if connections:
            for conn in connections:
                conn // dst_plug
            return True
    except Exception:
        pm.warning(f"transfer_connection_to_plug: failed to transfer connection to {dst_plug}")
    return False


def connect_plug_to_plug(src_plug, dst_plug):
    if src_plug is None or dst_plug is None:
        return False
    try:
        src_plug >> dst_plug
        return True
    except Exception:
        pm.warning(f"connect_plug_to_plug: failed to connect {src_plug} to {dst_plug}")
        return False


def delete_node_safe(node):
    if node is None:
        return
    try:
        pm.delete(node)
    except Exception:
        pm.warning(f"delete_node_safe: failed to delete {node}")


def get_connected_node(plug):
    try:
        conns = plug.connections(plugs=True, source=True)
        if conns:
            return conns[0]
    except Exception:
        pass
    return None


def get_shading_engine(material):
    try:
        sgs = material.outColor.connections(type="shadingEngine")
        if sgs:
            return sgs[0]
    except Exception:
        pass
    return None


def get_displacement_node_from_sg(shading_engine):
    try:
        conns = shading_engine.displacementShader.connections(plugs=False, source=True)
        if conns:
            return conns[0]
    except Exception:
        pass
    return None
