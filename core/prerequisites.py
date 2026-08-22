import maya.cmds as cmds

from core.logger import get_logger

_SOURCE = "prerequisites"


def _log_or_default(logger):
    return logger or get_logger()


def apply_prerequisites(material, config, logger=None):
    log = _log_or_default(logger)
    prereqs = config.get_prerequisites()
    if not prereqs:
        log.debug(f"No material prerequisites for {material}", source=_SOURCE)
        return
    log.debug(f"Applying {len(prereqs)} material prerequisite(s) to {material}", source=_SOURCE)
    _apply_prereq_dict(material, prereqs, log)


def apply_attr_prerequisites(material, config, common_attr, logger=None):
    log = _log_or_default(logger)
    prereq = config.get_attr_prerequisites(common_attr)
    if not prereq:
        return
    log.debug(f"Applying attribute prerequisite for {common_attr} on {material}", source=_SOURCE)
    _apply_single_prereq(material, prereq, log)


def _apply_single_prereq(material, prereq_info, log):
    if not isinstance(prereq_info, dict):
        log.warn(f"Invalid prerequisite definition for {material}: {prereq_info!r}", source=_SOURCE)
        return

    prereq_attr = prereq_info.get("attribute", "")
    prereq_value = prereq_info.get("value", None)
    if not prereq_attr or prereq_value is None:
        log.debug(f"Empty prerequisite on {material}: attribute={prereq_attr!r} value={prereq_value!r}", source=_SOURCE)
        return

    try:
        if isinstance(prereq_value, (list, tuple)) and len(prereq_value):
            cmds.setAttr(f"{material}.{prereq_attr}", *prereq_value)
        else:
            cmds.setAttr(f"{material}.{prereq_attr}", prereq_value)
        log.debug(f"Set prerequisite {material}.{prereq_attr} = {prereq_value!r}", source=_SOURCE)
    except Exception as exc:
        log.warn(f"Failed to set prerequisite {material}.{prereq_attr} = {prereq_value!r}: {exc}", source=_SOURCE)


def _apply_prereq_dict(material, prereq_dict, log):
    if not prereq_dict:
        return
    for attr_name, prereq_info in prereq_dict.items():
        _apply_single_prereq(material, prereq_info, log)
