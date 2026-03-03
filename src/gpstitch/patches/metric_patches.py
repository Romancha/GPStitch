"""Patch to extend gopro_overlay with custom camera metrics from DJI SRT."""

import logging

logger = logging.getLogger(__name__)


def patch_metric_accessor() -> None:
    """Extend metric_accessor_from() to support DJI camera metrics."""
    from gopro_overlay import layout_xml

    if getattr(layout_xml, "_ts_metric_patched", False):
        logger.debug("metric_accessor_from already patched, skipping")
        return

    _original = layout_xml.metric_accessor_from

    _custom_accessors = {
        "iso": lambda e: e.iso,
        "shutter": lambda e: e.shutter,
        "fnum": lambda e: e.fnum,
        "ev": lambda e: e.ev,
        "focal_len": lambda e: e.focal_len,
        "ct": lambda e: e.ct,
    }

    def extended_metric_accessor_from(name: str):
        try:
            return _original(name)
        except OSError:
            if name in _custom_accessors:
                return _custom_accessors[name]
            raise

    layout_xml.metric_accessor_from = extended_metric_accessor_from
    layout_xml._ts_metric_patched = True
    logger.debug("Patched metric_accessor_from with DJI camera metrics")
