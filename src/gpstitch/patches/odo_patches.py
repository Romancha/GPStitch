"""Patch to make gopro_overlay's calculate_odo() start from an initial offset."""

import logging

from gopro_overlay.units import units

logger = logging.getLogger(__name__)


def patch_calculate_odo(initial_offset_meters: float) -> None:
    """Patch timeseries_process.calculate_odo to start from an initial offset.

    After this patch, calculate_odo() returns a processor that begins
    accumulating distance from initial_offset_meters instead of 0.

    Args:
        initial_offset_meters: Starting odometer value in meters.
    """
    from gopro_overlay import timeseries_process

    if getattr(timeseries_process, "_ts_odo_patched", False):
        logger.debug("calculate_odo already patched, skipping")
        return

    def patched_calculate_odo():
        total = [units.Quantity(initial_offset_meters, units.m)]

        def accept(e):
            if e.dist is not None:
                total[0] += e.dist
            return {"codo": total[0]}

        return accept

    timeseries_process.calculate_odo = patched_calculate_odo
    timeseries_process._ts_odo_patched = True
    logger.info("Patched calculate_odo with initial offset: %.1f meters", initial_offset_meters)
