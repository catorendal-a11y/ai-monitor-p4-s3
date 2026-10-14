"""Local release gate. Neither USB messages nor saved preferences can replace validation."""
# Change only after the documented physical enrollment/hold/deny/unplug/provider gates pass.
PHYSICAL_PERMISSION_RELEASE_READY = False


def release_ready():
    return PHYSICAL_PERMISSION_RELEASE_READY is True


def selected(config):
    return (config.get('usb_permissions') is True and config.get('board') == 'guition-p4'
            and 'claude' in config.get('providers', []))
