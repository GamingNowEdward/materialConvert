import maya.cmds as cmds

from dataclasses import dataclass, field

from core.logger import get_logger

_SOURCE = "prerequisites"


@dataclass
class PrerequisiteOutcome:
    """Result of applying one or more prerequisite attributes.

    ``ok`` is False when at least one attribute could not be set (for example a
    renderer mode switch that must be enabled before a mapped attribute means
    anything).  ``failures`` carries the concrete items so callers can report
    *which* prerequisite failed instead of a bare "prerequisites failed".
    """

    ok: bool = True
    failures: list = field(default_factory=list)

    def __bool__(self):
        return bool(self.ok)


def _log_or_default(logger):
    return logger or get_logger()


def apply_prerequisites(material, config, logger=None):
    log = _log_or_default(logger)
    prereqs = config.get_prerequisites()
    if not prereqs:
        log.debug(f"No material prerequisites for {material}", source=_SOURCE, nodes=(material,))
        return PrerequisiteOutcome()
    log.debug(f"Applying {len(prereqs)} material prerequisite(s) to {material}", source=_SOURCE, nodes=(material,))
    return _apply_prereq_dict(material, prereqs, log)


def apply_attr_prerequisites(material, config, common_attr, logger=None):
    log = _log_or_default(logger)
    prereq = config.get_attr_prerequisites(common_attr)
    if not prereq:
        return PrerequisiteOutcome()
    log.debug(f"Applying attribute prerequisite for {common_attr} on {material}", source=_SOURCE, nodes=(material,))
    ok, failure = _apply_single_prereq(material, prereq, log)
    outcome = PrerequisiteOutcome(ok=ok)
    if failure:
        outcome.failures.append(failure)
    return outcome


def apply_prerequisite_dict(material, prereq_dict, logger=None):
    """Apply a prerequisite mapping that comes straight from a config.

    ``prereq_dict`` may be a single ``{"attribute": ..., "value": ...}`` entry or
    a mapping of named entries.  Used by the Builder for its per-channel
    prerequisites, so no renderer attribute name is hardcoded in Python.
    """
    log = _log_or_default(logger)
    if not prereq_dict:
        return PrerequisiteOutcome()
    if "attribute" in prereq_dict:
        ok, failure = _apply_single_prereq(material, prereq_dict, log)
        outcome = PrerequisiteOutcome(ok=ok)
        if failure:
            outcome.failures.append(failure)
        return outcome
    return _apply_prereq_dict(material, prereq_dict, log)


def _apply_single_prereq(material, prereq_info, log):
    """Set one prerequisite attribute; return ``(ok, failure_description)``."""
    if not isinstance(prereq_info, dict):
        log.warn(f"Invalid prerequisite definition for {material}: {prereq_info!r}", source=_SOURCE, nodes=(material,))
        return False, f"{material}: invalid prerequisite definition {prereq_info!r}"

    prereq_attr = prereq_info.get("attribute", "")
    prereq_value = prereq_info.get("value", None)
    if not prereq_attr or prereq_value is None:
        log.debug(f"Empty prerequisite on {material}: attribute={prereq_attr!r} value={prereq_value!r}", source=_SOURCE, nodes=(material,))
        return True, ""

    try:
        if isinstance(prereq_value, (list, tuple)) and len(prereq_value):
            cmds.setAttr(f"{material}.{prereq_attr}", *prereq_value)
        else:
            cmds.setAttr(f"{material}.{prereq_attr}", prereq_value)
        log.debug(f"Set prerequisite {material}.{prereq_attr} = {prereq_value!r}", source=_SOURCE, nodes=(material,))
        return True, ""
    except Exception as exc:
        log.warn(f"Failed to set prerequisite {material}.{prereq_attr} = {prereq_value!r}: {exc}", source=_SOURCE, nodes=(material,))
        return False, f"{material}.{prereq_attr}={prereq_value!r} ({exc})"


def _apply_prereq_dict(material, prereq_dict, log):
    outcome = PrerequisiteOutcome()
    if not prereq_dict:
        return outcome
    for _attr_name, prereq_info in prereq_dict.items():
        ok, failure = _apply_single_prereq(material, prereq_info, log)
        if not ok:
            outcome.ok = False
            if failure:
                outcome.failures.append(failure)
    return outcome
