from core.logger import get_logger


def set_enabled(widgets, enabled):
    """Enable/disable a group of widgets, ignoring ones already destroyed.

    Batch operations call this around their work so a second click cannot enter
    the same run again while ``processEvents()`` keeps the UI responsive.
    """
    for widget in widgets:
        try:
            widget.setEnabled(bool(enabled))
        except RuntimeError:
            # Widget was deleted (window closed mid-run): nothing to restore.
            continue


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
