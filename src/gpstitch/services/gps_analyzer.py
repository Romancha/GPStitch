"""GPS quality analysis service."""

import logging
import statistics
from pathlib import Path

from gpstitch.config import settings
from gpstitch.constants import (
    DOP_THRESHOLD_EXCELLENT,
    DOP_THRESHOLD_GOOD,
    DOP_THRESHOLD_MODERATE,
)
from gpstitch.models.schemas import GPSQualityReport, GPSQualityScore

# Apply runtime patches if enabled
if settings.enable_gopro_patches:
    from gpstitch.patches import apply_patches

    apply_patches()

logger = logging.getLogger(__name__)

# DOP value indicating no GPS signal (GoPro uses 99.99 when no lock)
NO_SIGNAL_DOP = 99.0


def analyze_gps_quality(file_path: Path) -> GPSQualityReport | None:
    """Analyze GPS quality from a video file.

    For GoPro videos with GPMF data, performs full DOP-based quality analysis.
    For DJI Action videos with embedded DJI meta GPS, returns None since DJI meta
    has no DOP data and quality analysis would be meaningless (same as SRT).

    Args:
        file_path: Path to the video file

    Returns:
        GPSQualityReport with quality analysis, or None if analysis fails/not applicable
    """
    from gpstitch.services.dji_meta_parser import detect_dji_meta_stream

    # DJI Action videos with embedded GPS have no DOP data —
    # quality analysis is meaningless, same as SRT files
    try:
        if detect_dji_meta_stream(file_path) is not None:
            logger.debug(f"Skipping GPS quality analysis for DJI Action video: {file_path}")
            return None
    except Exception:
        pass

    from gopro_overlay.ffmpeg import FFMPEG
    from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro
    from gopro_overlay.gpmd_filters import standard as gps_filter_standard
    from gopro_overlay.loading import GoproLoader
    from gopro_overlay.units import units

    try:
        ffmpeg = FFMPEG()
        ffmpeg_gopro = FFMPEGGoPro(ffmpeg)

        # Use very loose filter to get all data for analysis
        loader = GoproLoader(
            ffmpeg_gopro=ffmpeg_gopro,
            units=units,
            gps_lock_filter=gps_filter_standard(dop_max=100, speed_max=units.Quantity(500, units.kph)),
        )

        gopro = loader.load(file_path)
        framemeta = gopro.framemeta

        # Collect GPS data
        dop_values: list[float] = []
        locked_points = 0
        total_points = 0

        for entry in framemeta.items():
            total_points += 1

            # Extract DOP value
            if entry.dop is not None:
                dop_val = entry.dop.magnitude if hasattr(entry.dop, "magnitude") else float(entry.dop)
                dop_values.append(dop_val)

            # Check GPS lock status (2=2D lock, 3=3D lock)
            if entry.gpslock is not None and entry.gpslock in [2, 3]:
                locked_points += 1

        return _build_report(total_points, locked_points, dop_values)

    except OSError as e:
        # Video doesn't have GPS data stream
        logger.warning(f"No GPS data in video: {e}")
        return GPSQualityReport(
            total_points=0,
            locked_points=0,
            lock_rate=0.0,
            quality_score="no_signal",
            usable_percentage=0.0,
            warnings=["Video file does not contain GPS metadata"],
        )
    except Exception as e:
        logger.error(f"Error analyzing GPS quality: {e}", exc_info=True)
        return None


def analyze_external_gps_quality(file_path: Path) -> GPSQualityReport | None:
    """Analyze GPS quality from an external telemetry file (GPX, FIT, or SRT).

    External files don't have DOP data like GoPro GPMF, so quality is assessed
    based on point count, coordinate validity, and available metadata.

    Args:
        file_path: Path to the GPX, FIT, or SRT file

    Returns:
        GPSQualityReport with quality analysis, or None if analysis fails
    """
    try:
        suffix = file_path.suffix.lower()

        if suffix == ".srt":
            # SRT files have no DOP, satellite count, or fix type data —
            # quality analysis would be meaningless
            return None

        from gopro_overlay.loading import load_external
        from gopro_overlay.units import units

        timeseries = load_external(file_path, units)
        return _analyze_timeseries_quality(timeseries)

    except Exception as e:
        logger.error(f"Error analyzing external GPS quality from {file_path}: {e}")
        return None


def _analyze_timeseries_quality(timeseries) -> GPSQualityReport:
    """Analyze GPS quality from a gopro_overlay Timeseries (GPX/FIT)."""
    entries = timeseries.items()
    total_points = len(entries)

    if total_points == 0:
        return GPSQualityReport(
            total_points=0,
            locked_points=0,
            lock_rate=0.0,
            quality_score="no_signal",
            usable_percentage=0.0,
            warnings=["No GPS data points found"],
        )

    # Collect DOP values if available
    dop_values: list[float] = []
    locked_points = 0

    for entry in entries:
        if entry.point is not None:
            locked_points += 1

        if entry.dop is not None:
            dop_val = entry.dop.magnitude if hasattr(entry.dop, "magnitude") else float(entry.dop)
            dop_values.append(dop_val)

    if dop_values:
        # Have DOP data — use full analysis
        return _build_report(total_points, locked_points, dop_values)

    # No DOP data — assess based on point count and validity
    lock_rate = (locked_points / total_points) * 100 if total_points > 0 else 0.0

    if lock_rate == 0:
        quality_score: GPSQualityScore = "no_signal"
    elif lock_rate >= 90:
        quality_score = "good"
    else:
        quality_score = "ok"

    warnings: list[str] = []
    if quality_score == "no_signal":
        warnings.append("No valid GPS coordinates found in file")
    elif lock_rate < 90:
        warnings.append(f"Only {lock_rate:.0f}% of points have valid coordinates")

    return GPSQualityReport(
        total_points=total_points,
        locked_points=locked_points,
        lock_rate=round(lock_rate, 1),
        quality_score=quality_score,
        usable_percentage=round(lock_rate, 1),
        warnings=warnings,
    )


def _build_report(total_points: int, locked_points: int, dop_values: list[float]) -> GPSQualityReport:
    """Build GPS quality report from collected data."""

    # Handle empty data
    if total_points == 0:
        return GPSQualityReport(
            total_points=0,
            locked_points=0,
            lock_rate=0.0,
            quality_score="no_signal",
            usable_percentage=0.0,
            warnings=["No GPS data points found"],
        )

    lock_rate = (locked_points / total_points) * 100

    # Calculate DOP statistics
    dop_min = None
    dop_max = None
    dop_mean = None
    dop_median = None

    if dop_values:
        dop_min = min(dop_values)
        dop_max = max(dop_values)
        dop_mean = statistics.mean(dop_values)
        dop_median = statistics.median(dop_values)

    # Count points by quality bucket
    excellent_count = sum(1 for d in dop_values if d < DOP_THRESHOLD_EXCELLENT)
    good_count = sum(1 for d in dop_values if DOP_THRESHOLD_EXCELLENT <= d < DOP_THRESHOLD_GOOD)
    moderate_count = sum(1 for d in dop_values if DOP_THRESHOLD_GOOD <= d < DOP_THRESHOLD_MODERATE)
    poor_count = sum(1 for d in dop_values if d >= DOP_THRESHOLD_MODERATE)

    # Calculate usable percentage (DOP < 10)
    usable_count = excellent_count + good_count + moderate_count
    usable_percentage = (usable_count / len(dop_values) * 100) if dop_values else 0.0

    # Determine overall quality score
    quality_score = _determine_quality_score(lock_rate, dop_mean, usable_percentage, dop_values)

    # Generate warnings
    warnings = _generate_warnings(quality_score, lock_rate, dop_mean, usable_percentage, total_points)

    return GPSQualityReport(
        total_points=total_points,
        locked_points=locked_points,
        lock_rate=round(lock_rate, 1),
        dop_min=round(dop_min, 2) if dop_min is not None else None,
        dop_max=round(dop_max, 2) if dop_max is not None else None,
        dop_mean=round(dop_mean, 2) if dop_mean is not None else None,
        dop_median=round(dop_median, 2) if dop_median is not None else None,
        excellent_count=excellent_count,
        good_count=good_count,
        moderate_count=moderate_count,
        poor_count=poor_count,
        quality_score=quality_score,
        usable_percentage=round(usable_percentage, 1),
        warnings=warnings,
    )


def _determine_quality_score(
    lock_rate: float,
    dop_mean: float | None,
    usable_percentage: float,
    dop_values: list[float],
) -> GPSQualityScore:
    """Determine overall GPS quality score."""

    # No signal if no lock or all DOP values are invalid
    if lock_rate == 0:
        return "no_signal"

    if dop_values and all(d >= NO_SIGNAL_DOP for d in dop_values):
        return "no_signal"

    if dop_mean is None:
        return "no_signal"

    # Score based on mean DOP
    if dop_mean < DOP_THRESHOLD_EXCELLENT:
        return "excellent"
    elif dop_mean < DOP_THRESHOLD_GOOD:
        return "good"
    elif dop_mean < DOP_THRESHOLD_MODERATE:
        return "ok"
    else:
        return "poor"


def _generate_warnings(
    quality_score: GPSQualityScore,
    lock_rate: float,
    dop_mean: float | None,
    usable_percentage: float,
    total_points: int,
) -> list[str]:
    """Generate user-facing warnings based on GPS quality."""

    warnings = []

    if quality_score == "no_signal":
        warnings.append("GPS signal was not acquired during recording")
        warnings.append("Consider using an external GPX file for telemetry overlay")
        return warnings

    if lock_rate < 50:
        warnings.append(f"Only {lock_rate:.0f}% of recording has GPS lock")

    if quality_score == "poor":
        warnings.append(f"Poor GPS quality (average DOP: {dop_mean:.1f})")
        warnings.append("Overlay may show incorrect speed and position data")

    if usable_percentage < 50:
        warnings.append(f"Only {usable_percentage:.0f}% of GPS points are usable")

    if quality_score == "ok":
        warnings.append("GPS signal quality is OK - some data may be slightly imprecise")

    return warnings
