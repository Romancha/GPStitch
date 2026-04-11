"""Preview rendering service using gopro_overlay."""

import asyncio
import base64
import datetime
import io
import logging
import os
import re
import shlex
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from gopro_overlay import timeseries_process
from PIL import Image, ImageFont

from gpstitch.config import settings
from gpstitch.constants import (
    DEFAULT_GPS_DOP_MAX,
    DEFAULT_GPS_SPEED_MAX,
    DEFAULT_GPS_TARGET_HZ,
    DEFAULT_UNITS_ALTITUDE,
    DEFAULT_UNITS_DISTANCE,
    DEFAULT_UNITS_SPEED,
    DEFAULT_UNITS_TEMPERATURE,
    PYCAIRO_INSTALL_HINT,
    UNIT_OPTIONS,
    is_pycairo_available,
)
from gpstitch.scripts.gopro_dashboard_wrapper import (
    TS_DJI_META_SOURCE_ARG,
    TS_ODO_OFFSET_ARG,
    TS_SRT_SOURCE_ARG,
    TS_SRT_VIDEO_ARG,
)

logger = logging.getLogger(__name__)

# Apply runtime patches if enabled
if settings.enable_gopro_patches:
    from gpstitch.patches import apply_patches

    apply_patches()

# Thread pool for running sync code that uses asyncio (geotiler)
_executor = ThreadPoolExecutor(max_workers=2)


# Shared font list for consistency between preview and CLI render
_FONTS_TO_TRY = [
    # Standard Roboto font (may be installed)
    "Roboto-Medium.ttf",
    # macOS system fonts
    "/Library/Fonts/SF-Pro.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Geneva.ttf",
    "/System/Library/Fonts/Monaco.ttf",
    "/Library/Fonts/Arial.ttf",
    # Linux common fonts
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    # Windows fonts
    "C:/Windows/Fonts/arial.ttf",
    # Generic names (PIL will search system paths)
    "Arial",
    "Helvetica",
]


def _find_available_font() -> str | None:
    """Find an available font file. Used by both preview and CLI render."""
    from pathlib import Path

    for font in _FONTS_TO_TRY:
        path = Path(font)
        if path.is_absolute() and path.exists():
            return str(path)
        # For non-absolute paths, try to find via font loader
        try:
            from gopro_overlay.font import load_font

            load_font(font)
            return font  # Font name is valid
        except (OSError, ImportError):
            continue

    return None


def _load_font_with_fallback():
    """Load font with fallback to system fonts. Uses same list as CLI."""
    from gopro_overlay.font import load_font

    for font_name in _FONTS_TO_TRY:
        try:
            return load_font(font_name)
        except OSError:
            continue

    # Last resort - use default PIL font
    return ImageFont.load_default()


@dataclass
class LayoutInfo:
    """Information about an available layout."""

    name: str
    display_name: str
    width: int
    height: int
    requires_cairo: bool = False


def _discover_local_layouts() -> list[str]:
    """Discover layout names from the gpstitch layouts/ directory."""
    layouts_dir = Path(__file__).parent.parent / "layouts"
    if not layouts_dir.is_dir():
        return []
    return sorted(p.stem for p in layouts_dir.glob("*.xml"))


def _read_canvas_dims_from_sidecar(layout_xml_path: str | Path) -> tuple[int, int] | None:
    """Read canvas width/height from the sidecar JSON metadata of a custom template.

    Custom templates saved from the Advanced Mode editor are stored as two files:
    ``{name}.xml`` (the layout) and ``{name}.json`` (metadata including canvas dimensions
    the user set in the editor). This helper reads the sidecar to recover those
    dimensions so the render command can pass ``--overlay-size`` matching the editor
    canvas — preventing the widget-shift bug where pixel-absolute coordinates designed
    for one canvas size got rendered onto a different-size overlay.

    Returns (width, height) on success, or None when:
    - the XML path has no sidecar JSON (raw XML / pre-fix templates)
    - the JSON is malformed
    - the JSON doesn't contain ``canvas_width`` and ``canvas_height`` keys
    - the values are non-integer

    Callers must treat None as "fall back to the default behavior".
    """
    import json as _json

    xml_path = Path(layout_xml_path)
    sidecar_path = xml_path.with_suffix(".json")
    if not sidecar_path.is_file():
        return None
    try:
        data = _json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.debug("Could not read template sidecar %s: %s", sidecar_path, e)
        return None
    try:
        width = int(data["canvas_width"])
        height = int(data["canvas_height"])
    except (KeyError, TypeError, ValueError) as e:
        logger.debug("Template sidecar %s missing canvas dims: %s", sidecar_path, e)
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _layout_requires_cairo(name: str) -> bool:
    """Check if a layout XML contains cairo widgets."""
    # Check local layouts first
    local_path = Path(__file__).parent.parent / "layouts" / f"{name}.xml"
    if local_path.exists():
        try:
            content = local_path.read_text()
            return "cairo" in content.lower()
        except OSError:
            return False

    # Check gopro-overlay built-in layouts
    try:
        from importlib.resources import as_file, files

        from gopro_overlay import layouts as gopro_layouts

        ref = files(gopro_layouts) / f"{name}.xml"
        with as_file(ref) as path:
            content = path.read_text()
            return "cairo" in content.lower()
    except Exception:
        return False


def get_available_layouts() -> list[LayoutInfo]:
    """Get list of available layouts with their metadata."""
    layouts = []

    # Auto-discover custom layouts from layouts/ directory, then add gopro-overlay built-ins
    local_layouts = _discover_local_layouts()
    builtin_layouts = [
        "default-1920x1080",
        "default-2688x1512",
        "default-2704x1520",
        "default-3840x2160",
        "moto_1080",
        "moto_1080_2bars",
        "moto_1080_needle",
        "moto_2160",
        "moto_2160_2bars",
        "moto_2160_needle",
        "power-1920x1080",
        "example",
        "example-2",
    ]
    layout_names = local_layouts + builtin_layouts

    for name in layout_names:
        width, height = _parse_resolution(name)
        display_name = _format_display_name(name)
        layouts.append(
            LayoutInfo(
                name=name,
                display_name=display_name,
                width=width,
                height=height,
                requires_cairo=_layout_requires_cairo(name),
            )
        )

    return layouts


def _parse_resolution(name: str) -> tuple[int, int]:
    """Parse resolution from layout name."""
    # Try to extract WIDTHxHEIGHT pattern
    match = re.search(r"(\d+)x(\d+)", name)
    if match:
        return int(match.group(1)), int(match.group(2))

    # Handle moto layouts
    if "2160" in name:
        return 3840, 2160
    elif "1080" in name:
        return 1920, 1080

    # Default fallback
    return 1920, 1080


_UPPERCASE_WORDS = {"dji"}


def _format_display_name(name: str) -> str:
    """Format layout name for display."""
    # Replace underscores and hyphens with spaces
    display = name.replace("_", " ").replace("-", " ")
    # Capitalize words, keeping known abbreviations uppercase
    words = display.split()
    return " ".join(w.upper() if w.lower() in _UPPERCASE_WORDS else w.title() for w in words)


def _resolve_layout_path(layout: str) -> Path:
    """Resolve layout path, checking gpstitch layouts first.

    Layouts in src/gpstitch/layouts/ take priority over gopro-overlay built-ins.
    """
    local = Path(__file__).parent.parent / "layouts" / f"{layout}.xml"
    if local.exists():
        return local
    return Path(layout)


def _resolve_gopro_overlay_layout_path(layout: str) -> Path:
    """Resolve XML path for a gopro-overlay built-in layout."""
    from importlib.resources import files

    from gopro_overlay import layouts

    xml_path = Path(str(files(layouts) / f"{layout}.xml"))
    if not xml_path.exists():
        raise ValueError(f"Layout '{layout}' not found in gopro_overlay package (looked for {xml_path})")
    return xml_path


def get_available_units() -> dict:
    """Get available unit options from centralized constants."""
    return UNIT_OPTIONS


def get_available_map_styles() -> list[dict]:
    """Get available map styles from gopro_overlay."""
    from gopro_overlay.geo import available_map_styles

    # Map styles that require API keys (by prefix)
    API_KEY_PREFIXES = ["tf-", "geo-"]

    styles = available_map_styles()
    result = []
    for style in styles:
        # Format display name
        display_name = style.replace("-", " ").replace("_", " ").title()

        # Check if this style requires an API key
        requires_api_key = any(style.startswith(prefix) for prefix in API_KEY_PREFIXES)

        result.append(
            {
                "name": style,
                "display_name": display_name,
                "requires_api_key": requires_api_key,
            }
        )
    return result


def get_output_extension_for_profile(ffmpeg_profile: str | None) -> str:
    """Return the appropriate file extension based on the FFmpeg profile.

    Some profiles require specific container formats:
    - mov (PNG codec) → .mov (QuickTime, needed for Final Cut Pro / DaVinci Resolve)
    - vp9/vp8 (alpha channel) → .webm
    - all others → .mp4
    """
    if ffmpeg_profile == "mov":
        return ".mov"
    if ffmpeg_profile in ("vp9", "vp8"):
        return ".webm"
    return ".mp4"


def get_available_ffmpeg_profiles() -> list[dict]:
    """Get available FFmpeg encoding profiles."""
    from gopro_overlay.ffmpeg_profile import builtin_profiles

    # Profile descriptions
    profile_descriptions = {
        "nvgpu": "NVIDIA GPU acceleration (H.264, 25 Mbps)",
        "nnvgpu": "NVIDIA GPU with CUDA overlay (H.264, 25 Mbps)",
        "mov": "Lossless PNG codec (large files)",
        "vp9": "VP9 codec with alpha channel",
        "vp8": "VP8 codec with alpha channel",
        "mac_hevc": "macOS VideoToolbox HEVC (high quality)",
        "mac": "macOS VideoToolbox H.264 (high quality)",
        "qsv": "Intel QuickSync HEVC acceleration",
    }

    result = []

    # Add "default" option first
    result.append(
        {
            "name": "",
            "display_name": "Default",
            "description": "H.264, veryfast preset (balanced speed/quality)",
            "is_builtin": True,
        }
    )

    # Add builtin profiles
    for name in builtin_profiles:
        display_name = name.replace("_", " ").replace("-", " ").title()
        description = profile_descriptions.get(name, f"{name} encoding profile")

        result.append(
            {
                "name": name,
                "display_name": display_name,
                "description": description,
                "is_builtin": True,
            }
        )

    # TODO: Add user-defined profiles from ~/.gopro-graphics/ffmpeg-profiles.json

    return result


def _fit_video_to_canvas(video_frame: Image.Image, canvas_width: int, canvas_height: int) -> Image.Image:
    """Fit video frame into canvas preserving aspect ratio (pillarbox/letterbox).

    If video aspect ratio differs from canvas, the video is centered
    with black bars on sides (pillarbox) or top/bottom (letterbox).
    """
    video_w, video_h = video_frame.size
    if video_w == canvas_width and video_h == canvas_height:
        return video_frame

    # Calculate scale to fit within canvas
    scale = min(canvas_width / video_w, canvas_height / video_h)
    new_w = int(video_w * scale)
    new_h = int(video_h * scale)

    # Resize video preserving aspect ratio
    resized = video_frame.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Create black canvas and paste centered
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 255))
    offset_x = (canvas_width - new_w) // 2
    offset_y = (canvas_height - new_h) // 2
    canvas.paste(resized, (offset_x, offset_y))

    return canvas


def _extract_video_frame(file_path: Path, time_ms: int, width: int, height: int) -> Image.Image | None:
    """Extract a frame from video at specified time."""
    from gopro_overlay.ffmpeg import FFMPEG
    from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro
    from gopro_overlay.timeunits import timeunits

    try:
        ffmpeg = FFMPEG()
        ffmpeg_gopro = FFMPEGGoPro(ffmpeg)

        frame_bytes = ffmpeg_gopro.load_frame(file_path, timeunits(millis=time_ms))
        if frame_bytes:
            # Convert raw RGBA bytes to PIL Image
            frame = Image.frombytes("RGBA", (width, height), frame_bytes)
            return frame
    except Exception as e:
        logger.warning("Failed to extract video frame: %s", e)

    return None


def _extract_creation_time(file_path: Path) -> datetime.datetime | None:
    """Extract creation_time from video metadata via ffprobe.

    Returns a timezone-aware datetime or None if not found.
    """
    import json

    from gopro_overlay.ffmpeg import FFMPEG

    try:
        ffmpeg = FFMPEG()
        output = str(
            ffmpeg.ffprobe()
            .invoke(
                [
                    "-hide_banner",
                    "-print_format",
                    "json",
                    "-show_format",
                    str(file_path),
                ]
            )
            .stdout
        )
        data = json.loads(output)
        tags = data.get("format", {}).get("tags", {})
        creation_time_str = tags.get("creation_time")
        if creation_time_str:
            dt = datetime.datetime.fromisoformat(creation_time_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.UTC)
            return dt
    except Exception as e:
        logger.debug("Could not extract creation_time from %s: %s", file_path, e)

    return None


def _get_gps_time_range(gps_path: Path) -> tuple[float, float] | None:
    """Get (min_timestamp, max_timestamp) in UTC from a GPX or FIT file.

    Returns Unix timestamps or None if parsing fails.
    Uses load_external for reliable parsing (GPX/FIT always store UTC).

    Note: This re-parses the GPS file even though callers may load it again later
    for rendering. The extra parse adds ~50-200ms for typical FIT/GPX files (< 2MB),
    which is negligible vs. render times (minutes). Caching was considered but deferred
    as premature — revisit if profiling shows GPS parsing as a bottleneck.
    """
    try:
        from gopro_overlay.loading import load_external
        from gopro_overlay.units import units

        timeseries = load_external(gps_path, units)
        entries = timeseries.items()
        if len(entries) < 2:
            return None
        return (entries[0].dt.timestamp(), entries[-1].dt.timestamp())
    except (Exception, SystemExit) as e:
        logger.debug("Could not get GPS time range from %s: %s", gps_path, e)
        return None


# Known fractional (non-whole-hour) UTC offsets as signed 15-minute quarters.
# Sign matters: UTC+5:45 (Nepal) exists but UTC-5:45 does not.
# Whole-hour offsets (quarters % 4 == 0) are valid on both sides (UTC-12 to UTC+14).
_KNOWN_FRACTIONAL_TZ_QUARTERS: frozenset[int] = frozenset(
    {
        # Negative (west of UTC)
        -38,  # UTC-9:30  (Marquesas Islands)
        -14,  # UTC-3:30  (Newfoundland Standard Time)
        -10,  # UTC-2:30  (Newfoundland Daylight Time)
        # Positive (east of UTC)
        14,  # UTC+3:30  (Iran Standard Time)
        18,  # UTC+4:30  (Afghanistan Time)
        22,  # UTC+5:30  (India, Sri Lanka)
        23,  # UTC+5:45  (Nepal)
        26,  # UTC+6:30  (Myanmar, Cocos Islands)
        35,  # UTC+8:45  (Eucla)
        38,  # UTC+9:30  (Australian Central Standard Time)
        42,  # UTC+10:30 (Lord Howe Island)
        51,  # UTC+12:45 (Chatham Islands)
        55,  # UTC+13:45 (Chatham Islands DST)
    }
)


def _is_valid_tz_offset(quarters: int) -> bool:
    """Check if offset (in 15-min quarters) corresponds to a real timezone.

    The `quarters` parameter is the correction to apply (negative of the
    camera's timezone). The camera timezone is therefore `-quarters`.
    """
    camera_tz = -quarters
    if camera_tz % 4 == 0:
        # Whole-hour: valid range is UTC-12 to UTC+14 (asymmetric)
        return -48 <= camera_tz <= 56
    return camera_tz in _KNOWN_FRACTIONAL_TZ_QUARTERS


def _overlap_seconds(shifted_start: float, duration: float, gps_min: float, gps_max: float) -> float:
    """Compute overlap in seconds between shifted video interval and GPS range."""
    return max(0.0, min(shifted_start + duration, gps_max) - max(shifted_start, gps_min))


@dataclass
class CorrectionResult:
    """Result from _validate_creation_time with correction metadata."""

    time: datetime.datetime
    correction_type: str | None = None  # None, "system-tz", "exhaustive", or "mtime"
    tz_correction_hours: float | None = None  # set for "system-tz" and "exhaustive"
    suggested_offset_seconds: int | None = None  # only set when correction failed


def _get_system_tz_offset(reference_dt: datetime.datetime | None = None) -> datetime.timedelta:
    """Return the system's UTC offset that was in effect at `reference_dt`.

    When `reference_dt` is provided, uses Python's `astimezone()` to look up the
    historical offset for that specific moment — this correctly handles DST
    transitions, e.g., a video recorded in PST (UTC-8) but processed after the
    DST switch in PDT (UTC-7) gets the recording-date offset, not the runtime
    offset (Bug B from issue #9).

    When `reference_dt` is None, falls back to the current local offset.
    Mockable in tests.

    Caveat: when `reference_dt` is the corrupt local-as-UTC creation_time of an
    Insta360-style file, the date in `reference_dt` is correct but the hour is
    shifted by `|offset|`. For recordings made within `|offset|` hours after a
    DST switch, the astimezone() lookup may return the pre-switch offset
    (off-by-one-hour). This narrow window is left to the exhaustive cascade.
    """
    if reference_dt is None:
        reference_dt = datetime.datetime.now(tz=datetime.UTC)
    return reference_dt.astimezone().utcoffset()


def _find_overlap_candidates(ct_ts: float, duration: float, gps_min: float, gps_max: float) -> list[int]:
    """Find all valid TZ offsets (in seconds) where shifted video overlaps GPS range.

    Enumerates whole-hour offsets (UTC-12 to UTC+14) and known fractional offsets.
    Returns list of correction seconds (positive = shift forward in time).
    Skips offset=0 (as-is case is checked separately).
    """
    candidates = []
    # Whole-hour: camera_tz in [-48, 56] quarters (step 4)
    for camera_q in range(-48, 57, 4):
        if camera_q == 0:
            continue
        correction_sec = -camera_q * 900
        shifted = ct_ts + correction_sec
        if _overlap_seconds(shifted, duration, gps_min, gps_max) > 0:
            candidates.append(correction_sec)
    # Fractional offsets
    for camera_q in _KNOWN_FRACTIONAL_TZ_QUARTERS:
        correction_sec = -camera_q * 900
        shifted = ct_ts + correction_sec
        if _overlap_seconds(shifted, duration, gps_min, gps_max) > 0:
            candidates.append(correction_sec)
    return candidates


def _best_guess_offset(ct_ts: float, duration: float, gps_min: float, gps_max: float) -> int:
    """Compute best-guess offset for Manual mode suggestion.

    Places video midpoint at GPS midpoint, rounded to nearest whole hour.
    Never used for auto-correction — only populates the Manual mode suggestion.
    """
    gps_mid = (gps_min + gps_max) / 2
    ct_mid = ct_ts + duration / 2
    diff_sec = gps_mid - ct_mid
    # Round to nearest whole hour
    return round(diff_sec / 3600) * 3600


def _validate_creation_time(
    file_path: Path,
    creation_time: datetime.datetime,
    video_duration_sec: float = 0.0,
    gps_path: Path | None = None,
) -> CorrectionResult:
    """Validate creation_time against GPS data and file mtime.

    Problem: The MP4 spec says creation_time should be UTC, and ffprobe always
    appends a 'Z' suffix. GoPro follows the spec correctly, but cameras like
    Insta360 (Go 3S, X4, etc.) write local time into creation_time. For example,
    a video recorded at 14:00 UTC+5:30 gets creation_time "2024-01-01T19:30:00Z"
    instead of "2024-01-01T14:00:00Z". This causes time sync failures with GPS
    data — the video appears to start hours away from the actual GPS track.

    Solution: When GPS data is available, cross-validate by checking if
    creation_time overlaps the GPS time range. If it doesn't but file mtime does,
    prefer mtime (which reflects real UTC from the filesystem).

    Note on mtime reliability: mtime is preserved when copying from SD card
    (drag-and-drop, cp) which is the primary workflow. However, mtime may be
    wrong if the file was downloaded from cloud storage (e.g. Insta360 app sync)
    or cloned from git — in those cases mtime reflects the download/checkout time.
    When neither creation_time nor mtime overlaps GPS, we fall back to creation_time
    which limits the blast radius of a corrupted mtime.

    Args:
        file_path: Path to the video file.
        creation_time: Extracted creation_time (may be wrong timezone).
        video_duration_sec: Video duration in seconds (0 = unknown, validation skipped).
        gps_path: Path to secondary GPS file (GPX/FIT) or None.

    Returns:
        CorrectionResult with validated datetime and correction metadata.
    """
    no_correction = CorrectionResult(time=creation_time)

    if gps_path is None or gps_path.suffix.lower() not in (".gpx", ".fit"):
        return no_correction

    if video_duration_sec <= 0:
        return no_correction

    gps_range = _get_gps_time_range(gps_path)
    if gps_range is None:
        return no_correction

    gps_min, gps_max = gps_range
    ct_ts = creation_time.timestamp()

    # Pre-compute both candidates upfront so we can detect ambiguity (Bug A from issue #9).
    # Bug A trigger: when GPS range is wide enough to contain BOTH the as-is creation_time
    # and the system-tz-shifted creation_time, Step 1 used to win greedily and silently
    # return the wrong answer for non-GoPro cameras (Insta360 local-as-UTC bug). We don't
    # change behavior here — Step 1 still wins — but we emit a warning so silent
    # miscorrections become discoverable in logs.
    system_tz = _get_system_tz_offset(creation_time)  # Bug B: use historical offset
    system_tz_seconds = int(system_tz.total_seconds())
    system_shifted = ct_ts + (-system_tz_seconds)  # negate: UTC-7 means +7h correction

    as_is_overlap = _overlap_seconds(ct_ts, video_duration_sec, gps_min, gps_max)
    sys_overlap = (
        _overlap_seconds(system_shifted, video_duration_sec, gps_min, gps_max) if system_tz_seconds != 0 else 0.0
    )

    if as_is_overlap > 0 and sys_overlap > 0:
        shifted_dt_for_log = datetime.datetime.fromtimestamp(system_shifted, tz=datetime.UTC)
        logger.warning(
            "Ambiguous time alignment for %s: both as-is (%s) and system-tz-shifted (%s) "
            "overlap GPS range. Using as-is. If sync looks wrong, switch to Manual offset mode. "
            "(issue #9)",
            file_path.name,
            creation_time.isoformat(),
            shifted_dt_for_log.isoformat(),
        )

    # Step 1: creation_time as-is overlaps GPS → no correction needed
    if as_is_overlap > 0:
        return no_correction

    # Step 2: system timezone correction
    if sys_overlap > 0:
        shifted_dt = datetime.datetime.fromtimestamp(system_shifted, tz=datetime.UTC)
        correction_hours = (-system_tz_seconds) / 3600
        logger.info(
            "System timezone correction: creation_time %s shifted by %+.1fh → %s",
            creation_time.isoformat(),
            correction_hours,
            shifted_dt.isoformat(),
        )
        return CorrectionResult(
            time=shifted_dt,
            correction_type="system-tz",
            tz_correction_hours=correction_hours,
        )

    # Step 3: exhaustive search over all valid TZ offsets
    candidates = _find_overlap_candidates(ct_ts, video_duration_sec, gps_min, gps_max)
    system_correction_sec = -system_tz_seconds

    if len(candidates) == 1:
        offset_sec = candidates[0]
        shifted_ts = ct_ts + offset_sec
        shifted_dt = datetime.datetime.fromtimestamp(shifted_ts, tz=datetime.UTC)
        correction_hours = offset_sec / 3600
        logger.info(
            "Exhaustive TZ search: creation_time %s shifted by %+.1fh → %s",
            creation_time.isoformat(),
            correction_hours,
            shifted_dt.isoformat(),
        )
        return CorrectionResult(
            time=shifted_dt,
            correction_type="exhaustive",
            tz_correction_hours=correction_hours,
        )
    elif len(candidates) > 1 and system_correction_sec in candidates:
        shifted_dt = datetime.datetime.fromtimestamp(system_shifted, tz=datetime.UTC)
        correction_hours = system_correction_sec / 3600
        logger.info(
            "Multiple TZ candidates found, using system timezone: %s shifted by %+.1fh → %s",
            creation_time.isoformat(),
            correction_hours,
            shifted_dt.isoformat(),
        )
        return CorrectionResult(
            time=shifted_dt,
            correction_type="system-tz",
            tz_correction_hours=correction_hours,
        )
    # len > 1 but system TZ not among them, or len == 0 → fall through

    # Step 4: mtime as-is (last resort, no TZ shifting)
    try:
        mtime_ts = os.stat(file_path).st_mtime
    except OSError:
        mtime_ts = None

    if mtime_ts is not None:
        mtime_start_overlaps = _overlap_seconds(mtime_ts, video_duration_sec, gps_min, gps_max) > 0
        mtime_end_overlaps = _overlap_seconds(mtime_ts - video_duration_sec, video_duration_sec, gps_min, gps_max) > 0

        if mtime_start_overlaps or mtime_end_overlaps:
            mtime_dt = datetime.datetime.fromtimestamp(mtime_ts, tz=datetime.UTC)
            if mtime_end_overlaps and not mtime_start_overlaps:
                mtime_dt = mtime_dt - datetime.timedelta(seconds=video_duration_sec)
            logger.warning(
                "Using file mtime as last resort: creation_time %s → mtime %s",
                creation_time.isoformat(),
                mtime_dt.isoformat(),
            )
            return CorrectionResult(time=mtime_dt, correction_type="mtime")

    # Step 5: complete failure — populate best-guess for Manual mode
    suggested = _best_guess_offset(ct_ts, video_duration_sec, gps_min, gps_max)
    logger.warning(
        "Timezone auto-correction failed for %s. Suggested manual offset: %+ds",
        creation_time.isoformat(),
        suggested,
    )
    return CorrectionResult(
        time=creation_time,
        correction_type=None,
        suggested_offset_seconds=suggested,
    )


def _resolve_time_alignment(
    file_path: Path,
    video_time_alignment: str | None,
    ffmpeg_gopro,
    time_offset_seconds: int = 0,
    gpx_path: Path | None = None,
):
    """Resolve video start_date and duration for GPX time alignment.

    Modes:
    - "auto": extract creation_time from video metadata (ffprobe),
      fallback to st_ctime. Returns (start_date, duration, source).
    - "gpx-timestamps": no alignment, GPX used as-is.
      Returns (None, None, None).
    - "manual": auto-detected time + offset shift.
      Returns (start_date + offset, duration, source).

    When gpx_path is provided, cross-validates creation_time against GPS data
    to detect cameras that store local time as UTC (e.g. Insta360).

    Returns (start_date, duration, source) where source is
    "media-created", "system-tz", "exhaustive", "mtime", "file-created", "failed", or None.
    """
    if not video_time_alignment or video_time_alignment == "gpx-timestamps":
        return None, None, None

    recording = ffmpeg_gopro.find_recording(file_path)
    duration = recording.video.duration
    duration_sec = duration.millis() / 1000.0

    creation_time = _extract_creation_time(file_path)
    if creation_time is not None:
        result = _validate_creation_time(file_path, creation_time, duration_sec, gpx_path)
        start_date = result.time
        if result.correction_type is not None:
            source = result.correction_type  # "system-tz", "exhaustive", or "mtime"
        elif result.suggested_offset_seconds is not None:
            source = "failed"
        else:
            source = "media-created"
    else:
        from gopro_overlay.ffmpeg_gopro import filestat

        fstat = filestat(file_path)
        start_date = fstat.ctime
        source = "file-created"

    if video_time_alignment == "manual" and time_offset_seconds:
        start_date = start_date + datetime.timedelta(seconds=time_offset_seconds)

    return start_date, duration, source


def _align_timezone(start_date, timeseries):
    """Align start_date timezone with the timeseries data.

    SRT timeseries produces naive datetimes in the drone's local time,
    while start_date from video metadata is UTC-aware. Simply stripping
    tzinfo would leave a multi-hour gap (e.g. UTC 07:21 vs local 10:21).

    Instead, estimate the UTC offset by comparing start_date with the
    timeseries midpoint and round to the nearest 15-minute timezone
    boundary, then convert start_date to the local time domain.
    """
    if start_date is None or len(timeseries) == 0:
        return start_date
    if start_date.tzinfo is not None and timeseries.min.tzinfo is None:
        # start_date is UTC-aware, timeseries is naive local time.
        # Estimate the local timezone offset from the data.
        start_naive_utc = start_date.replace(tzinfo=None)
        ts_mid = timeseries.min + (timeseries.max - timeseries.min) / 2
        diff_seconds = (ts_mid - start_naive_utc).total_seconds()
        # Round to nearest 15 minutes (handles UTC+5:30, UTC+5:45, etc.)
        quarter_hours = round(diff_seconds / 900)
        tz_offset = datetime.timedelta(seconds=quarter_hours * 900)
        return start_naive_utc + tz_offset
    if start_date.tzinfo is None and timeseries.min.tzinfo is not None:
        return start_date.replace(tzinfo=timeseries.min.tzinfo)
    return start_date


def _apply_timeseries_processing(timeseries):
    """Apply post-processing to compute calculated metrics (speed, distance, etc.).

    External GPX/FIT files only contain raw GPS points. This runs the same
    processing pipeline as gopro-dashboard.py to derive cspeed, dist, codo, etc.

    Must be called on the full Timeseries BEFORE timeseries_to_framemeta() so that
    cumulative metrics like codo reflect the absolute distance from the track start,
    not relative to the video segment.
    """
    timeseries.process_deltas(timeseries_process.calculate_speeds(), skip=1)
    timeseries.process(timeseries_process.calculate_odo())


def _load_external_timeseries(filepath: Path, units):
    """Load telemetry from GPX, FIT, or SRT file into a Timeseries.

    Automatically thins high-frequency data (e.g. DJI SRT at 30fps)
    to DEFAULT_GPS_TARGET_HZ (1 Hz) for optimal rendering performance.
    """
    target_hz = DEFAULT_GPS_TARGET_HZ

    if filepath.suffix.lower() == ".srt":
        from gpstitch.services.srt_parser import (
            calc_sample_rate,
            estimate_srt_fps,
            load_srt_timeseries,
            parse_srt,
        )

        points = parse_srt(filepath)
        source_hz = estimate_srt_fps(filepath, points=points)
        sample_rate = calc_sample_rate(source_hz, target_hz)

        return load_srt_timeseries(filepath, units, sample_rate, points=points)

    from gopro_overlay.loading import load_external

    timeseries = load_external(filepath, units)
    return _thin_timeseries(timeseries, target_hz)


def _thin_timeseries(timeseries, target_hz: int):
    """Thin a Timeseries to approximately target_hz points per second.

    Uses uniform time-based sampling. If source data is already at or below
    the target rate, returns unchanged.
    """
    entries = timeseries.items()
    if len(entries) < 2:
        return timeseries

    # Estimate source rate from timestamps
    total_seconds = (entries[-1].dt - entries[0].dt).total_seconds()
    if total_seconds <= 0:
        return timeseries

    source_hz = len(entries) / total_seconds
    if source_hz <= target_hz * 1.5:  # Allow some tolerance
        return timeseries

    # Calculate step and sample
    step = max(1, round(source_hz / target_hz))
    sampled = entries[::step]

    new_ts = type(timeseries)()
    new_ts.add(*sampled)
    return new_ts


def _load_dji_meta_for_preview(file_path: Path, units):
    """Load GPS timeseries from embedded DJI meta stream for preview rendering.

    Detects DJI meta stream, extracts GPS points, thins to target Hz, and
    returns a processed Timeseries ready for framemeta conversion.

    Args:
        file_path: Path to the video file with DJI meta stream
        units: gopro_overlay units module

    Returns:
        Timeseries with GPS data and calculated speeds/odometer

    Raises:
        ValueError: If no DJI meta stream or GPS data found
    """
    from gpstitch.services.dji_meta_parser import (
        parse_dji_meta_file,
    )
    from gpstitch.services.srt_parser import calc_sample_rate

    target_hz = DEFAULT_GPS_TARGET_HZ

    points = parse_dji_meta_file(file_path)
    if not points:
        raise ValueError(f"No valid GPS data found in DJI meta stream: {file_path}")

    # Estimate source rate from timestamps
    if len(points) > 1:
        duration_s = (points[-1].timestamp - points[0].timestamp).total_seconds()
        if duration_s > 0:
            source_hz = len(points) / duration_s
            sample_rate = calc_sample_rate(source_hz, target_hz)
        else:
            sample_rate = 1
    else:
        sample_rate = 1

    from gpstitch.services.dji_meta_parser import dji_meta_to_timeseries

    timeseries = dji_meta_to_timeseries(points, units, sample_rate)
    _apply_timeseries_processing(timeseries)
    return timeseries


def _resolve_dji_meta_start_date(file_path: Path, ffmpeg_gopro, video_time_alignment=None, time_offset_seconds=None):
    """Resolve video start_date from DJI meta GPS timestamps.

    Uses the first GPS point's timestamp, adjusted for any GPS lock delay
    (frame offset). This keeps preview and render aligned on the same source.

    Returns (start_date, duration) or falls back to _resolve_time_alignment
    if DJI meta parsing fails.
    """
    try:
        from gpstitch.services.dji_meta_parser import parse_dji_meta_file

        points = parse_dji_meta_file(file_path)
        if points:
            recording = ffmpeg_gopro.find_recording(file_path)
            duration = recording.video.duration

            first_ts = points[0].timestamp
            # Account for GPS lock delay: subtract frame offset / fps
            frame_idx = points[0].frame_idx
            if frame_idx > 0:
                fps = recording.video.frame_rate()
                if fps and fps > 0:
                    first_ts = first_ts - datetime.timedelta(seconds=frame_idx / fps)

            start_date = first_ts
            if video_time_alignment == "manual" and time_offset_seconds:
                start_date = start_date + datetime.timedelta(seconds=time_offset_seconds)
            return start_date, duration
    except Exception:
        pass

    # Fallback to standard resolution
    start_date, duration, _source = _resolve_time_alignment(
        file_path, video_time_alignment, ffmpeg_gopro, time_offset_seconds
    )
    return start_date, duration


def calculate_odo_offset(gpx_path: Path, video_start_time: datetime.datetime) -> float:
    """Calculate the odometer offset for a video within a shared GPX track.

    Loads the full GPX timeseries, computes cumulative odometer (codo),
    and returns the codo value at the given video_start_time.

    Args:
        gpx_path: Path to the GPX file.
        video_start_time: The start time of the video (timezone-aware).

    Returns:
        Odometer offset in meters (float).
    """
    from gopro_overlay.units import units

    timeseries = _load_external_timeseries(gpx_path, units)
    _apply_timeseries_processing(timeseries)

    entries = timeseries.items()
    if not entries:
        return 0.0

    # Align timezone awareness between video_start_time and timeseries
    ts_min = entries[0].dt
    if video_start_time.tzinfo is not None and ts_min.tzinfo is None:
        video_start_time = video_start_time.replace(tzinfo=None)
    elif video_start_time.tzinfo is None and ts_min.tzinfo is not None:
        video_start_time = video_start_time.replace(tzinfo=ts_min.tzinfo)

    # If video starts before the track, offset is 0
    if video_start_time <= entries[0].dt:
        return 0.0

    # If video starts after the track ends, return the final codo
    if video_start_time >= entries[-1].dt:
        last_codo = entries[-1].codo
        return float(last_codo.magnitude) if last_codo is not None else 0.0

    # Find the closest entry at or before video_start_time
    best_entry = entries[0]
    for entry in entries:
        if entry.dt <= video_start_time:
            best_entry = entry
        else:
            break

    codo = best_entry.codo
    return float(codo.magnitude) if codo is not None else 0.0


def render_preview(
    file_path: Path,
    layout: str,
    frame_time_ms: int,
    units_speed: str = DEFAULT_UNITS_SPEED,
    units_altitude: str = DEFAULT_UNITS_ALTITUDE,
    units_distance: str = DEFAULT_UNITS_DISTANCE,
    units_temperature: str = DEFAULT_UNITS_TEMPERATURE,
    map_style: str | None = None,
    gps_dop_max: float = DEFAULT_GPS_DOP_MAX,
    gps_speed_max: float = DEFAULT_GPS_SPEED_MAX,
    gpx_path: Path | None = None,
    video_time_alignment: str | None = None,
    time_offset_seconds: int = 0,
) -> tuple[bytes, int, int]:
    """Render a preview image for the given file and settings.

    Returns tuple of (png_bytes, width, height).
    """
    from gopro_overlay.ffmpeg import FFMPEG
    from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro
    from gopro_overlay.framemeta_gpx import timeseries_to_framemeta
    from gopro_overlay.geo import MapRenderer, MapStyler
    from gopro_overlay.gpmd_filters import standard as gps_filter_standard
    from gopro_overlay.layout import Overlay
    from gopro_overlay.layout_xml import Converters, layout_from_xml, load_xml_layout
    from gopro_overlay.loading import GoproLoader
    from gopro_overlay.privacy import NoPrivacyZone
    from gopro_overlay.timeunits import timeunits
    from gopro_overlay.units import units

    # Check if layout requires cairo
    if _layout_requires_cairo(layout) and not is_pycairo_available():
        raise ValueError(PYCAIRO_INSTALL_HINT)

    suffix = file_path.suffix.lower()

    # Set up converters with specified units
    converters = Converters(
        speed_unit=units_speed,
        distance_unit=units_distance,
        altitude_unit=units_altitude,
        temperature_unit=units_temperature,
    )

    # Load the layout XML
    layout_xml = load_xml_layout(_resolve_layout_path(layout))

    # Get layout dimensions
    layout_info = None
    for info in get_available_layouts():
        if info.name == layout:
            layout_info = info
            break

    if layout_info is None:
        layout_info = get_available_layouts()[0]

    # Try to extract video frame as background (for video files)
    background = None
    if suffix in (".mp4", ".mov"):
        try:
            from gpstitch.services.metadata import get_display_dimensions, get_video_rotation

            # Get display dimensions accounting for rotation
            ffmpeg = FFMPEG()
            ffmpeg_gopro = FFMPEGGoPro(ffmpeg)
            recording = ffmpeg_gopro.find_recording(file_path)
            rotation = get_video_rotation(file_path)
            video_width, video_height = get_display_dimensions(
                recording.video.dimension.x, recording.video.dimension.y, rotation
            )

            background = _extract_video_frame(file_path, frame_time_ms, video_width, video_height)
            if background and background.size != (layout_info.width, layout_info.height):
                background = _fit_video_to_canvas(background, layout_info.width, layout_info.height)
        except Exception as e:
            logger.warning("Failed to extract video frame for preview: %s", e)

    # Create base image - use video frame or black background
    image = (
        background.convert("RGBA")
        if background
        else Image.new("RGBA", (layout_info.width, layout_info.height), (0, 0, 0, 255))
    )

    # Set up map renderer with cache
    cache_dir = Path(tempfile.gettempdir()) / "gpstitch_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    style = map_style or "osm"
    styler = MapStyler()

    with MapRenderer(cache_dir, styler).open(style) as renderer:
        # Load font with fallback
        font = _load_font_with_fallback()

        # Privacy zone
        privacy = NoPrivacyZone()

        if suffix in (".mp4", ".mov"):
            # Load GoPro video
            ffmpeg = FFMPEG()
            ffmpeg_gopro = FFMPEGGoPro(ffmpeg)

            # Create GPS filter with configured thresholds
            gps_filter = gps_filter_standard(
                dop_max=gps_dop_max,
                speed_max=units.Quantity(gps_speed_max, units.kph),
            )

            loader = GoproLoader(ffmpeg_gopro, units, gps_lock_filter=gps_filter)

            try:
                gopro = loader.load(file_path)
                framemeta = gopro.framemeta
            except (OSError, TypeError, ValueError) as e:
                if gpx_path:
                    # Video has no GPS — use external GPX/FIT/SRT file
                    timeseries = _load_external_timeseries(gpx_path, units)
                    _apply_timeseries_processing(timeseries)
                    start_date, duration, _source = _resolve_time_alignment(
                        file_path,
                        video_time_alignment,
                        ffmpeg_gopro,
                        time_offset_seconds,
                        gpx_path=gpx_path,
                    )
                    start_date = _align_timezone(start_date, timeseries)
                    framemeta = timeseries_to_framemeta(timeseries, units, start_date=start_date, duration=duration)
                else:
                    # Try DJI Action embedded GPS (DJI meta stream)
                    from gpstitch.services.dji_meta_parser import detect_dji_meta_stream

                    if detect_dji_meta_stream(file_path) is not None:
                        timeseries = _load_dji_meta_for_preview(file_path, units)
                        start_date, duration = _resolve_dji_meta_start_date(
                            file_path, ffmpeg_gopro, video_time_alignment, time_offset_seconds
                        )
                        start_date = _align_timezone(start_date, timeseries)
                        framemeta = timeseries_to_framemeta(timeseries, units, start_date=start_date, duration=duration)
                    else:
                        raise ValueError("Video file does not contain GPS metadata") from e

        else:
            # Load GPX, FIT, or SRT file
            timeseries = _load_external_timeseries(file_path, units)
            _apply_timeseries_processing(timeseries)
            framemeta = timeseries_to_framemeta(timeseries, units)

        # Parse the layout XML
        create_widgets = layout_from_xml(
            layout_xml,
            renderer=renderer,
            framemeta=framemeta,
            font=font,
            privacy=privacy,
            converters=converters,
        )

        # Create overlay
        overlay = Overlay(framemeta, create_widgets)

        # Draw at specified time
        pts = timeunits(millis=frame_time_ms)
        image = overlay.draw(pts, image)

    # Convert to PNG bytes
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    png_bytes = buffer.getvalue()

    return png_bytes, layout_info.width, layout_info.height


def image_to_base64(png_bytes: bytes) -> str:
    """Convert PNG bytes to base64 string."""
    return base64.b64encode(png_bytes).decode("utf-8")


async def render_preview_from_layout(
    layout,
    file_path: Path | None = None,
    frame_time_ms: int = 0,
    units_speed: str = DEFAULT_UNITS_SPEED,
    units_altitude: str = DEFAULT_UNITS_ALTITUDE,
    units_distance: str = DEFAULT_UNITS_DISTANCE,
    units_temperature: str = DEFAULT_UNITS_TEMPERATURE,
    map_style: str | None = None,
    gps_dop_max: float = DEFAULT_GPS_DOP_MAX,
    gps_speed_max: float = DEFAULT_GPS_SPEED_MAX,
    gpx_path: Path | None = None,
    video_time_alignment: str | None = None,
    time_offset_seconds: int = 0,
) -> dict:
    """
    Render preview from an editor layout.

    Args:
        layout: EditorLayout object with widgets
        file_path: Optional path to uploaded video/gpx/fit file
        frame_time_ms: Time in milliseconds for the preview frame
        units_speed: Speed unit (kph, mph, knots, pace)
        units_altitude: Altitude unit (metre, foot)
        units_distance: Distance unit (km, mile)
        units_temperature: Temperature unit (degC, degF)
        map_style: Map style to use

    Returns:
        Dict with image_base64, width, height
    """
    from gpstitch.services.xml_converter import xml_converter

    # Convert layout to XML
    xml_content = xml_converter.layout_to_xml(layout)

    # Check if layout contains cairo widgets
    if "cairo" in xml_content.lower() and not is_pycairo_available():
        raise ValueError(PYCAIRO_INSTALL_HINT)

    width = layout.canvas.width
    height = layout.canvas.height

    # If we have an uploaded file, try to render with actual data
    if file_path and file_path.exists():
        # Run in separate thread to avoid asyncio conflicts with geotiler
        loop = asyncio.get_running_loop()
        png_bytes, _, _ = await loop.run_in_executor(
            _executor,
            lambda: _render_layout_with_data(
                xml_content,
                file_path,
                frame_time_ms,
                width,
                height,
                units_speed,
                units_altitude,
                units_distance,
                units_temperature,
                map_style,
                gps_dop_max,
                gps_speed_max,
                gpx_path,
                video_time_alignment,
                time_offset_seconds,
            ),
        )
        return {
            "image_base64": image_to_base64(png_bytes),
            "width": width,
            "height": height,
            "frame_time_ms": frame_time_ms,
        }

    # No file uploaded - render placeholder preview
    png_bytes = _render_layout_placeholder(xml_content, width, height)

    return {
        "image_base64": image_to_base64(png_bytes),
        "width": width,
        "height": height,
        "frame_time_ms": frame_time_ms,
    }


def _render_layout_with_data(
    xml_content: str,
    file_path: Path,
    frame_time_ms: int,
    width: int,
    height: int,
    units_speed: str = DEFAULT_UNITS_SPEED,
    units_altitude: str = DEFAULT_UNITS_ALTITUDE,
    units_distance: str = DEFAULT_UNITS_DISTANCE,
    units_temperature: str = DEFAULT_UNITS_TEMPERATURE,
    map_style: str | None = None,
    gps_dop_max: float = DEFAULT_GPS_DOP_MAX,
    gps_speed_max: float = DEFAULT_GPS_SPEED_MAX,
    gpx_path: Path | None = None,
    video_time_alignment: str | None = None,
    time_offset_seconds: int = 0,
) -> tuple[bytes, int, int]:
    """Render layout XML with actual data from file."""
    from gopro_overlay.ffmpeg import FFMPEG
    from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro
    from gopro_overlay.framemeta_gpx import timeseries_to_framemeta
    from gopro_overlay.geo import MapRenderer, MapStyler
    from gopro_overlay.gpmd_filters import standard as gps_filter_standard
    from gopro_overlay.layout import Overlay
    from gopro_overlay.layout_xml import Converters, layout_from_xml
    from gopro_overlay.loading import GoproLoader
    from gopro_overlay.privacy import NoPrivacyZone
    from gopro_overlay.timeunits import timeunits
    from gopro_overlay.units import units

    suffix = file_path.suffix.lower()

    converters = Converters(
        speed_unit=units_speed,
        distance_unit=units_distance,
        altitude_unit=units_altitude,
        temperature_unit=units_temperature,
    )

    # Try to extract video frame as background (for MP4 files)
    background = None
    if suffix in (".mp4", ".mov"):
        try:
            from gpstitch.services.metadata import get_display_dimensions, get_video_rotation

            ffmpeg = FFMPEG()
            ffmpeg_gopro = FFMPEGGoPro(ffmpeg)
            recording = ffmpeg_gopro.find_recording(file_path)
            rotation = get_video_rotation(file_path)
            video_width, video_height = get_display_dimensions(
                recording.video.dimension.x, recording.video.dimension.y, rotation
            )

            background = _extract_video_frame(file_path, frame_time_ms, video_width, video_height)
            if background and background.size != (width, height):
                background = _fit_video_to_canvas(background, width, height)
        except Exception as e:
            logger.warning("Failed to extract video frame for editor preview: %s", e)

    # Create base image - use video frame or black background
    image = background.convert("RGBA") if background else Image.new("RGBA", (width, height), (0, 0, 0, 255))

    # Set up map renderer
    cache_dir = Path(tempfile.gettempdir()) / "gpstitch_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    styler = MapStyler()
    style = map_style or "osm"

    with MapRenderer(cache_dir, styler).open(style) as renderer:
        font = _load_font_with_fallback()
        privacy = NoPrivacyZone()

        if suffix in (".mp4", ".mov"):
            ffmpeg = FFMPEG()
            ffmpeg_gopro = FFMPEGGoPro(ffmpeg)

            # Create GPS filter with configured thresholds
            gps_filter = gps_filter_standard(
                dop_max=gps_dop_max,
                speed_max=units.Quantity(gps_speed_max, units.kph),
            )

            loader = GoproLoader(ffmpeg_gopro, units, gps_lock_filter=gps_filter)
            try:
                gopro = loader.load(file_path)
                framemeta = gopro.framemeta
            except (OSError, TypeError, ValueError) as e:
                if gpx_path:
                    timeseries = _load_external_timeseries(gpx_path, units)
                    _apply_timeseries_processing(timeseries)
                    start_date, duration, _source = _resolve_time_alignment(
                        file_path,
                        video_time_alignment,
                        ffmpeg_gopro,
                        time_offset_seconds,
                        gpx_path=gpx_path,
                    )
                    start_date = _align_timezone(start_date, timeseries)
                    framemeta = timeseries_to_framemeta(timeseries, units, start_date=start_date, duration=duration)
                else:
                    # Try DJI Action embedded GPS (DJI meta stream)
                    from gpstitch.services.dji_meta_parser import detect_dji_meta_stream

                    if detect_dji_meta_stream(file_path) is not None:
                        timeseries = _load_dji_meta_for_preview(file_path, units)
                        start_date, duration = _resolve_dji_meta_start_date(
                            file_path, ffmpeg_gopro, video_time_alignment, time_offset_seconds
                        )
                        start_date = _align_timezone(start_date, timeseries)
                        framemeta = timeseries_to_framemeta(timeseries, units, start_date=start_date, duration=duration)
                    else:
                        raise ValueError(f"Could not load GPS data from video: {e}. Try adding a GPX/FIT file.") from e
        else:
            timeseries = _load_external_timeseries(file_path, units)
            _apply_timeseries_processing(timeseries)
            framemeta = timeseries_to_framemeta(timeseries, units)

        create_widgets = layout_from_xml(
            xml_content,
            renderer=renderer,
            framemeta=framemeta,
            font=font,
            privacy=privacy,
            converters=converters,
        )

        overlay = Overlay(framemeta, create_widgets)
        pts = timeunits(millis=frame_time_ms)
        image = overlay.draw(pts, image)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), width, height


def _render_layout_placeholder(xml_content: str, width: int, height: int) -> bytes:
    """Render a placeholder preview showing widget positions."""
    from PIL import ImageDraw

    # Create dark background
    image = Image.new("RGBA", (width, height), (26, 26, 46, 255))
    draw = ImageDraw.Draw(image)

    # Draw grid
    grid_color = (50, 50, 80, 100)
    grid_size = 50
    for x in range(0, width, grid_size):
        draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
    for y in range(0, height, grid_size):
        draw.line([(0, y), (width, y)], fill=grid_color, width=1)

    # Draw center guides
    guide_color = (100, 100, 150, 100)
    draw.line([(width // 2, 0), (width // 2, height)], fill=guide_color, width=1)
    draw.line([(0, height // 2), (width, height // 2)], fill=guide_color, width=1)

    # Add text overlay
    try:
        font = _load_font_with_fallback()
        text = "Upload a file to see actual preview"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        draw.text((x, y), text, fill=(150, 150, 150, 200), font=font)
    except Exception:
        pass

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _convert_srt_to_gpx(srt_path: Path, tz_offset: timedelta | None = None) -> str:
    """Convert an SRT file to GPX, parsing once and reusing points.

    Uses a unique temp file path to avoid race conditions in concurrent renders.

    Returns:
        Path string to the generated GPX file
    """
    import uuid

    from gpstitch.services.srt_parser import (
        calc_sample_rate,
        estimate_srt_fps,
        parse_srt,
        srt_to_gpx_file,
    )

    points = parse_srt(srt_path)
    source_hz = estimate_srt_fps(srt_path, points=points)
    sample_rate = calc_sample_rate(source_hz, DEFAULT_GPS_TARGET_HZ)

    gpx_output = Path(tempfile.gettempdir()) / f"gpstitch_srt_{srt_path.stem}_{uuid.uuid4().hex[:8]}.gpx"
    srt_to_gpx_file(srt_path, gpx_output, sample_rate, tz_offset=tz_offset, points=points)
    return str(gpx_output)


def _convert_dji_meta_to_gpx(video_path: Path) -> str:
    """Convert DJI meta GPS stream to GPX for CLI compatibility.

    Uses a unique temp file path to avoid race conditions in concurrent renders.

    Returns:
        Path string to the generated GPX file
    """
    import uuid

    from gpstitch.services.dji_meta_parser import (
        dji_meta_to_gpx_file,
        parse_dji_meta_file,
    )
    from gpstitch.services.srt_parser import calc_sample_rate

    points = parse_dji_meta_file(video_path)
    # DJI Action typically records at 25fps; thin to ~1Hz
    source_hz = (
        len(points) / max((points[-1].timestamp - points[0].timestamp).total_seconds(), 1) if len(points) > 1 else 25.0
    )
    sample_rate = calc_sample_rate(source_hz, DEFAULT_GPS_TARGET_HZ)

    gpx_output = Path(tempfile.gettempdir()) / f"gpstitch_djimeta_{video_path.stem}_{uuid.uuid4().hex[:8]}.gpx"
    dji_meta_to_gpx_file(video_path, gpx_output, sample_rate, points=points)
    return str(gpx_output)


def generate_cli_command(
    session_id: str,
    output_file: str | None,
    layout: str,
    layout_xml_path: str | None = None,
    units_speed: str = DEFAULT_UNITS_SPEED,
    units_altitude: str = DEFAULT_UNITS_ALTITUDE,
    units_distance: str = DEFAULT_UNITS_DISTANCE,
    units_temperature: str = DEFAULT_UNITS_TEMPERATURE,
    map_style: str | None = None,
    gpx_merge_mode: str = "OVERWRITE",
    video_time_alignment: str | None = None,
    ffmpeg_profile: str | None = None,
    gps_dop_max: float = DEFAULT_GPS_DOP_MAX,
    gps_speed_max: float = DEFAULT_GPS_SPEED_MAX,
    odo_offset: float | None = None,
) -> tuple[str, list[str]]:
    """Generate the CLI command for full video processing.

    Supports three modes:
    1. Video only (GoPro with embedded GPS)
    2. Video + GPX/FIT merge
    3. GPX/FIT only (overlay-only mode)

    Note: All paths and values are properly shell-escaped to prevent command injection.

    Returns:
        Tuple of (command_string, temp_files) where temp_files is a list of
        temporary file paths (e.g. SRT→GPX conversions) that should be cleaned up
        after the command finishes.
    """
    import logging
    import os

    from gpstitch.services.file_manager import file_manager

    logger = logging.getLogger(__name__)

    files = file_manager.get_files(session_id)
    primary = file_manager.get_primary_file(session_id)
    secondary = file_manager.get_secondary_file(session_id)

    logger.info(f"generate_cli_command: session_id={session_id}")
    logger.info(
        f"generate_cli_command: video_time_alignment={video_time_alignment!r}, gpx_merge_mode={gpx_merge_mode!r}"
    )
    logger.info(f"generate_cli_command: files={files}")
    logger.info(f"generate_cli_command: primary={primary}")

    if not primary:
        raise ValueError(f"No primary file in session {session_id}. Available files: {files}")

    # Track temp files created during command generation (e.g. SRT→GPX)
    temp_files: list[str] = []

    primary_path = primary.file_path
    primary_type = primary.file_type

    # Auto-generate output filename if not specified
    if not output_file:
        primary_dir = os.path.dirname(primary_path)
        primary_name = os.path.splitext(os.path.basename(primary_path))[0]
        ext = get_output_extension_for_profile(ffmpeg_profile)
        output_file = os.path.join(primary_dir, f"{primary_name}_overlay{ext}")

    # Get canvas dimensions for --overlay-size.
    # Priority: sidecar JSON of a custom template > named layout lookup > fallback.
    # The sidecar branch is the fix for the editor-to-render widget shift bug: custom
    # templates saved from Advanced Mode store the user's canvas dimensions in a JSON
    # file next to the XML, and those are the dimensions the widget coordinates were
    # designed for. Without this, the fallback path silently used the first
    # discovered built-in layout's dimensions (1920x1080), causing widgets to shift.
    canvas_width, canvas_height = None, None
    if primary_type == "video":
        sidecar_dims = _read_canvas_dims_from_sidecar(layout_xml_path) if layout_xml_path else None
        if sidecar_dims is not None:
            canvas_width, canvas_height = sidecar_dims
        else:
            layout_info = None
            for info in get_available_layouts():
                if info.name == layout:
                    layout_info = info
                    break
            if layout_info is None:
                layout_info = get_available_layouts()[0]
            canvas_width, canvas_height = layout_info.width, layout_info.height

    # For DJI SRT: always use file-modified time alignment.
    # DJI videos don't have GoPro metadata, so --use-gpx-only is required.
    # SRT telemetry comes from the same recording — time alignment is determined
    # automatically from the video's mtime vs SRT timestamps.
    # mtime_role tracks whether mtime = start or end of recording (varies by DJI model).
    srt_mtime_role = "start"
    if secondary and secondary.file_type == "srt" and primary_type == "video":
        video_time_alignment = "file-modified"

    # If secondary is SRT, convert to GPX for CLI compatibility
    secondary_gpx_path = None
    if secondary and secondary.file_type == "srt":
        from gpstitch.services.srt_parser import estimate_tz_offset

        tz_offset, srt_mtime_role = estimate_tz_offset(Path(secondary.file_path), Path(primary_path))
        secondary_gpx_path = _convert_srt_to_gpx(Path(secondary.file_path), tz_offset=tz_offset)
        temp_files.append(secondary_gpx_path)
        logger.info(f"Converted secondary SRT to GPX: {secondary_gpx_path}")

    # Resolve secondary file path (use converted GPX if SRT was converted)
    secondary_path = secondary_gpx_path or (secondary.file_path if secondary else None)

    # Map new alignment modes to CLI flag values.
    # "auto" and "manual" use file-modified — render_service sets mtime to the
    # resolved start_date (creation_time or st_ctime, optionally offset).
    # "gpx-timestamps" means no alignment (GPX used as-is).
    # "file-modified" is legacy (SRT auto-detection).
    cli_time_alignment = video_time_alignment
    if video_time_alignment in ("auto", "manual"):
        cli_time_alignment = "file-modified"
    elif video_time_alignment == "gpx-timestamps":
        cli_time_alignment = None

    # Determine mode and build command
    if secondary and primary_type == "video":
        # Mode 2: Video + GPX/FIT merge
        # Note: --video-time-start only works with --use-gpx-only in gopro-dashboard.
        # When time alignment is requested, use --use-gpx-only mode instead of --gpx-merge.
        if cli_time_alignment:
            # For SRT: choose --video-time-start or --video-time-end based on detected mtime role.
            # Different DJI models set mtime at recording start or end.
            if secondary.file_type == "srt" and srt_mtime_role == "end":
                time_arg = f"--video-time-end {shlex.quote(cli_time_alignment)}"
            else:
                time_arg = f"--video-time-start {shlex.quote(cli_time_alignment)}"
            cmd_parts = [
                "gpstitch-dashboard",
                shlex.quote(primary_path),
                shlex.quote(output_file),
                "--use-gpx-only",
                f"--gpx {shlex.quote(secondary_path)}",
                time_arg,
            ]
        else:
            cmd_parts = [
                "gpstitch-dashboard",
                shlex.quote(primary_path),
                shlex.quote(output_file),
                f"--gpx {shlex.quote(secondary_path)}",
                f"--gpx-merge {shlex.quote(gpx_merge_mode)}",
            ]
        if canvas_width and canvas_height:
            cmd_parts.append(f"--overlay-size {canvas_width}x{canvas_height}")
    elif primary_type in ("gpx", "fit", "srt"):
        # Mode 3: GPX/FIT/SRT only (overlay-only mode)
        # Get overlay size from layout
        layout_info = None
        for info in get_available_layouts():
            if info.name == layout:
                layout_info = info
                break
        if layout_info is None:
            layout_info = get_available_layouts()[0]

        # Convert SRT to GPX for CLI compatibility
        gpx_primary_path = primary_path
        if primary_type == "srt":
            gpx_primary_path = _convert_srt_to_gpx(Path(primary_path))
            temp_files.append(gpx_primary_path)

        cmd_parts = [
            "gpstitch-dashboard",
            shlex.quote(output_file),
            "--use-gpx-only",
            f"--gpx {shlex.quote(gpx_primary_path)}",
            f"--overlay-size {layout_info.width}x{layout_info.height}",
        ]
        if cli_time_alignment:
            cmd_parts.append(f"--video-time-start {shlex.quote(cli_time_alignment)}")
    elif primary_type == "video" and getattr(primary.video_metadata, "has_dji_meta", False) is True and not secondary:
        # Mode 4: DJI Action video with embedded GPS (DJI meta stream)
        # Extract GPS → convert to GPX temp file → use --use-gpx-only
        dji_meta_gpx_path = _convert_dji_meta_to_gpx(Path(primary_path))
        temp_files.append(dji_meta_gpx_path)
        logger.info(f"Converted DJI meta GPS to GPX: {dji_meta_gpx_path}")

        cmd_parts = [
            "gpstitch-dashboard",
            shlex.quote(primary_path),
            shlex.quote(output_file),
            "--use-gpx-only",
            f"--gpx {shlex.quote(dji_meta_gpx_path)}",
            f"--video-time-start {shlex.quote('file-modified')}",
        ]
        if canvas_width and canvas_height:
            cmd_parts.append(f"--overlay-size {canvas_width}x{canvas_height}")
    else:
        # Mode 1: Video only (default - GoPro with embedded GPS)
        # Note: --video-time-start is not valid without --use-gpx-only
        cmd_parts = [
            "gpstitch-dashboard",
            shlex.quote(primary_path),
            shlex.quote(output_file),
        ]
        if canvas_width and canvas_height:
            cmd_parts.append(f"--overlay-size {canvas_width}x{canvas_height}")

    # Handle layout - either custom XML or predefined
    if layout_xml_path:
        # Custom template: use --layout xml --layout-xml <path>
        cmd_parts.append("--layout xml")
        cmd_parts.append(f"--layout-xml {shlex.quote(layout_xml_path)}")
    else:
        # Check if layout is a gpstitch custom layout (e.g. dji-drone-1920x1080)
        local_layout = _resolve_layout_path(layout)
        if local_layout.exists():
            cmd_parts.append("--layout xml")
            cmd_parts.append(f"--layout-xml {shlex.quote(str(local_layout))}")
        else:
            # gopro-dashboard.py only accepts: default, speed-awareness, xml
            if layout.startswith("default-"):
                cmd_parts.append("--layout default")
            elif layout == "speed-awareness":
                cmd_parts.append("--layout speed-awareness")
            else:
                # All other layouts are XML files in gopro_overlay/layouts/
                xml_path = _resolve_gopro_overlay_layout_path(layout)
                cmd_parts.append("--layout xml")
                cmd_parts.append(f"--layout-xml {shlex.quote(str(xml_path))}")

    # Always add unit options (CLI defaults differ from UI defaults)
    cmd_parts.append(f"--units-speed {shlex.quote(units_speed)}")
    cmd_parts.append(f"--units-altitude {shlex.quote(units_altitude)}")
    cmd_parts.append(f"--units-distance {shlex.quote(units_distance)}")
    cmd_parts.append(f"--units-temperature {shlex.quote(units_temperature)}")

    # Always load extra GoPro telemetry tracks (ACCL/GRAV/CORI).
    # gopro-dashboard.py defaults --load to an empty set, which skips these
    # tracks for performance. GPStitch needs them so that metric widgets bound
    # to accl.*, grav.*, and ori.pitch/roll/yaw render correctly in the final
    # video — matching the editor preview, which loads all tracks by default.
    # The flag is a no-op in --use-gpx-only paths (GPX/FIT/SRT/DJI meta), since
    # gopro-dashboard only consumes it when loading GPMF from a GoPro video.
    # See GitHub issue #15.
    cmd_parts.append("--load ACCL GRAV CORI")

    # Always add map style if specified
    if map_style:
        cmd_parts.append(f"--map-style {shlex.quote(map_style)}")

    # Add font option (auto-detect if Roboto-Medium.ttf is not available)
    font_path = _find_available_font()
    if font_path and font_path != "Roboto-Medium.ttf":
        cmd_parts.append(f"--font {shlex.quote(font_path)}")

    # Add FFmpeg profile if specified
    if ffmpeg_profile:
        cmd_parts.append(f"--profile {shlex.quote(ffmpeg_profile)}")

    # Add GPS filter parameters
    if gps_dop_max is not None:
        cmd_parts.append(f"--gps-dop-max {gps_dop_max}")
    if gps_speed_max is not None:
        cmd_parts.append(f"--gps-speed-max {gps_speed_max}")

    # Pass original SRT path to wrapper for camera metrics preservation.
    if secondary and secondary.file_type == "srt":
        cmd_parts.append(f"{TS_SRT_SOURCE_ARG} {shlex.quote(secondary.file_path)}")
        cmd_parts.append(f"{TS_SRT_VIDEO_ARG} {shlex.quote(primary_path)}")
    elif primary_type == "srt":
        # No --ts-srt-video: SRT-only mode has no video for tz-offset estimation
        cmd_parts.append(f"{TS_SRT_SOURCE_ARG} {shlex.quote(primary_path)}")

    # Pass DJI meta source path to wrapper for protobuf GPS loading.
    if getattr(primary.video_metadata, "has_dji_meta", False) is True and not secondary:
        cmd_parts.append(f"{TS_DJI_META_SOURCE_ARG} {shlex.quote(primary_path)}")

    # Pass odo offset for shared GPX batch render.
    # The wrapper strips this arg and patches calculate_odo() to start from offset.
    if odo_offset is not None:
        cmd_parts.append(f"{TS_ODO_OFFSET_ARG} {odo_offset:.3f}")

    return " ".join(cmd_parts), temp_files
