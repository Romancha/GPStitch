"""Patch gopro_overlay to load SRT data directly instead of intermediate GPX.

When rendering video with DJI SRT telemetry, the SRT is converted to GPX for
CLI compatibility. GPX only carries GPS data — camera metrics (iso, fnum, ev,
ct, shutter, focal_len) are lost. This patch intercepts load_external() to
load the original SRT file with all camera metrics preserved.

Applied conditionally by the wrapper script when --ts-srt-source is present.
"""

import logging
from dataclasses import replace as dc_replace
from datetime import UTC
from pathlib import Path

logger = logging.getLogger(__name__)


def patch_gpx_load_for_srt(srt_path: str, video_path: str | None = None) -> None:
    """Patch gopro_overlay.loading.load_external to load SRT instead of GPX.

    Args:
        srt_path: Path to the original .srt file.
        video_path: Path to the video file (for timezone offset estimation).
    """
    import gopro_overlay.loading as loading_module

    if getattr(loading_module, "_ts_srt_patched", False):
        logger.debug("load_external already patched for SRT, skipping")
        return

    from gpstitch.constants import DEFAULT_GPS_TARGET_HZ
    from gpstitch.services.srt_parser import (
        calc_sample_rate,
        estimate_srt_fps,
        estimate_tz_offset,
        parse_srt,
        srt_to_timeseries,
    )

    srt_filepath = Path(srt_path)
    video_filepath = Path(video_path) if video_path else None

    points = parse_srt(srt_filepath)
    if not points:
        raise ValueError(f"No valid GPS data found in SRT file: {srt_filepath}")

    source_hz = estimate_srt_fps(srt_filepath, points=points)
    sample_rate = calc_sample_rate(source_hz, DEFAULT_GPS_TARGET_HZ)

    # Apply timezone offset and make timestamps UTC-aware.
    # gopro-dashboard.py compares timeseries dates with video file dates (timezone-aware UTC).
    # SRT timestamps are naive local time — we must convert to UTC-aware to avoid
    # "can't compare offset-naive and offset-aware datetimes" TypeError.
    if video_filepath and video_filepath.exists():
        tz_offset, mtime_role = estimate_tz_offset(srt_filepath, video_filepath, points=points)
        if tz_offset is not None:
            points = [dc_replace(p, dt=(p.dt - tz_offset).replace(tzinfo=UTC)) for p in points]
            logger.info(f"SRT patch: adjusted timestamps by {tz_offset} (mtime_role={mtime_role})")

    logger.info(f"SRT patch: {srt_filepath.name}, {len(points)} points, {source_hz:.1f}fps, sample_rate={sample_rate}")

    _original = loading_module.load_external

    def patched_load_external(filepath: Path, units):
        """Load SRT data instead of GPX, preserving camera metrics."""
        logger.info(f"SRT patch: intercepting load_external({filepath.name}) -> {srt_filepath.name}")
        return srt_to_timeseries(points, units, sample_rate)

    loading_module.load_external = patched_load_external
    loading_module._ts_srt_patched = True
    logger.info("Patched gopro_overlay.loading.load_external for SRT")
