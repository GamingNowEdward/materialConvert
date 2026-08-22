import maya.cmds as cmds

from core.logger import get_logger

RENDERER_SHORT = {"arnold": "ai", "redshift": "rs", "vray": "vray"}

_SOURCE = "node_utils"


def _log_or_default(logger):
    return logger or get_logger()


def get_materials_from_selection(logger=None):
    log = _log_or_default(logger)
    materials = []
    seen = set()
    selection = cmds.ls(sl=True) or []

    log.debug(f"Scanning {len(selection)} selected node(s) for materials", source=_SOURCE)

    for node in selection:
        try:
            if cmds.attributeQuery("outColor", node=node, exists=True) and node not in seen:
                seen.add(node)
                materials.append(node)
                log.debug(f"Selected node is a material: {node}", source=_SOURCE)
        except Exception as exc:
            log.warn(f"Failed to query outColor on {node}: {exc}", source=_SOURCE)

    if not materials:
        shapes = cmds.ls(sl=True, dag=True, shapes=True, noIntermediate=True) or []
        log.debug(
            f"No direct material nodes found; tracing {len(shapes)} shape(s) through shading engines",
            source=_SOURCE,
        )
        for shape in shapes:
            try:
                sgs = cmds.listConnections(shape, type="shadingEngine") or []
            except Exception as exc:
                log.warn(f"Failed to list shading engines for {shape}: {exc}", source=_SOURCE)
                continue

            if not sgs:
                log.debug(f"No shading engine found on {shape}", source=_SOURCE)
                continue
            for sg in sgs:
                try:
                    mats = cmds.listConnections(f"{sg}.surfaceShader", source=True, destination=False) or []
                except Exception as exc:
                    log.warn(f"Failed to list surfaceShader connections on {sg}: {exc}", source=_SOURCE)
                    continue
                for mat_node in mats:
                    if mat_node not in seen:
                        seen.add(mat_node)
                        materials.append(mat_node)
                        log.debug(f"Found material {mat_node} via {sg}", source=_SOURCE)

    if not materials:
        log.warn("No materials found on selection.", source=_SOURCE)
    else:
        log.info(f"Found {len(materials)} material(s) from selection", source=_SOURCE)

    return materials


def identify_node_type(material):
    node_type = cmds.nodeType(material)
    get_logger().debug(f"Identified {material} as {node_type}", source=_SOURCE)
    return node_type


def collect_attribute_info(material, attr_names, logger=None):
    log = _log_or_default(logger)
    info = {}
    log.debug(f"Collecting {len(attr_names)} attribute(s) from {material}", source=_SOURCE)

    for attr_name in attr_names:
        value = None
        connection = None
        plug = f"{material}.{attr_name}"

        try:
            plug_exists = cmds.objExists(plug)
        except Exception as exc:
            log.warn(f"Failed to query existence of {plug}: {exc}", source=_SOURCE)
            plug_exists = False

        if not plug_exists:
            info[attr_name] = {"value": None, "connection": None, "plug": None}
            log.debug(f"{plug}: plug does not exist, skipped", source=_SOURCE)
            continue

        try:
            connections = cmds.listConnections(plug, plugs=True, source=True) or []
        except Exception as exc:
            log.warn(f"Failed to list connections for {plug}: {exc}", source=_SOURCE)
            connections = []

        if connections:
            src_plug = connections[0]
            src_node = src_plug.split(".")[0]
            connection = {"node": src_node, "plug": src_plug}
            log.debug(f"{plug}: connected from {src_plug}", source=_SOURCE)
        else:
            try:
                value = cmds.getAttr(plug)
                if isinstance(value, list) and value and isinstance(value[0], (tuple, list)):
                    value = value[0]
                log.debug(f"{plug}: value={value!r}", source=_SOURCE)
            except Exception as exc:
                value = None
                log.warn(f"Failed to read value from {plug}: {exc}", source=_SOURCE)

        info[attr_name] = {"value": value, "connection": connection, "plug": plug}

    return info


def is_cc_node(node, config, logger=None):
    """Return whether *node* is a configured color-correction node.

    The supported types come from ``colorCorrection.json`` through
    ``ConfigLoader`` so renderer extensions do not require a code edit here.
    """
    log = _log_or_default(logger)
    try:
        result = cmds.nodeType(node) in config.get_all_cc_types()
        log.debug(f"CC node check {node}: {result}", source=_SOURCE)
        return result
    except Exception as exc:
        log.warn(f"Failed to identify CC node {node}: {exc}", source=_SOURCE)
        return False


def _hue_to_offset(value, cc_config):
    """Renderer hue value -> generic offset angle [-180, 180] (0 = no change)."""
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
    """Generic offset angle [-180, 180] -> renderer hue value."""
    if not cc_config.hue_range:
        return offset
    lo, hi = cc_config.hue_range
    if lo == -hi:
        return offset * (hi / 180.0)
    return (offset + cc_config.hue_center) % 360.0


def collect_cc_chain_params(cc_node, cc_config, logger=None):
    log = _log_or_default(logger)
    params = {}

    for common_name, attr_name in [("gamma", cc_config.gamma), ("contrast", cc_config.contrast),
                                    ("gain", cc_config.gain), ("hue", cc_config.hue),
                                    ("saturation", cc_config.saturation)]:
        if not attr_name:
            continue
        try:
            val = cmds.getAttr(f"{cc_node}.{attr_name}")
            if common_name == "hue" and val is not None and cc_config.hue_range:
                val = _hue_to_offset(val, cc_config)
            params[common_name] = val
            log.debug(f"Read CC {cc_node}.{attr_name} = {val!r}", source=_SOURCE)
        except Exception as exc:
            params[common_name] = None
            log.warn(f"Failed to read CC {cc_node}.{attr_name}: {exc}", source=_SOURCE)

    input_plug = None
    if cc_config.source_connection:
        try:
            conns = cmds.listConnections(f"{cc_node}.{cc_config.source_connection}", plugs=True, source=True) or []
            if conns:
                input_plug = conns[0]
                log.debug(f"CC {cc_node} input connection: {input_plug}", source=_SOURCE)
            else:
                log.debug(f"CC {cc_node} has no input connection on {cc_config.source_connection}", source=_SOURCE)
        except Exception as exc:
            log.warn(f"Failed to query CC input on {cc_node}.{cc_config.source_connection}: {exc}", source=_SOURCE)

    return params, input_plug


def create_cc_node(cc_config, base_name=None):
    kwargs = {"asUtility": True}
    if base_name:
        kwargs["name"] = base_name
    node = cmds.shadingNode(cc_config.node_type, **kwargs)
    get_logger().debug(f"Created CC node {node}", source=_SOURCE)
    return node


def set_cc_params(cc_node, params, cc_config, logger=None):
    log = _log_or_default(logger)
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
        if val is None:
            continue
        try:
            if common_name == "hue" and cc_config.hue_range:
                val = _offset_to_hue(val, cc_config)
            cmds.setAttr(f"{cc_node}.{target_attr}", val)
            log.debug(f"Set CC {cc_node}.{target_attr} = {val!r}", source=_SOURCE)
        except Exception as exc:
            log.warn(f"Failed to set {target_attr} on {cc_node}: {exc}", source=_SOURCE)


def create_target_material(node_type, base_name):
    node = cmds.shadingNode(node_type, asShader=True, name=base_name)
    get_logger().debug(f"Created material node {node} ({node_type})", source=_SOURCE)
    return node


def smart_connect(src_plug, dst_plug, logger=None):
    log = _log_or_default(logger)
    if not src_plug or not dst_plug:
        log.warn("smart_connect called with empty plug", source=_SOURCE, src=src_plug, dst=dst_plug)
        return False

    try:
        if cmds.isConnected(src_plug, dst_plug):
            log.debug(f"Already connected: {src_plug} -> {dst_plug}", source=_SOURCE)
            return True
    except Exception as exc:
        log.warn(f"Failed to check connection {src_plug} -> {dst_plug}: {exc}", source=_SOURCE)

    errors = []
    try:
        cmds.connectAttr(src_plug, dst_plug, force=True)
        log.debug(f"Connected: {src_plug} -> {dst_plug}", source=_SOURCE)
        return True
    except Exception as exc:
        errors.append(f"{src_plug}: {exc}")
        log.debug(f"Direct connect failed for {src_plug} -> {dst_plug}: {exc}; trying outColor fallback", source=_SOURCE)

    src_node = src_plug.split(".")[0]
    try:
        cmds.connectAttr(f"{src_node}.outColor", dst_plug, force=True)
        log.info(f"Connected via outColor fallback: {src_node}.outColor -> {dst_plug}", source=_SOURCE)
        return True
    except Exception as exc:
        errors.append(f"{src_node}.outColor: {exc}")
        log.debug(f"outColor fallback failed for {src_node} -> {dst_plug}: {exc}; trying outAlpha fallback", source=_SOURCE)

    try:
        cmds.connectAttr(f"{src_node}.outAlpha", dst_plug, force=True)
        log.info(f"Connected via outAlpha fallback: {src_node}.outAlpha -> {dst_plug}", source=_SOURCE)
        return True
    except Exception as exc:
        errors.append(f"{src_node}.outAlpha: {exc}")

    log.warn(f"smart_connect failed: {src_plug} -> {dst_plug}: {' | '.join(errors)}", source=_SOURCE)
    return False


def get_shading_engine(material, logger=None):
    log = _log_or_default(logger)
    try:
        sgs = cmds.listConnections(f"{material}.outColor", type="shadingEngine") or []
        if sgs:
            log.debug(f"Shading engine for {material}: {sgs[0]}", source=_SOURCE)
            return sgs[0]
        log.debug(f"No shading engine connected to {material}.outColor", source=_SOURCE)
    except Exception as exc:
        log.warn(f"Failed to query shading engine for {material}: {exc}", source=_SOURCE)
    return None


def get_displacement_node_from_sg(shading_engine, logger=None):
    log = _log_or_default(logger)
    try:
        conns = cmds.listConnections(f"{shading_engine}.displacementShader", source=True, destination=False) or []
        if conns:
            log.debug(f"Displacement node for {shading_engine}: {conns[0]}", source=_SOURCE)
            return conns[0]
        log.debug(f"No displacementShader connected to {shading_engine}", source=_SOURCE)
    except Exception as exc:
        log.warn(f"Failed to query displacementShader on {shading_engine}: {exc}", source=_SOURCE)
    return None
