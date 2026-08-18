import maya.cmds as cmds

RENDERER_SHORT = {"arnold": "ai", "redshift": "rs", "vray": "vray"}


def get_materials_from_selection():
    materials = []
    seen = set()
    selection = cmds.ls(sl=True) or []

    for node in selection:
        try:
            if cmds.attributeQuery("outColor", node=node, exists=True) and node not in seen:
                seen.add(node)
                materials.append(node)
        except Exception:
            pass

    if not materials:
        shapes = cmds.ls(sl=True, dag=True, shapes=True, noIntermediate=True) or []
        for shape in shapes:
            sgs = cmds.listConnections(shape, type="shadingEngine") or []
            if not sgs:
                continue
            for sg in sgs:
                mats = cmds.listConnections(f"{sg}.surfaceShader", source=True, destination=False) or []
                for mat_node in mats:
                    if mat_node not in seen:
                        seen.add(mat_node)
                        materials.append(mat_node)

    if not materials:
        cmds.warning("No materials found on selection.")

    return materials


def identify_node_type(material):
    return cmds.nodeType(material)


def collect_attribute_info(material, attr_names):
    info = {}
    for attr_name in attr_names:
        value = None
        connection = None
        plug = f"{material}.{attr_name}"

        if not cmds.objExists(plug):
            info[attr_name] = {"value": None, "connection": None, "plug": None}
            continue

        connections = cmds.listConnections(plug, plugs=True, source=True) or []
        if connections:
            src_plug = connections[0]
            src_node = src_plug.split(".")[0]
            connection = {"node": src_node, "plug": src_plug}
        else:
            try:
                value = cmds.getAttr(plug)
                if isinstance(value, list) and value and isinstance(value[0], (tuple, list)):
                    value = value[0]
            except Exception:
                value = None

        info[attr_name] = {"value": value, "connection": connection, "plug": plug}

    return info


def is_cc_node(node, config):
    """Return whether *node* is a configured color-correction node.

    The supported types come from ``colorCorrection.json`` through
    ``ConfigLoader`` so renderer extensions do not require a code edit here.
    """
    try:
        return cmds.nodeType(node) in config.get_all_cc_types()
    except Exception:
        return False


def _hue_to_offset(value, cc_config):
    """渲染器 hue 值 → 通用偏移角 [-180, 180](0 = 无变化)。"""
    if not cc_config.hue_range:
        return value
    lo, hi = cc_config.hue_range
    if lo == -hi:
        return value * (180.0 / hi)
    center = cc_config.hue_center
    offset = value - center
    if offset > 180.0:
        offset -= 360.0
    elif offset < -180.0:
        offset += 360.0
    return offset


def _offset_to_hue(offset, cc_config):
    """通用偏移角 [-180, 180] → 渲染器 hue 值。"""
    if not cc_config.hue_range:
        return offset
    lo, hi = cc_config.hue_range
    if lo == -hi:
        return offset * (hi / 180.0)
    return (offset + cc_config.hue_center) % 360.0


def collect_cc_chain_params(cc_node, cc_config):
    params = {}

    for common_name, attr_name in [("gamma", cc_config.gamma), ("contrast", cc_config.contrast),
                                    ("gain", cc_config.gain), ("hue", cc_config.hue),
                                    ("saturation", cc_config.saturation)]:
        if attr_name:
            try:
                val = cmds.getAttr(f"{cc_node}.{attr_name}")
                if common_name == "hue" and val is not None and cc_config.hue_range:
                    val = _hue_to_offset(val, cc_config)
                params[common_name] = val
            except Exception:
                params[common_name] = None

    input_plug = None
    if cc_config.source_connection:
        try:
            conns = cmds.listConnections(f"{cc_node}.{cc_config.source_connection}", plugs=True, source=True) or []
            if conns:
                input_plug = conns[0]
        except Exception:
            pass

    return params, input_plug


def create_cc_node(cc_config, base_name=None):
    kwargs = {"asUtility": True}
    if base_name:
        kwargs["name"] = base_name
    return cmds.shadingNode(cc_config.node_type, **kwargs)


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
                    val = _offset_to_hue(val, cc_config)
                cmds.setAttr(f"{cc_node}.{target_attr}", val)
            except Exception:
                cmds.warning(f"set_cc_params: failed to set {target_attr} on {cc_node}")


def create_target_material(node_type, base_name):
    return cmds.shadingNode(node_type, asShader=True, name=base_name)


def smart_connect(src_plug, dst_plug):
    if not src_plug or not dst_plug:
        return False
    try:
        if cmds.isConnected(src_plug, dst_plug):
            return True
    except Exception:
        pass
    try:
        cmds.connectAttr(src_plug, dst_plug, force=True)
        return True
    except Exception:
        pass
    src_node = src_plug.split(".")[0]
    try:
        cmds.connectAttr(f"{src_node}.outColor", dst_plug, force=True)
        return True
    except Exception:
        pass
    try:
        cmds.connectAttr(f"{src_node}.outAlpha", dst_plug, force=True)
        return True
    except Exception:
        pass
    return False


def transfer_connection_to_plug(src_plug, dst_plug):
    if src_plug is None or dst_plug is None:
        return False
    try:
        connections = cmds.listConnections(src_plug, plugs=True, source=True) or []
        if connections:
            for conn in connections:
                cmds.disconnectAttr(conn, dst_plug)
            return True
    except Exception:
        cmds.warning(f"transfer_connection_to_plug: failed to transfer connection to {dst_plug}")
    return False


def connect_plug_to_plug(src_plug, dst_plug):
    if src_plug is None or dst_plug is None:
        return False
    try:
        cmds.connectAttr(src_plug, dst_plug, force=True)
        return True
    except Exception:
        cmds.warning(f"connect_plug_to_plug: failed to connect {src_plug} to {dst_plug}")
        return False


def delete_node_safe(node):
    if node is None:
        return
    try:
        cmds.delete(node)
    except Exception:
        cmds.warning(f"delete_node_safe: failed to delete {node}")


def get_connected_node(plug):
    try:
        conns = cmds.listConnections(plug, plugs=True, source=True) or []
        if conns:
            return conns[0]
    except Exception:
        pass
    return None


def get_shading_engine(material):
    try:
        sgs = cmds.listConnections(f"{material}.outColor", type="shadingEngine") or []
        if sgs:
            return sgs[0]
    except Exception:
        pass
    return None


def get_displacement_node_from_sg(shading_engine):
    try:
        conns = cmds.listConnections(f"{shading_engine}.displacementShader", source=True, destination=False) or []
        if conns:
            return conns[0]
    except Exception:
        pass
    return None
