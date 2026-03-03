"""DJI SRT telemetry file parser.

Parses DJI drone subtitle files (.srt) that contain per-frame telemetry data
including GPS coordinates, altitude, and camera settings.

DJI SRT format example:
    1
    00:00:00,000 --> 00:00:00,033
    <font size="28">FrameCnt: 1, DiffTime: 33ms
    2024-08-07 12:34:24.380
    [iso: 100] [shutter: 1/3200.0] [fnum: 1.7] [ev: 0] [color_md: default]
    [focal_len: 24.00] [latitude: 69.189116] [longitude: 35.259334]
    [rel_alt: 1.100 abs_alt: -2.927] [ct: 5310] </font>
"""

import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement

from gopro_overlay.gpmf import GPSFix
from gopro_overlay.point import Point
from gopro_overlay.timeseries import Entry, Timeseries

logger = logging.getLogger(__name__)

# Regex patterns for DJI SRT parsing
_RE_DATETIME = re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)")
_RE_LATITUDE = re.compile(r"\[latitude:\s*([-\d.]+)\]")
_RE_LONGITUDE = re.compile(r"\[longitude:\s*([-\d.]+)\]")
_RE_REL_ALT = re.compile(r"\[rel_alt:\s*([-\d.]+)")
_RE_ABS_ALT = re.compile(r"abs_alt:\s*([-\d.]+)\]")

# Camera metrics patterns
_RE_ISO = re.compile(r"\[iso:\s*(\d+)\]")
_RE_SHUTTER = re.compile(r"\[shutter:\s*([\d/.]+)\]")
_RE_FNUM = re.compile(r"\[fnum:\s*([\d.]+)\]")
_RE_EV = re.compile(r"\[ev:\s*([-\d.]+)\]")
_RE_FOCAL_LEN = re.compile(r"\[focal_len:\s*([\d.]+)\]")
_RE_CT = re.compile(r"\[ct:\s*(\d+)\]")


@dataclass
class SrtPoint:
    """A single telemetry point from a DJI SRT file.

    Note: dt is naive datetime in the drone's local time (no timezone info).
    DJI drones write SRT timestamps in local time without timezone.
    Use estimate_tz_offset() to determine the UTC offset when needed.
    """

    dt: datetime
    lat: float
    lon: float
    rel_alt: float
    abs_alt: float
    # Camera metrics (optional — not all SRT files have them)
    iso: int | None = None
    shutter: float | None = None  # parsed from fraction "1/3200.0" → 0.0003125
    fnum: float | None = None
    ev: float | None = None
    focal_len: float | None = None
    ct: int | None = None  # color temperature


def _parse_shutter(value: str) -> float:
    """Parse shutter speed string to float seconds. '1/3200.0' → 0.0003125."""
    if "/" in value:
        num, den = value.split("/", 1)
        return float(num) / float(den)
    return float(value)


def parse_srt(filepath: Path) -> list[SrtPoint]:
    """Parse a DJI SRT file and return all telemetry points.

    Args:
        filepath: Path to the .srt file

    Returns:
        List of SrtPoint with GPS data and timestamps
    """
    text = filepath.read_text(encoding="utf-8", errors="replace")
    points = []

    # Split into subtitle blocks (separated by blank lines)
    blocks = re.split(r"\n\s*\n", text)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Extract datetime
        dt_match = _RE_DATETIME.search(block)
        if not dt_match:
            continue

        # Extract coordinates
        lat_match = _RE_LATITUDE.search(block)
        lon_match = _RE_LONGITUDE.search(block)
        if not lat_match or not lon_match:
            continue

        try:
            dt = datetime.strptime(dt_match.group(1), "%Y-%m-%d %H:%M:%S.%f")
            lat = float(lat_match.group(1))
            lon = float(lon_match.group(1))
        except (ValueError, IndexError):
            continue

        # Skip invalid coordinates
        if lat == 0.0 and lon == 0.0:
            continue

        # Extract altitude (optional)
        rel_alt = 0.0
        abs_alt = 0.0
        rel_alt_match = _RE_REL_ALT.search(block)
        abs_alt_match = _RE_ABS_ALT.search(block)
        if rel_alt_match:
            rel_alt = float(rel_alt_match.group(1))
        if abs_alt_match:
            abs_alt = float(abs_alt_match.group(1))

        # Extract camera metrics (optional)
        iso_match = _RE_ISO.search(block)
        shutter_match = _RE_SHUTTER.search(block)
        fnum_match = _RE_FNUM.search(block)
        ev_match = _RE_EV.search(block)
        focal_len_match = _RE_FOCAL_LEN.search(block)
        ct_match = _RE_CT.search(block)

        points.append(
            SrtPoint(
                dt=dt,
                lat=lat,
                lon=lon,
                rel_alt=rel_alt,
                abs_alt=abs_alt,
                iso=int(iso_match.group(1)) if iso_match else None,
                shutter=_parse_shutter(shutter_match.group(1)) if shutter_match else None,
                fnum=float(fnum_match.group(1)) if fnum_match else None,
                ev=float(ev_match.group(1)) if ev_match else None,
                focal_len=float(focal_len_match.group(1)) if focal_len_match else None,
                ct=int(ct_match.group(1)) if ct_match else None,
            )
        )

    return points


def srt_to_timeseries(points: list[SrtPoint], units, sample_rate: int = 1) -> Timeseries:
    """Convert parsed SRT points to a gopro_overlay Timeseries.

    Args:
        points: Parsed SRT telemetry points
        units: gopro_overlay units module
        sample_rate: Take every N-th point (1 = all, 10 = every 10th, 30 = ~1/sec at 30fps)

    Returns:
        Timeseries compatible with gopro_overlay rendering pipeline
    """
    timeseries = Timeseries()

    sampled = points[::sample_rate] if sample_rate > 1 else points

    entries = [
        Entry(
            point.dt,
            point=Point(point.lat, point.lon),
            alt=units.Quantity(point.rel_alt, units.m),
            gpsfix=GPSFix.LOCK_3D.value,
            gpslock=units.Quantity(GPSFix.LOCK_3D.value),
            packet=units.Quantity(index),
            packet_index=units.Quantity(0),
            # Camera metrics (None values are filtered out by Entry.__init__)
            iso=units.Quantity(point.iso) if point.iso is not None else None,
            shutter=units.Quantity(point.shutter) if point.shutter is not None else None,
            fnum=units.Quantity(point.fnum) if point.fnum is not None else None,
            ev=units.Quantity(point.ev) if point.ev is not None else None,
            focal_len=units.Quantity(point.focal_len) if point.focal_len is not None else None,
            ct=units.Quantity(point.ct) if point.ct is not None else None,
        )
        for index, point in enumerate(sampled)
    ]

    timeseries.add(*entries)
    return timeseries


def load_srt_timeseries(
    filepath: Path, units, sample_rate: int = 1, points: list[SrtPoint] | None = None
) -> Timeseries:
    """Load an SRT file and return a Timeseries.

    This is the main entry point, matching the signature pattern of
    gpx.load_timeseries() and fit.load_timeseries().

    Args:
        filepath: Path to the .srt file
        units: gopro_overlay units module
        sample_rate: Take every N-th point (1 = all, 30 = ~1/sec at 30fps)
        points: Pre-parsed SRT points (avoids re-parsing if already available)

    Returns:
        Timeseries compatible with gopro_overlay rendering pipeline
    """
    if points is None:
        points = parse_srt(filepath)
    if not points:
        raise ValueError(f"No valid GPS data found in SRT file: {filepath}")
    return srt_to_timeseries(points, units, sample_rate)


def estimate_tz_offset(
    srt_path: Path, video_path: Path, points: list[SrtPoint] | None = None
) -> tuple[timedelta | None, str]:
    """Estimate timezone offset between DJI SRT local timestamps and real UTC.

    DJI drones write SRT timestamps in the drone's local time without timezone info.
    The video file's mtime is set by the OS in real UTC. Different DJI models/firmware
    set mtime differently — some at the start of recording, some at the end.

    This function tries both approaches (comparing first and last SRT points with mtime)
    and picks the one with the smallest rounding error, which indicates which approach
    correctly identifies the timezone offset.

    Handles all real-world timezone offsets including half-hour (UTC+5:30 India,
    UTC+3:30 Iran) and quarter-hour (UTC+5:45 Nepal) by rounding to the nearest
    15 minutes.

    Args:
        srt_path: Path to the .srt file
        video_path: Path to the corresponding video file
        points: Pre-parsed SRT points (avoids re-parsing if already available)

    Returns:
        Tuple of (offset, mtime_role):
        - offset: timedelta to subtract from SRT timestamps to get UTC, or None
        - mtime_role: "start" if mtime ≈ recording start, "end" if mtime ≈ recording end
    """
    if points is None:
        points = parse_srt(srt_path)
    if not points:
        return None, "start"

    if not video_path.exists():
        logger.warning("Video file not found for tz offset estimation: %s", video_path)
        return None, "start"

    stat = os.stat(video_path)
    mtime_utc = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    mtime_naive = mtime_utc.replace(tzinfo=None)

    # Try both: compare first SRT (mtime=start) and last SRT (mtime=end) with mtime.
    # The one with smaller rounding error to a standard timezone offset wins.
    diff_first = (points[0].dt - mtime_naive).total_seconds()
    diff_last = (points[-1].dt - mtime_naive).total_seconds()

    quarter_first = round(diff_first / 900)
    error_first = abs(diff_first - quarter_first * 900)

    quarter_last = round(diff_last / 900)
    error_last = abs(diff_last - quarter_last * 900)

    if error_first <= error_last:
        # mtime ≈ start of recording (first SRT point aligns better)
        offset = timedelta(minutes=quarter_first * 15)
        mtime_role = "start"
    else:
        # mtime ≈ end of recording (last SRT point aligns better)
        offset = timedelta(minutes=quarter_last * 15)
        mtime_role = "end"

    logger.info(
        f"SRT timezone offset: {offset}, mtime_role={mtime_role} "
        f"(first={points[0].dt.isoformat()}, last={points[-1].dt.isoformat()}, "
        f"mtime={mtime_utc.isoformat()}, err_first={error_first:.1f}s, err_last={error_last:.1f}s)"
    )

    return offset, mtime_role


def srt_to_gpx_file(
    filepath: Path,
    output_path: Path,
    sample_rate: int = 1,
    tz_offset: timedelta | None = None,
    points: list[SrtPoint] | None = None,
) -> Path:
    """Convert a DJI SRT file to GPX format.

    Used for CLI rendering via gopro-dashboard.py which only accepts GPX/FIT.

    Args:
        filepath: Path to the .srt file
        output_path: Path for the output .gpx file
        sample_rate: Take every N-th point (1 = all, 30 = ~1/sec at 30fps)
        tz_offset: Timezone offset to subtract from SRT timestamps (local→UTC).
                   Use estimate_tz_offset() to calculate this from video file mtime.
        points: Pre-parsed SRT points (avoids re-parsing if already available)

    Returns:
        Path to the generated GPX file
    """
    if points is None:
        points = parse_srt(filepath)
    if not points:
        raise ValueError(f"No valid GPS data found in SRT file: {filepath}")

    sampled = points[::sample_rate] if sample_rate > 1 else points
    offset = tz_offset or timedelta(0)

    # Build GPX XML
    gpx = Element(
        "gpx",
        {
            "version": "1.1",
            "creator": "gpstitch",
            "xmlns": "http://www.topografix.com/GPX/1/1",
        },
    )

    trk = SubElement(gpx, "trk")
    SubElement(trk, "name").text = filepath.stem
    trkseg = SubElement(trk, "trkseg")

    for point in sampled:
        adjusted_dt = point.dt - offset
        trkpt = SubElement(
            trkseg,
            "trkpt",
            {
                "lat": f"{point.lat:.6f}",
                "lon": f"{point.lon:.6f}",
            },
        )
        SubElement(trkpt, "ele").text = f"{point.rel_alt:.1f}"
        SubElement(trkpt, "time").text = adjusted_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    tree = ElementTree(gpx)
    tree.write(str(output_path), encoding="utf-8", xml_declaration=True)

    return output_path


def estimate_srt_fps(filepath: Path, points: list[SrtPoint] | None = None) -> float:
    """Estimate the frame rate of an SRT file from point timestamps.

    Args:
        filepath: Path to the .srt file
        points: Pre-parsed SRT points (avoids re-parsing if already available)

    Returns:
        Estimated frames per second (e.g., 29.97, 30.0, 25.0)
    """
    if points is None:
        points = parse_srt(filepath)
    if len(points) < 2:
        return 1.0

    duration = (points[-1].dt - points[0].dt).total_seconds()
    if duration <= 0:
        return 1.0

    return len(points) / duration


def calc_sample_rate(source_hz: float, target_hz: int) -> int:
    """Calculate sample_rate (every N-th point) to achieve target Hz.

    Args:
        source_hz: Source data rate in Hz (e.g., 30.0 for 30fps SRT)
        target_hz: Target rate in Hz (e.g., 1 for 1 point/sec)

    Returns:
        Integer sample_rate (minimum 1, meaning no thinning)
    """
    if target_hz <= 0 or source_hz <= target_hz:
        return 1
    return max(1, round(source_hz / target_hz))


def get_srt_metadata(filepath: Path, points: list[SrtPoint] | None = None) -> dict:
    """Extract basic metadata from an SRT file.

    Args:
        filepath: Path to the .srt file
        points: Pre-parsed SRT points (avoids re-parsing if already available)

    Returns:
        Dict with gps_point_count and duration_seconds
    """
    if points is None:
        points = parse_srt(filepath)

    duration = None
    if len(points) > 1:
        duration = (points[-1].dt - points[0].dt).total_seconds()

    return {
        "gps_point_count": len(points),
        "duration_seconds": duration,
    }
