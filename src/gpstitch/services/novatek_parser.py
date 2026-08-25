"""Novatek `freeGPS` embedded GPS telemetry parser (Viofo and other dashcams).

Dashcams built on Novatek chipsets — Viofo, Azdome, Blueskysea and many others —
do not write GoPro's GPMF metadata stream, so gopro-overlay reports "Unable to
locate metadata stream — is it a GoPro file" (issue #27). The GPS is there, it
just lives elsewhere: in `freeGPS` blocks placed inside the mdat, each block
being a `free` atom whose payload starts with the `GPS ` marker.

Two ways to find them, tried in that order:

1. A `gps ` box in moov listing absolute (offset, size) pairs — present on the
   cameras that write an index, and O(1) to read.
2. A chunked scan of the file for the `freeGPS` magic — slower, but covers
   cameras that write no index and files that have been trimmed.

Block layout (all multi-byte values little-endian unless noted):

    [0:4]    block size, BIG-endian (the block is itself a `free` atom)
    [4:12]   b"freeGPS "
    [12:16]  payload marker (0x2c on the samples seen so far; not enforced,
             since variants differ between chipset generations)
    [16:40]  hour, minute, second, year (+2000), month, day — one uint32 each
    [40:44]  flags: b"A"/b"V" (fix valid / void), b"N"/b"S", b"E"/b"W", NUL
    [44:60]  lat, lon (NMEA ddmm.mmmm), speed (knots), bearing (deg) — 4 floats

Every field is range-checked before a block is accepted: an unrecognised
freeGPS variant must be skipped, never decoded into plausible-looking garbage.
"""

import logging
import math
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement

from gopro_overlay.gpmf import GPSFix
from gopro_overlay.point import Point
from gopro_overlay.timeseries import Entry, Timeseries

logger = logging.getLogger(__name__)

FREEGPS_MAGIC = b"freeGPS "
GPS_INDEX_BOX = b"gps "

_HEADER_SIZE = 60  # bytes we need from the start of a block
_KNOTS_TO_MS = 1852 / 3600
_SCAN_CHUNK = 1 << 20  # 1 MiB


@dataclass
class NovatekGpsPoint:
    """A single GPS telemetry point from a Novatek `freeGPS` block."""

    timestamp: datetime  # naive local time from the camera's GPS receiver
    lat: float
    lon: float
    speed_ms: float
    bearing_deg: float


# --- Block decoding ---


def _nmea_to_degrees(value: float) -> float:
    """Convert NMEA ddmm.mmmm / dddmm.mmmm to decimal degrees."""
    degrees = int(value // 100)
    return degrees + (value - degrees * 100) / 60


def parse_novatek_block(data: bytes) -> NovatekGpsPoint | None:
    """Decode one `freeGPS` block.

    Returns None for anything that is not a valid, GPS-locked block — a foreign
    magic, an out-of-range field, a void fix, or a truncated buffer.
    """
    if len(data) < _HEADER_SIZE or data[4:12] != FREEGPS_MAGIC:
        return None

    try:
        _, hour, minute, second, year, month, day = struct.unpack("<7I", data[12:40])
        active, ns, ew = data[40:41], data[41:42], data[42:43]
        lat_nmea, lon_nmea, speed_knots, bearing = struct.unpack("<4f", data[44:60])
    except struct.error:
        return None

    if active != b"A":
        return None  # void fix — the coordinates are stale
    if ns not in (b"N", b"S") or ew not in (b"E", b"W"):
        return None

    try:
        timestamp = datetime(2000 + year, month, day, hour, minute, second)
    except ValueError:
        return None

    if not all(math.isfinite(v) for v in (lat_nmea, lon_nmea, speed_knots, bearing)):
        return None

    lat = _nmea_to_degrees(lat_nmea)
    lon = _nmea_to_degrees(lon_nmea)
    if not (0 <= lat <= 90) or not (0 <= lon <= 180):
        return None

    return NovatekGpsPoint(
        timestamp=timestamp,
        lat=-lat if ns == b"S" else lat,
        lon=-lon if ew == b"W" else lon,
        speed_ms=max(speed_knots, 0.0) * _KNOTS_TO_MS,
        bearing_deg=bearing,
    )


# --- Block discovery ---


def _read_gps_index_box(file_path: Path) -> list[tuple[int, int]]:
    """Read the `gps ` box from moov, returning absolute (offset, size) pairs.

    The box is a flat table, so it is cheaper to find it by scanning the (small)
    moov region than to walk the full atom tree.
    """
    try:
        with file_path.open("rb") as f:
            head = f.read(_SCAN_CHUNK)
    except OSError:
        return []

    entries: list[tuple[int, int]] = []
    search_from = 0
    while True:
        marker = head.find(GPS_INDEX_BOX, search_from)
        if marker < 4:
            return entries
        search_from = marker + 4

        box_size = struct.unpack(">I", head[marker - 4 : marker])[0]
        count_at = marker + 8
        if box_size < 16 or count_at + 4 > len(head):
            continue

        count = struct.unpack(">I", head[count_at : count_at + 4])[0]
        if box_size != 16 + 8 * count or count == 0:
            continue

        table = head[marker + 12 : marker - 4 + box_size]
        if len(table) != 8 * count:
            continue

        entries = [struct.unpack(">II", table[i * 8 : i * 8 + 8]) for i in range(count)]
        logger.debug("Found gps index box in %s with %d entries", file_path.name, count)
        return entries


def _scan_for_blocks(file_path: Path) -> list[tuple[int, int]]:
    """Scan the whole file for the `freeGPS` magic.

    Chunks overlap by the magic length so a block straddling a chunk boundary is
    still found.
    """
    offsets: list[tuple[int, int]] = []
    overlap = len(FREEGPS_MAGIC)

    try:
        with file_path.open("rb") as f:
            base = 0
            carry = b""
            while chunk := f.read(_SCAN_CHUNK):
                window = carry + chunk
                start = 0
                while (found := window.find(FREEGPS_MAGIC, start)) != -1:
                    # The magic sits 4 bytes into the block (after the size field).
                    block_start = base - len(carry) + found - 4
                    if block_start >= 0:
                        offsets.append((block_start, _HEADER_SIZE))
                    start = found + 1
                base += len(chunk)
                carry = window[-overlap:] if len(window) >= overlap else window
    except OSError as e:
        logger.warning("Could not scan %s for freeGPS blocks: %s", file_path, e)
        return []

    if offsets:
        logger.debug("Scanned %s and found %d freeGPS blocks", file_path.name, len(offsets))
    return offsets


def find_novatek_gps_blocks(file_path: Path) -> list[tuple[int, int]]:
    """Locate the `freeGPS` blocks, returning absolute (offset, size) pairs.

    Prefers the `gps ` index box in moov; falls back to scanning the file.
    """
    file_path = Path(file_path)
    entries = _read_gps_index_box(file_path)
    if entries:
        return entries
    return _scan_for_blocks(file_path)


# --- File-level parsing ---


def parse_novatek_gps_file(file_path: Path) -> list[NovatekGpsPoint]:
    """Parse all valid GPS points from a Novatek dashcam video.

    Returns an empty list when the file carries no usable `freeGPS` blocks —
    callers treat that as "no embedded telemetry", not as an error.
    """
    file_path = Path(file_path)
    blocks = find_novatek_gps_blocks(file_path)
    if not blocks:
        return []

    points: list[NovatekGpsPoint] = []
    skipped = 0
    try:
        with file_path.open("rb") as f:
            for offset, size in blocks:
                f.seek(offset)
                point = parse_novatek_block(f.read(min(size, _HEADER_SIZE)))
                if point is None:
                    skipped += 1
                else:
                    points.append(point)
    except OSError as e:
        logger.warning("Could not read freeGPS blocks from %s: %s", file_path, e)
        return []

    if skipped:
        logger.debug("Skipped %d unusable freeGPS blocks in %s", skipped, file_path.name)

    points.sort(key=lambda p: p.timestamp)
    return points


def detect_novatek_gps(file_path: Path) -> bool:
    """Report whether a video carries usable Novatek `freeGPS` telemetry."""
    return bool(parse_novatek_gps_file(file_path))


def get_novatek_gps_metadata(file_path: Path, *, points: list[NovatekGpsPoint] | None = None) -> dict:
    """Summarise the embedded GPS for the upload/metadata layer.

    Args:
        file_path: Path to the video file
        points: Pre-parsed points, to avoid re-reading the file

    Returns:
        Dict with gps_point_count and duration_seconds; empty if no GPS found.
    """
    if points is None:
        points = parse_novatek_gps_file(file_path)
    if not points:
        return {}

    duration = None
    if len(points) > 1:
        duration = (points[-1].timestamp - points[0].timestamp).total_seconds()

    return {"gps_point_count": len(points), "duration_seconds": duration}


# --- Timeseries conversion and GPX export ---


def novatek_to_timeseries(points: list[NovatekGpsPoint], units, sample_rate: int = 1) -> Timeseries:
    """Convert parsed points to a gopro_overlay Timeseries.

    Novatek blocks carry no altitude, so `alt` is left at zero.

    Note the camera stamps whole seconds and can emit two blocks for the same
    one; Timeseries keys on the timestamp, so such a pair collapses to the later
    entry.
    """
    timeseries = Timeseries()

    sampled = points[::sample_rate] if sample_rate > 1 else points

    entries = [
        Entry(
            point.timestamp,
            point=Point(point.lat, point.lon),
            alt=units.Quantity(0, units.m),
            speed=units.Quantity(point.speed_ms, units.mps),
            # Without a fix value Journey.accept() skips the point entirely.
            gpsfix=GPSFix.LOCK_3D.value,
            gpslock=units.Quantity(GPSFix.LOCK_3D.value),
            packet=units.Quantity(index),
            packet_index=units.Quantity(0),
        )
        for index, point in enumerate(sampled)
    ]

    timeseries.add(*entries)
    return timeseries


def load_novatek_timeseries(file_path: Path, units, sample_rate: int = 1) -> Timeseries:
    """Load Novatek GPS from a video file and return a Timeseries.

    Raises:
        ValueError: If the file carries no usable GPS data.
    """
    points = parse_novatek_gps_file(file_path)
    if not points:
        raise ValueError(f"No valid GPS data found in Novatek freeGPS blocks: {file_path}")
    return novatek_to_timeseries(points, units, sample_rate)


def novatek_to_gpx_file(
    file_path: Path,
    output_path: Path,
    sample_rate: int = 1,
    points: list[NovatekGpsPoint] | None = None,
) -> Path:
    """Convert Novatek GPS data to GPX, for CLI rendering via gopro-dashboard.py.

    Raises:
        ValueError: If the file carries no usable GPS data.
    """
    file_path = Path(file_path)
    if points is None:
        points = parse_novatek_gps_file(file_path)
    if not points:
        raise ValueError(f"No valid GPS data found in Novatek freeGPS blocks: {file_path}")

    sampled = points[::sample_rate] if sample_rate > 1 else points

    gpx = Element(
        "gpx",
        {
            "version": "1.1",
            "creator": "gpstitch",
            "xmlns": "http://www.topografix.com/GPX/1/1",
        },
    )

    trk = SubElement(gpx, "trk")
    SubElement(trk, "name").text = file_path.stem
    trkseg = SubElement(trk, "trkseg")

    for point in sampled:
        trkpt = SubElement(trkseg, "trkpt", {"lat": f"{point.lat:.6f}", "lon": f"{point.lon:.6f}"})
        SubElement(trkpt, "time").text = point.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")

    ElementTree(gpx).write(str(output_path), encoding="utf-8", xml_declaration=True)

    return output_path
