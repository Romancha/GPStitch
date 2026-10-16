"""Patch gopro_overlay to draw the overlay at a configurable frame rate (smooth animation).

gopro-dashboard draws one overlay frame per 0.1 s of video and feeds the frames to
ffmpeg as a 10 FPS stream. Three things encode that rate and must change together:

- FrameMeta.stepper: the timeline of drawn frames. gopro-dashboard calls it only from
  its draw loop, asking for a step of ``0.1 s * timelapse_correction``.
- The ``-framerate`` of the raw overlay stream, in our FFMPEGOverlayVideo patch and in
  FFMPEGOverlay (overlay-only renders without a video).
- Overlay.draw: telemetry is sampled at ~10 Hz and FrameMeta.get() returns the previous
  sample, so without interpolation the extra frames would just repeat it.

Applied only in the render subprocess (via the wrapper's --ts-overlay-fps), never in the
server process, so previews and renders without the option keep the stock behaviour.
"""

import bisect
import contextlib
import logging

from gopro_overlay.entry import Entry
from gopro_overlay.gpmf.gpmf import GPS_FIXED_VALUES
from gopro_overlay.gpmf.visitors.cori import Orientation
from gopro_overlay.point import Point, Point3
from gopro_overlay.timeunits import Timeunit
from gopro_overlay.units import units

from gpstitch.constants import DEFAULT_OVERLAY_FPS

logger = logging.getLogger(__name__)

# Samples further apart than this are a gap in the data (signal loss, paused recording):
# hold the last value instead of sliding across it.
MAX_INTERPOLATION_GAP_US = 1_000_000

# Quantities that are counters, flags or discrete settings: interpolating them would
# produce values that never existed (e.g. gear 2.5, ISO 150 between 100 and 200).
HELD_KEYS = frozenset(
    {
        "gpsfix",
        "gpslock",
        "packet",
        "packet_count",
        "packet_index",
        "grad_other_packet",
        "grad_other_packet_index",
        "gear_front",
        "gear_rear",
        # DJI SRT camera metrics (see metric_patches.py)
        "iso",
        "shutter",
        "fnum",
        "ev",
        "focal_len",
        "ct",
    }
)

# Headings wrap around, so they are interpolated along the shortest arc (359° -> 1°
# passes 0°) and kept in the range gopro-overlay produces them in.
SIGNED_ANGLE_KEYS = frozenset({"azi"})  # (-180°, 180]
UNSIGNED_ANGLE_KEYS = frozenset({"cog"})  # [0°, 360°)


class _FrameStepper:
    """Overlay frame times from 0 to the end of the data, as FrameMeta's Stepper.

    Each time is computed from its index, so a fractional step (1/29.97 s) does not
    accumulate rounding drift over a long video.
    """

    def __init__(self, end: Timeunit, step_us: float):
        self._end_us = end.us
        self._step_us = step_us

    def __len__(self) -> int:
        return int(self._end_us // self._step_us) + 1

    def steps(self):
        index = 0
        while (us := round(index * self._step_us)) <= self._end_us:
            yield Timeunit(us)
            index += 1


def _lerp(a, b, pos: float):
    return a + (b - a) * pos


def _lerp_angle(a: float, b: float, pos: float, full_turn: float, signed: bool) -> float:
    """Shortest-arc interpolation, wrapped into (-half, half] if signed else [0, full_turn)."""
    half = full_turn / 2
    value = a + ((b - a + half) % full_turn - half) * pos
    return half - (half - value) % full_turn if signed else value % full_turn


def _lerp_angle_quantity(a, b, pos: float, signed: bool):
    full_turn = units.Quantity(360, units.degree).to(a.units).magnitude
    return units.Quantity(_lerp_angle(a.magnitude, b.to(a.units).magnitude, pos, full_turn, signed), a.units)


def _interpolate_value(key: str, a, b, pos: float):
    """Value between samples a and b at fraction pos, or a when it must not be blended."""
    if a is None or b is None or key in HELD_KEYS:
        return a

    try:
        if isinstance(a, units.Quantity):
            if key in SIGNED_ANGLE_KEYS or key in UNSIGNED_ANGLE_KEYS:
                return _lerp_angle_quantity(a, b, pos, signed=key in SIGNED_ANGLE_KEYS)
            return _lerp(a, b, pos)
        if isinstance(a, Point):
            return Point(_lerp(a.lat, b.lat, pos), _lerp_angle(a.lon, b.lon, pos, 360.0, signed=True))
        if isinstance(a, Point3):  # also PintPoint3
            return type(a)(_lerp(a.x, b.x, pos), _lerp(a.y, b.y, pos), _lerp(a.z, b.z, pos))
        if isinstance(a, Orientation):
            # Euler angles come from atan2 and wrap at ±π, roll and pitch included
            return Orientation(
                roll=_lerp_angle_quantity(a.roll, b.roll, pos, signed=True),
                pitch=_lerp_angle_quantity(a.pitch, b.pitch, pos, signed=True),
                yaw=_lerp_angle_quantity(a.yaw, b.yaw, pos, signed=True),
            )
    except Exception:
        logger.debug("Cannot interpolate %s between %r and %r, holding", key, a, b, exc_info=True)
    # Plain ints, enums, quaternions and anything unknown: hold the previous sample
    return a


def _has_fix(entry) -> bool:
    return entry.gpsfix is None or entry.gpsfix in GPS_FIXED_VALUES


def interpolate_entries(a, b, pos: float):
    """Entry between consecutive samples a and b at fraction pos (0..1)."""
    if not (_has_fix(a) and _has_fix(b)):
        return a
    items = {key: _interpolate_value(key, value, b.items.get(key), pos) for key, value in a.items.items()}
    return Entry(_lerp(a.dt, b.dt, pos), **items)


def sample_framemeta(framemeta, pts):
    """FrameMeta entry at pts, interpolated between the surrounding samples."""
    framemeta.check_modified()
    framelist = framemeta.framelist
    if pts in framemeta.frames or pts <= framelist[0] or pts >= framelist[-1]:
        return framemeta.get(pts)

    after = bisect.bisect_left(framelist, pts)
    before_pts, after_pts = framelist[after - 1], framelist[after]
    before, later = framemeta.frames[before_pts], framemeta.frames[after_pts]
    span_us = after_pts.us - before_pts.us
    if span_us > MAX_INTERPOLATION_GAP_US:
        return before
    return interpolate_entries(before, later, (pts.us - before_pts.us) / span_us)


def _draw(self, pts, image):
    """Overlay.draw with the frame's entry interpolated instead of the previous sample."""
    self._entry = sample_framemeta(self.framemeta, pts)
    return self.scene.draw(image)


def _patch_overlay_only_framerate(fps: float) -> None:
    """Replace FFMPEGOverlay.generate with a copy whose raw input runs at fps.

    Mirrors gopro_overlay 0.129.0 except for the -framerate value; the output stays
    at 30 FPS, which is why overlay-only renders are drawn at 30 FPS.
    """
    from gopro_overlay.ffmpeg_overlay import FFMPEGOverlay, flatten

    @contextlib.contextmanager
    def generate(self):
        cmd = flatten(
            [
                "-hide_banner",
                "-y",
                self.options.general,
                "-f",
                "rawvideo",
                "-framerate",
                str(fps),
                "-s",
                f"{self.overlay_size.x}x{self.overlay_size.y}",
                "-pix_fmt",
                "rgba",
                "-i",
                "-",
                "-r",
                "30",
                self.options.output,
                "-metadata",
                f"creation_time={self.creation_time.isoformat()}",
                str(self.output),
            ]
        )

        yield from self.exe.execute(self.execution, cmd)

    FFMPEGOverlay.generate = generate


def patch_overlay_fps(fps: float) -> None:
    """Make gopro-dashboard draw and encode the overlay at fps instead of 10 FPS.

    Requires apply_patches() to have run first (FFMPEGOverlayVideo patch).

    Args:
        fps: Overlay frame rate, positive and finite.
    """
    from gopro_overlay.ffmpeg_overlay import FFMPEGOverlayVideo
    from gopro_overlay.framemeta import FrameMeta
    from gopro_overlay.layout import Overlay

    if getattr(FrameMeta, "_ts_overlay_fps_patched", False):
        logger.debug("Overlay FPS already patched, skipping")
        return

    scale = DEFAULT_OVERLAY_FPS / fps

    def stepper(self, step):
        self.check_modified()
        # step is 0.1 s * timelapse_correction; keep the correction, change the rate
        return _FrameStepper(self.framelist[-1], step.us * scale)

    FrameMeta.stepper = stepper
    Overlay.draw = _draw
    FFMPEGOverlayVideo._ts_overlay_fps = fps
    _patch_overlay_only_framerate(fps)
    FrameMeta._ts_overlay_fps_patched = True
    logger.info("Patched overlay frame rate: %s FPS", fps)
