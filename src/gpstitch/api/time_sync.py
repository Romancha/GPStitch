"""Time sync analysis API endpoint."""

import asyncio
import datetime
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gpstitch.models.schemas import FileRole
from gpstitch.services.file_manager import file_manager
from gpstitch.services.renderer import _align_timezone, _extract_creation_time, _validate_creation_time

logger = logging.getLogger(__name__)

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=2)


class TimeSyncAnalyzeRequest(BaseModel):
    session_id: str
    time_offset_seconds: int = 0


class OverlapInfo(BaseModel):
    points: int
    distance_m: float
    avg_speed_kph: float


class TimeSyncAnalyzeResponse(BaseModel):
    video_start: str = Field(description="ISO UTC datetime string")
    video_duration_sec: float
    source: str = Field(description="'media-created' or 'file-created'")
    overlap: OverlapInfo | None = None


def _get_video_duration(file_path: Path) -> float:
    """Get video duration in seconds via ffprobe."""
    from gopro_overlay.ffmpeg import FFMPEG
    from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro

    ffmpeg = FFMPEG()
    ffmpeg_gopro = FFMPEGGoPro(ffmpeg)
    recording = ffmpeg_gopro.find_recording(file_path)
    return recording.video.duration.millis() / 1000.0


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two GPS points in meters using Haversine formula."""
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def _calculate_overlap(
    video_start: datetime.datetime,
    video_duration_sec: float,
    gpx_path: Path,
) -> OverlapInfo | None:
    """Calculate overlap between video time range and GPX/FIT/SRT track."""
    from gopro_overlay.units import units

    try:
        if gpx_path.suffix.lower() == ".srt":
            from gpstitch.services.srt_parser import (
                calc_sample_rate,
                estimate_srt_fps,
                load_srt_timeseries,
                parse_srt,
            )

            points = parse_srt(gpx_path)
            source_hz = estimate_srt_fps(gpx_path, points=points)
            sample_rate = calc_sample_rate(source_hz, 1)
            timeseries = load_srt_timeseries(gpx_path, units, sample_rate, points=points)
        else:
            from gopro_overlay.loading import load_external

            timeseries = load_external(gpx_path, units)
        entries = timeseries.items()
        if not entries:
            return None

        # Align timezone awareness to prevent TypeError on comparison
        video_start = _align_timezone(video_start, timeseries)
        video_end = video_start + datetime.timedelta(seconds=video_duration_sec)

        # Filter entries within video time range
        overlap_entries = [e for e in entries if e.dt is not None and video_start <= e.dt <= video_end]

        if not overlap_entries:
            return None

        # Calculate total distance and speed
        total_distance_m = 0.0
        for i in range(1, len(overlap_entries)):
            prev = overlap_entries[i - 1]
            curr = overlap_entries[i]
            if prev.point is not None and curr.point is not None:
                total_distance_m += _haversine_distance(
                    prev.point.lat,
                    prev.point.lon,
                    curr.point.lat,
                    curr.point.lon,
                )

        # Calculate average speed
        if len(overlap_entries) >= 2:
            time_span = (overlap_entries[-1].dt - overlap_entries[0].dt).total_seconds()
            avg_speed_kph = (total_distance_m / 1000) / (time_span / 3600) if time_span > 0 else 0.0
        else:
            avg_speed_kph = 0.0

        return OverlapInfo(
            points=len(overlap_entries),
            distance_m=round(total_distance_m, 1),
            avg_speed_kph=round(avg_speed_kph, 1),
        )

    except (Exception, SystemExit) as e:
        logger.warning(f"Failed to calculate overlap: {e}")
        return None


@router.post("/time-sync/analyze", response_model=TimeSyncAnalyzeResponse)
async def analyze_time_sync(request: TimeSyncAnalyzeRequest) -> TimeSyncAnalyzeResponse:
    """Analyze time alignment between video and GPX data.

    Returns video start time (from metadata or file stat), duration,
    and overlap information with GPX track if available.
    """
    # Get primary video file
    primary = file_manager.get_file_by_role(request.session_id, FileRole.PRIMARY)
    if not primary:
        raise HTTPException(status_code=404, detail="No primary video file in session")

    if primary.file_type != "video":
        raise HTTPException(
            status_code=400,
            detail="Primary file must be a video for time sync analysis",
        )

    video_path = Path(primary.file_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    # Get optional secondary GPX file path
    gpx_path = None
    secondary = file_manager.get_file_by_role(request.session_id, FileRole.SECONDARY)
    if secondary:
        p = Path(secondary.file_path)
        if p.exists():
            gpx_path = p

    # Run blocking I/O (ffprobe, GPX parsing) in thread pool
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            _executor,
            _analyze_sync,
            video_path,
            request.time_offset_seconds,
            gpx_path,
        )
    except Exception as e:
        logger.exception("Time sync analysis failed")
        raise HTTPException(status_code=500, detail="Analysis failed") from e

    return result


def _analyze_sync(
    video_path: Path,
    time_offset_seconds: int,
    gpx_path: Path | None,
) -> TimeSyncAnalyzeResponse:
    """Run blocking time sync analysis (ffprobe + GPX parsing)."""
    # Get video duration (needed for creation_time validation)
    try:
        video_duration_sec = _get_video_duration(video_path)
    except Exception as e:
        logger.warning("Failed to get video duration for creation_time validation: %s", e)
        video_duration_sec = 0.0

    # Extract creation time
    creation_time = _extract_creation_time(video_path)
    if creation_time is not None:
        # Cross-validate against GPS data to detect cameras with local-time creation_time
        creation_time = _validate_creation_time(video_path, creation_time, video_duration_sec, gpx_path)
        video_start = creation_time
        source = "media-created"
    else:
        from gopro_overlay.ffmpeg_gopro import filestat

        fstat = filestat(video_path)
        video_start = fstat.ctime
        source = "file-created"

    # Apply offset
    if time_offset_seconds:
        video_start = video_start + datetime.timedelta(seconds=time_offset_seconds)

    # Calculate overlap with GPX if available
    overlap = None
    if gpx_path is not None:
        overlap = _calculate_overlap(video_start, video_duration_sec, gpx_path)

    return TimeSyncAnalyzeResponse(
        video_start=video_start.isoformat(),
        video_duration_sec=round(video_duration_sec, 1),
        source=source,
        overlap=overlap,
    )
