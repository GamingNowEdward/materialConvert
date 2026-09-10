from core.logger import get_logger


def populate_material_targets(combo, config, logger=None, source="", label="material"):
    """Fill a material-target combo with ``(display name, node_type)`` entries.

    Shared by the Converter / Builder / Batch Builder tabs so the target list
    is always derived from the same ``ConfigLoader`` source of truth.
    """
    log = logger or get_logger()
    combo.clear()
    all_configs = config.get_all_material_configs()
    for node_type in sorted(all_configs.keys()):
        display_name = config.get_display_name(node_type)
        combo.addItem(display_name, node_type)
    log.debug(f"Populated {combo.count()} {label} target(s)", source=source)
    return combo.count()
