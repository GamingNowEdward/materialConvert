import pymel.core as pm


def apply_prerequisites(material, config):
    prereqs = config.get_prerequisites()
    _apply_prereq_dict(material, prereqs)


def apply_attr_prerequisites(material, config, common_attr):
    prereq = config.get_attr_prerequisites(common_attr)
    if prereq:
        _apply_single_prereq(material, prereq)


def _apply_single_prereq(material, prereq_info):
    if isinstance(prereq_info, dict):
        prereq_attr = prereq_info.get("attribute", "")
        prereq_value = prereq_info.get("value", None)
        if prereq_attr and prereq_value is not None:
            try:
                material.attr(prereq_attr).set(prereq_value)
            except Exception:
                pm.warning(f"prerequisites: failed to set {prereq_attr}={prereq_value} on {material.name()}")


def _apply_prereq_dict(material, prereq_dict):
    if not prereq_dict:
        return
    for attr_name, prereq_info in prereq_dict.items():
        _apply_single_prereq(material, prereq_info)
