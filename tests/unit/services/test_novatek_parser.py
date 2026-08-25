"""Tests for the Novatek `freeGPS` embedded telemetry parser (issue #27).

Viofo and other Novatek-chipset dashcams do not use GoPro's GPMF metadata
stream, so gopro-overlay reports "Unable to locate metadata stream — is it a
GoPro file". The GPS is present, though: it sits in `freeGPS` blocks inside the
mdat, indexed by a `gps ` box in moov.

Block layout (all multi-byte values little-endian unless noted):

    [0:4]    block size, BIG-endian (the block is itself a `free` atom)
    [4:12]   b"freeGPS "
    [12:16]  payload marker
    [16:40]  hour, minute, second, year (+2000), month, day — one uint32 each
    [40:44]  flags: b"A"/b"V" (fix valid), b"N"/b"S", b"E"/b"W", NUL
    [44:60]  lat, lon (NMEA ddmm.mmmm), speed (knots), bearing (deg) — 4 floats

The byte layout and the expected values below were decoded from the real Viofo
sample attached to issue #27; `tests/fixtures/videos/viofo_freegps_fixture.MP4`
carries those exact blocks.
"""

import struct
from datetime import datetime

import pytest

from tests.fixtures.data import TEST_VIOFO_VIDEO_PATH

BLOCK_SIZE = 16384


def make_block(
    *,
    hour=14,
    minute=48,
    second=33,
    year=26,
    month=8,
    day=17,
    active=b"A",
    ns=b"N",
    ew=b"E",
    lat=3410.3911,
    lon=10854.5264,
    speed_knots=1.89,
    bearing=72.36,
    size=BLOCK_SIZE,
    magic=b"freeGPS ",
):
    """Build one Novatek freeGPS block, mirroring the real byte layout."""
    body = (
        struct.pack(">I", size)
        + magic
        + struct.pack("<7I", 0x2C, hour, minute, second, year, month, day)
        + active
        + ns
        + ew
        + b"\x00"
        + struct.pack("<4f", lat, lon, speed_knots, bearing)
    )
    return body.ljust(size, b"\x00")


def make_mp4(blocks, *, with_index_box=True):
    """Build a minimal MP4 carrying `blocks`, optionally with the `gps ` index box.

    Layout: ftyp | moov (+ optional `gps ` box) | block... — mirroring how a real
    Viofo file indexes absolute block offsets from inside moov.
    """
    ftyp = struct.pack(">I4s", 24, b"ftyp") + b"mp42" + struct.pack(">I", 0) + b"isommp42"
    assert len(ftyp) == 24

    index_size = 16 + 8 * len(blocks) if with_index_box else 0
    moov_size = 8 + index_size
    blocks_start = len(ftyp) + moov_size

    moov = struct.pack(">I4s", moov_size, b"moov")
    if with_index_box:
        moov += struct.pack(">I4sII", index_size, b"gps ", 0x00000101, len(blocks))
        moov += b"".join(struct.pack(">II", blocks_start + i * BLOCK_SIZE, BLOCK_SIZE) for i in range(len(blocks)))

    return ftyp + moov + b"".join(blocks)


@pytest.fixture
def novatek_mp4(tmp_path):
    def _write(blocks, *, with_index_box=True, name="dashcam.MP4"):
        path = tmp_path / name
        path.write_bytes(make_mp4(blocks, with_index_box=with_index_box))
        return path

    return _write


class TestParseBlock:
    """Decoding a single freeGPS block."""

    def test_decodes_the_reference_block(self):
        from gpstitch.services.novatek_parser import parse_novatek_block

        point = parse_novatek_block(make_block())

        assert point is not None
        assert point.timestamp == datetime(2026, 8, 17, 14, 48, 33)
        # NMEA ddmm.mmmm -> decimal degrees: 34deg 10.3911' = 34.173185
        assert point.lat == pytest.approx(34.173185, abs=1e-6)
        assert point.lon == pytest.approx(108.908773, abs=1e-6)
        assert point.bearing_deg == pytest.approx(72.36, abs=1e-2)

    def test_converts_knots_to_metres_per_second(self):
        from gpstitch.services.novatek_parser import parse_novatek_block

        point = parse_novatek_block(make_block(speed_knots=10.0))

        assert point.speed_ms == pytest.approx(10.0 * 1852 / 3600, abs=1e-6)

    def test_southern_and_western_hemispheres_are_negated(self):
        from gpstitch.services.novatek_parser import parse_novatek_block

        point = parse_novatek_block(make_block(ns=b"S", ew=b"W"))

        assert point.lat == pytest.approx(-34.173185, abs=1e-6)
        assert point.lon == pytest.approx(-108.908773, abs=1e-6)

    def test_two_digit_year_is_2000_based(self):
        from gpstitch.services.novatek_parser import parse_novatek_block

        assert parse_novatek_block(make_block(year=5)).timestamp.year == 2005

    def test_void_fix_is_rejected(self):
        """'V' means the GPS had no fix — those rows carry stale coordinates."""
        from gpstitch.services.novatek_parser import parse_novatek_block

        assert parse_novatek_block(make_block(active=b"V")) is None

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"magic": b"notaGPS "},
            {"month": 13},
            {"day": 0},
            {"hour": 24},
            {"minute": 60},
            {"second": 61},
            {"ns": b"X"},
            {"ew": b"X"},
            {"lat": 9999.0},
            {"lon": 99999.0},
        ],
        ids=[
            "bad-magic",
            "month",
            "day",
            "hour",
            "minute",
            "second",
            "ns-flag",
            "ew-flag",
            "lat-range",
            "lon-range",
        ],
    )
    def test_malformed_blocks_are_rejected(self, kwargs):
        """Unknown freeGPS variants must be skipped, never decoded into garbage."""
        from gpstitch.services.novatek_parser import parse_novatek_block

        assert parse_novatek_block(make_block(**kwargs)) is None

    def test_truncated_block_is_rejected(self):
        from gpstitch.services.novatek_parser import parse_novatek_block

        assert parse_novatek_block(make_block()[:32]) is None

    def test_nan_coordinates_are_rejected(self):
        from gpstitch.services.novatek_parser import parse_novatek_block

        assert parse_novatek_block(make_block(lat=float("nan"))) is None


class TestFindBlocks:
    """Locating the blocks: `gps ` index box first, whole-file scan as fallback."""

    def test_uses_the_index_box(self, novatek_mp4):
        from gpstitch.services.novatek_parser import find_novatek_gps_blocks

        path = novatek_mp4([make_block(second=s) for s in (33, 35, 36)])

        assert len(find_novatek_gps_blocks(path)) == 3

    def test_falls_back_to_scanning_when_index_box_is_absent(self, novatek_mp4):
        """Trimmed files and cameras that write no index still carry the blocks."""
        from gpstitch.services.novatek_parser import find_novatek_gps_blocks

        path = novatek_mp4([make_block(second=s) for s in (33, 35, 36)], with_index_box=False)

        assert len(find_novatek_gps_blocks(path)) == 3

    def test_scan_finds_blocks_spanning_a_chunk_boundary(self, tmp_path):
        """The magic must still be found when it straddles two read chunks."""
        from gpstitch.services.novatek_parser import find_novatek_gps_blocks

        path = tmp_path / "big.MP4"
        # Pad with enough filler that the blocks land far from any obvious boundary.
        path.write_bytes(b"\x00" * (1024 * 1024 + 3) + make_block() + b"\x00" * 999)

        assert len(find_novatek_gps_blocks(path)) == 1

    def test_returns_empty_for_a_file_without_gps(self, tmp_path):
        from gpstitch.services.novatek_parser import find_novatek_gps_blocks

        path = tmp_path / "plain.MP4"
        path.write_bytes(b"\x00" * 4096)

        assert find_novatek_gps_blocks(path) == []


class TestParseFile:
    """End-to-end parsing against the real Viofo blocks from issue #27."""

    def test_parses_the_real_fixture(self):
        from gpstitch.services.novatek_parser import parse_novatek_gps_file

        points = parse_novatek_gps_file(TEST_VIOFO_VIDEO_PATH)

        assert len(points) == 7
        assert points[0].timestamp == datetime(2026, 8, 17, 14, 48, 33)
        assert points[-1].timestamp == datetime(2026, 8, 17, 14, 48, 40)
        assert points[0].lat == pytest.approx(34.173185, abs=1e-5)
        assert points[0].lon == pytest.approx(108.908773, abs=1e-5)

    def test_points_are_ordered_by_time(self):
        from gpstitch.services.novatek_parser import parse_novatek_gps_file

        points = parse_novatek_gps_file(TEST_VIOFO_VIDEO_PATH)

        assert [p.timestamp for p in points] == sorted(p.timestamp for p in points)

    def test_void_rows_are_dropped(self, novatek_mp4):
        from gpstitch.services.novatek_parser import parse_novatek_gps_file

        path = novatek_mp4([make_block(second=33), make_block(second=34, active=b"V")])

        assert len(parse_novatek_gps_file(path)) == 1

    def test_file_without_gps_yields_no_points(self, tmp_path):
        from gpstitch.services.novatek_parser import parse_novatek_gps_file

        path = tmp_path / "plain.MP4"
        path.write_bytes(b"\x00" * 4096)

        assert parse_novatek_gps_file(path) == []


class TestDetectAndMetadata:
    """The surface services/metadata.py consumes."""

    def test_detect_reports_the_real_fixture(self):
        from gpstitch.services.novatek_parser import detect_novatek_gps

        assert detect_novatek_gps(TEST_VIOFO_VIDEO_PATH) is True

    def test_detect_is_false_without_gps(self, tmp_path):
        from gpstitch.services.novatek_parser import detect_novatek_gps

        path = tmp_path / "plain.MP4"
        path.write_bytes(b"\x00" * 4096)

        assert detect_novatek_gps(path) is False

    def test_detect_is_false_for_a_gopro_video(self):
        """Must not claim GoPro files — they take the GPMF path."""
        from gpstitch.services.novatek_parser import detect_novatek_gps
        from tests.fixtures.data import TEST_VIDEO_PATH

        assert detect_novatek_gps(TEST_VIDEO_PATH) is False

    def test_metadata_reports_count_and_duration(self):
        from gpstitch.services.novatek_parser import get_novatek_gps_metadata

        meta = get_novatek_gps_metadata(TEST_VIOFO_VIDEO_PATH)

        assert meta["gps_point_count"] == 7
        assert meta["duration_seconds"] == pytest.approx(7.0)

    def test_metadata_is_empty_without_gps(self, tmp_path):
        from gpstitch.services.novatek_parser import get_novatek_gps_metadata

        path = tmp_path / "plain.MP4"
        path.write_bytes(b"\x00" * 4096)

        assert get_novatek_gps_metadata(path) == {}


class TestToTimeseries:
    """Conversion into the gopro_overlay rendering pipeline."""

    def test_builds_a_timeseries_with_position_and_speed(self):
        from gopro_overlay.units import units

        from gpstitch.services.novatek_parser import novatek_to_timeseries, parse_novatek_gps_file

        ts = novatek_to_timeseries(parse_novatek_gps_file(TEST_VIOFO_VIDEO_PATH), units)
        first = ts.get(ts.min)

        assert first.point.lat == pytest.approx(34.173185, abs=1e-5)
        assert first.speed is not None
        assert first.alt is None or first.alt.magnitude == 0

    def test_entries_carry_a_gps_lock_so_journey_accepts_them(self):
        """Journey.accept() skips entries without a fix — see gpx_to_timeseries."""
        from gopro_overlay.gpmf import GPSFix
        from gopro_overlay.units import units

        from gpstitch.services.novatek_parser import novatek_to_timeseries, parse_novatek_gps_file

        ts = novatek_to_timeseries(parse_novatek_gps_file(TEST_VIOFO_VIDEO_PATH), units)
        first = ts.get(ts.min)

        assert first.gpsfix == GPSFix.LOCK_3D.value

    def test_duplicate_seconds_collapse(self):
        """The camera stamps whole seconds and can repeat one; Timeseries keeps
        the last entry for a given timestamp, so 7 raw points give 6 entries."""
        from gopro_overlay.units import units

        from gpstitch.services.novatek_parser import novatek_to_timeseries, parse_novatek_gps_file

        points = parse_novatek_gps_file(TEST_VIOFO_VIDEO_PATH)
        ts = novatek_to_timeseries(points, units)

        assert len(points) == 7
        assert len(ts.items()) == len({p.timestamp for p in points}) == 6

    def test_sample_rate_thins_the_series(self, novatek_mp4):
        from gopro_overlay.units import units

        from gpstitch.services.novatek_parser import novatek_to_timeseries, parse_novatek_gps_file

        path = novatek_mp4([make_block(second=s) for s in range(30, 40)])
        points = parse_novatek_gps_file(path)

        assert len(novatek_to_timeseries(points, units, sample_rate=2).items()) == 5

    def test_load_timeseries_convenience(self):
        from gopro_overlay.units import units

        from gpstitch.services.novatek_parser import load_novatek_timeseries

        assert len(load_novatek_timeseries(TEST_VIOFO_VIDEO_PATH, units).items()) == 6

    def test_load_timeseries_raises_without_gps(self, tmp_path):
        from gopro_overlay.units import units

        from gpstitch.services.novatek_parser import load_novatek_timeseries

        path = tmp_path / "plain.MP4"
        path.write_bytes(b"\x00" * 4096)

        with pytest.raises(ValueError, match="No valid GPS"):
            load_novatek_timeseries(path, units)


class TestToGpxFile:
    """CLI rendering goes through GPX, like the DJI meta path."""

    def test_writes_a_parsable_gpx(self, tmp_path):
        from gopro_overlay.loading import load_external
        from gopro_overlay.units import units

        from gpstitch.services.novatek_parser import novatek_to_gpx_file

        out = novatek_to_gpx_file(TEST_VIOFO_VIDEO_PATH, tmp_path / "track.gpx")
        ts = load_external(out, units)

        assert out.exists()
        assert len(ts.items()) == 6
