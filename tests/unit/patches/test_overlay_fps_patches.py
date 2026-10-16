"""Tests for overlay_fps_patches: smooth animation at the video frame rate (issue #26)."""

import datetime
import itertools
import math
from pathlib import Path
from unittest.mock import Mock

import pytest
from gopro_overlay.dimensions import Dimension
from gopro_overlay.entry import Entry
from gopro_overlay.ffmpeg_overlay import FFMPEGOverlay, FFMPEGOverlayVideo
from gopro_overlay.framemeta import FrameMeta
from gopro_overlay.gpmf.visitors.cori import Orientation
from gopro_overlay.layout import Overlay
from gopro_overlay.point import PintPoint3, Point, Point3
from gopro_overlay.timeunits import timeunits
from gopro_overlay.units import units

from gpstitch.patches.overlay_fps_patches import (
    _interpolate_value,
    interpolate_entries,
    patch_overlay_fps,
    sample_framemeta,
)

T0 = datetime.datetime(2026, 6, 1, 10, 0, 0, tzinfo=datetime.UTC)


def _entry(ms: int, **items) -> Entry:
    return Entry(T0 + datetime.timedelta(milliseconds=ms), **items)


def _framemeta(*entries: tuple[int, Entry]) -> FrameMeta:
    framemeta = FrameMeta()
    for ms, entry in entries:
        framemeta.add(timeunits(millis=ms), entry)
    return framemeta


def _speed(mps: float):
    return units.Quantity(mps, units.mps)


def _deg(value: float):
    return units.Quantity(value, units.degree)


def _rad(degrees: float):
    return units.Quantity(math.radians(degrees), units.radians)


def _ffmpeg_command(overlay_class, **kwargs) -> list[str]:
    """Command an overlay's generate() hands to ffmpeg."""
    ffmpeg = Mock()
    ffmpeg.execute.return_value = iter([Mock()])
    overlay = overlay_class(
        ffmpeg=ffmpeg, output=Path("out.mp4"), overlay_size=Dimension(1920, 1080), creation_time=T0, **kwargs
    )
    with overlay.generate():
        pass
    return ffmpeg.execute.call_args.args[1]


def _overlay_video_command() -> list[str]:
    return _ffmpeg_command(FFMPEGOverlayVideo, input=Path("in.mp4"), timecode="00:00:00:00")


def _framerate(cmd: list[str]) -> str:
    return cmd[cmd.index("-framerate") + 1]


@pytest.fixture(autouse=True)
def restore_patched_classes(monkeypatch):
    """Undo patch_overlay_fps after each test: it patches gopro_overlay classes globally."""
    from gpstitch.patches import apply_patches

    apply_patches()
    monkeypatch.setattr(FrameMeta, "stepper", FrameMeta.stepper)
    monkeypatch.setattr(Overlay, "draw", Overlay.draw)
    monkeypatch.setattr(FFMPEGOverlay, "generate", FFMPEGOverlay.generate)
    monkeypatch.setattr(FFMPEGOverlayVideo, "_ts_overlay_fps", FFMPEGOverlayVideo._ts_overlay_fps)
    monkeypatch.setattr(FrameMeta, "_ts_overlay_fps_patched", False, raising=False)


class TestInterpolateValue:
    """Per-field interpolation rules."""

    def test_quantity_is_linear(self):
        assert _interpolate_value("speed", _speed(10), _speed(20), 0.25) == _speed(12.5)

    def test_offset_unit_quantity(self):
        result = _interpolate_value("atemp", units.Quantity(10, units.degC), units.Quantity(20, units.degC), 0.5)
        assert result.to(units.degC).magnitude == pytest.approx(15)

    @pytest.mark.parametrize(
        ("key", "a", "b"),
        [
            ("gpsfix", 3, 2),
            ("gpslock", units.Quantity(3), units.Quantity(2)),
            ("packet_index", units.Quantity(1), units.Quantity(3)),
            ("gear_front", units.Quantity(1), units.Quantity(2)),
            ("iso", units.Quantity(100), units.Quantity(200)),
            ("speed", _speed(10), None),  # missing in the later sample
            ("counter", 1, 3),  # plain int
            ("thing", object(), object()),  # unknown type
        ],
    )
    def test_held_values(self, key, a, b):
        assert _interpolate_value(key, a, b, 0.5) is a

    @pytest.mark.parametrize(
        ("key", "a", "b", "pos", "expected"),
        [
            ("azi", 170, -170, 0.5, 180),  # crosses ±180 instead of passing 0
            ("azi", 170, -170, 0.75, -175),  # stays in (-180, 180]
            ("azi", -10, 10, 0.5, 0),
            ("cog", 350, 10, 0.5, 0),  # crosses 0/360 instead of passing 180
            ("cog", 350, 10, 0.75, 5),  # stays in [0, 360)
            ("cog", 10, 350, 0.75, 355),
            ("cog", 90, 180, 0.5, 135),
        ],
    )
    def test_headings_take_the_shortest_arc_and_keep_their_range(self, key, a, b, pos, expected):
        result = _interpolate_value(key, _deg(a), _deg(b), pos)
        assert result.units == units.degree
        assert result.magnitude == pytest.approx(expected)

    def test_point_is_linear(self):
        result = _interpolate_value("point", Point(50.0, 10.0), Point(51.0, 12.0), 0.5)
        assert (result.lat, result.lon) == pytest.approx((50.5, 11.0))

    @pytest.mark.parametrize(("pos", "lon"), [(0.5, 180.0), (0.75, -179.5)])
    def test_point_crosses_antimeridian(self, pos, lon):
        result = _interpolate_value("point", Point(0.0, 179.0), Point(0.0, -179.0), pos)
        assert result.lon == pytest.approx(lon)

    def test_pint_point3_keeps_its_type(self):
        a = PintPoint3(_speed(0), _speed(0), _speed(0))
        b = PintPoint3(_speed(2), _speed(4), _speed(6))
        result = _interpolate_value("accl", a, b, 0.5)
        assert type(result) is PintPoint3
        assert (result.x, result.y, result.z) == (_speed(1), _speed(2), _speed(3))

    def test_point3(self):
        result = _interpolate_value("grav", Point3(0, 0, 0), Point3(2, 4, 6), 0.5)
        assert type(result) is Point3
        assert (result.x, result.y, result.z) == (1, 2, 3)

    def test_orientation_wraps_each_angle(self):
        a = Orientation(roll=_rad(170), pitch=_rad(0), yaw=_rad(-170))
        b = Orientation(roll=_rad(-170), pitch=_rad(20), yaw=_rad(170))
        result = _interpolate_value("ori", a, b, 0.75)
        assert isinstance(result, Orientation)
        assert result.roll.to(units.degree).magnitude == pytest.approx(-175)
        assert result.pitch.to(units.degree).magnitude == pytest.approx(15)
        assert result.yaw.to(units.degree).magnitude == pytest.approx(175)


class TestInterpolateEntries:
    def test_interpolates_dt_and_values(self):
        a = _entry(0, speed=_speed(10), gpsfix=3)
        b = _entry(100, speed=_speed(20), gpsfix=3)
        result = interpolate_entries(a, b, 0.5)
        assert result.dt == T0 + datetime.timedelta(milliseconds=50)
        assert result.speed == _speed(15)
        assert result.gpsfix == 3

    def test_without_fix_returns_earlier_entry(self):
        a = _entry(0, speed=_speed(10), gpsfix=0)
        b = _entry(100, speed=_speed(20), gpsfix=3)
        assert interpolate_entries(a, b, 0.5) is a
        assert interpolate_entries(b, a, 0.5) is b

    def test_entries_without_gpsfix_are_interpolated(self):
        result = interpolate_entries(_entry(0, speed=_speed(10)), _entry(100, speed=_speed(20)), 0.5)
        assert result.speed == _speed(15)

    def test_key_only_in_earlier_entry_is_held(self):
        cspeed = _speed(7)
        a = _entry(0, speed=_speed(10), cspeed=cspeed)
        b = _entry(100, speed=_speed(20))
        assert interpolate_entries(a, b, 0.5).cspeed is cspeed

    def test_does_not_mutate_samples(self):
        a = _entry(0, speed=_speed(10))
        b = _entry(100, speed=_speed(20))
        interpolate_entries(a, b, 0.5)
        assert (a.speed, b.speed) == (_speed(10), _speed(20))


class TestSampleFramemeta:
    def test_exact_sample_is_returned_as_is(self):
        a = _entry(0, speed=_speed(10))
        framemeta = _framemeta((0, a), (100, _entry(100, speed=_speed(20))))
        assert sample_framemeta(framemeta, timeunits(millis=0)) is a

    def test_between_samples_is_interpolated(self):
        framemeta = _framemeta((0, _entry(0, speed=_speed(10))), (100, _entry(100, speed=_speed(20))))
        assert sample_framemeta(framemeta, timeunits(millis=25)).speed == _speed(12.5)

    def test_gap_holds_earlier_sample(self):
        a = _entry(0, speed=_speed(10))
        framemeta = _framemeta((0, a), (5000, _entry(5000, speed=_speed(20))))
        assert sample_framemeta(framemeta, timeunits(millis=2500)) is a

    def test_outside_the_data_uses_framemeta_get(self):
        first = _entry(100, speed=_speed(10))
        last = _entry(200, speed=_speed(20))
        framemeta = _framemeta((100, first), (200, last))
        assert sample_framemeta(framemeta, timeunits(millis=0)) is first
        assert sample_framemeta(framemeta, timeunits(millis=300)) is last


class TestPatchOverlayFps:
    def test_stepper_at_10_fps_matches_stock(self):
        framemeta = _framemeta(*[(ms, _entry(ms)) for ms in range(0, 5001, 50)])
        step = timeunits(seconds=0.1)
        stock = framemeta.stepper(step)
        stock_steps = [t.us for t in stock.steps()]

        patch_overlay_fps(10.0)
        patched = framemeta.stepper(step)
        assert [t.us for t in patched.steps()] == stock_steps
        assert len(patched) == len(stock)

    def test_stepper_steps_at_fps(self):
        patch_overlay_fps(60.0)
        framemeta = _framemeta((0, _entry(0)), (1000, _entry(1000)))
        stepper = framemeta.stepper(timeunits(seconds=0.1))
        steps = [t.us for t in stepper.steps()]
        assert len(steps) == len(stepper) == 61
        assert steps[1] == round(1_000_000 / 60)
        assert steps[-1] == 1_000_000

    def test_stepper_keeps_timelapse_correction(self):
        """gopro-dashboard asks for 0.1 s * correction; a 5x timelapse covers 5x data time per frame."""
        patch_overlay_fps(25.0)
        framemeta = _framemeta((0, _entry(0)), (10_000, _entry(10_000)))
        steps = list(framemeta.stepper(timeunits(seconds=0.1 * 5)).steps())
        assert steps[1].us == 200_000

    def test_stepper_has_no_drift_at_ntsc_rate(self):
        fps = 30000 / 1001
        patch_overlay_fps(fps)
        hour_ms = 3_600_000
        framemeta = _framemeta((0, _entry(0)), (hour_ms, _entry(hour_ms)))
        frames = int(3600 * fps)
        last = next(itertools.islice(framemeta.stepper(timeunits(seconds=0.1)).steps(), frames, None))
        assert abs(last.us - frames * 1_000_000 / fps) <= 1

    def test_overlay_video_input_rate_follows_fps(self):
        patch_overlay_fps(29.97003)
        assert _framerate(_overlay_video_command()) == "29.97003"

    def test_overlay_only_input_rate_follows_fps(self):
        stock = _ffmpeg_command(FFMPEGOverlay)
        patch_overlay_fps(30.0)
        cmd = _ffmpeg_command(FFMPEGOverlay)

        expected = list(stock)
        expected[stock.index("-framerate") + 1] = "30.0"
        assert cmd == expected

    def test_overlay_draw_uses_interpolated_entry(self):
        patch_overlay_fps(60.0)
        framemeta = _framemeta((0, _entry(0, speed=_speed(10))), (100, _entry(100, speed=_speed(20))))
        overlay = Overlay(framemeta, lambda entry: [])
        overlay.scene = Mock()

        result = overlay.draw(timeunits(millis=50), "image")

        assert overlay.entry().speed == _speed(15)
        overlay.scene.draw.assert_called_once_with("image")
        assert result is overlay.scene.draw.return_value

    def test_patch_is_idempotent(self):
        patch_overlay_fps(60.0)
        patch_overlay_fps(30.0)
        assert _framerate(_overlay_video_command()) == "60.0"
