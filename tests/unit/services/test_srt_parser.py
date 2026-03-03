"""Tests for DJI SRT parser."""

import os
from datetime import UTC, datetime, timedelta

import pytest

from gpstitch.services.srt_parser import (
    _parse_shutter,
    estimate_tz_offset,
    get_srt_metadata,
    parse_srt,
    srt_to_gpx_file,
)

SAMPLE_SRT = """\
1
00:00:00,000 --> 00:00:00,033
<font size="28">FrameCnt: 1, DiffTime: 33ms
2024-08-07 12:34:24.380
[iso: 100] [shutter: 1/3200.0] [fnum: 1.7] [ev: 0] [color_md: default] [focal_len: 24.00] [latitude: 69.189116] [longitude: 35.259334] [rel_alt: 1.100 abs_alt: -2.927] [ct: 5310] </font>

2
00:00:00,033 --> 00:00:00,066
<font size="28">FrameCnt: 2, DiffTime: 33ms
2024-08-07 12:34:24.414
[iso: 100] [shutter: 1/3200.0] [fnum: 1.7] [ev: 0] [color_md: default] [focal_len: 24.00] [latitude: 69.189116] [longitude: 35.259334] [rel_alt: 1.100 abs_alt: -2.927] [ct: 5310] </font>

3
00:00:00,066 --> 00:00:00,099
<font size="28">FrameCnt: 3, DiffTime: 33ms
2024-08-07 12:34:24.448
[iso: 100] [shutter: 1/3200.0] [fnum: 1.7] [ev: 0] [color_md: default] [focal_len: 24.00] [latitude: 69.189200] [longitude: 35.259400] [rel_alt: 5.500 abs_alt: 1.573] [ct: 5310] </font>
"""


@pytest.fixture
def srt_file(tmp_path):
    """Create a sample SRT file for testing."""
    path = tmp_path / "test.srt"
    path.write_text(SAMPLE_SRT, encoding="utf-8")
    return path


class TestParseSrt:
    def test_parses_all_points(self, srt_file):
        points = parse_srt(srt_file)
        assert len(points) == 3

    def test_extracts_coordinates(self, srt_file):
        points = parse_srt(srt_file)
        assert points[0].lat == pytest.approx(69.189116)
        assert points[0].lon == pytest.approx(35.259334)

    def test_extracts_datetime(self, srt_file):
        points = parse_srt(srt_file)
        expected = datetime(2024, 8, 7, 12, 34, 24, 380000)
        assert points[0].dt == expected
        assert points[0].dt.tzinfo is None

    def test_extracts_altitude(self, srt_file):
        points = parse_srt(srt_file)
        assert points[0].rel_alt == pytest.approx(1.1)
        assert points[0].abs_alt == pytest.approx(-2.927)

    def test_different_coordinates_per_point(self, srt_file):
        points = parse_srt(srt_file)
        # Third point has different coordinates
        assert points[2].lat == pytest.approx(69.189200)
        assert points[2].lon == pytest.approx(35.259400)
        assert points[2].rel_alt == pytest.approx(5.5)

    def test_skips_zero_coordinates(self, tmp_path):
        srt_content = """\
1
00:00:00,000 --> 00:00:00,033
<font size="28">FrameCnt: 1, DiffTime: 33ms
2024-08-07 12:34:24.380
[latitude: 0.000000] [longitude: 0.000000] [rel_alt: 0.000 abs_alt: 0.000] </font>

2
00:00:00,033 --> 00:00:00,066
<font size="28">FrameCnt: 2, DiffTime: 33ms
2024-08-07 12:34:24.414
[latitude: 69.189116] [longitude: 35.259334] [rel_alt: 1.100 abs_alt: -2.927] </font>
"""
        path = tmp_path / "zero.srt"
        path.write_text(srt_content, encoding="utf-8")
        points = parse_srt(path)
        assert len(points) == 1
        assert points[0].lat == pytest.approx(69.189116)

    def test_empty_file(self, tmp_path):
        path = tmp_path / "empty.srt"
        path.write_text("", encoding="utf-8")
        points = parse_srt(path)
        assert len(points) == 0

    def test_extracts_camera_metrics(self, srt_file):
        points = parse_srt(srt_file)
        p = points[0]
        assert p.iso == 100
        assert p.shutter == pytest.approx(1.0 / 3200.0)
        assert p.fnum == pytest.approx(1.7)
        assert p.ev == pytest.approx(0.0)
        assert p.focal_len == pytest.approx(24.0)
        assert p.ct == 5310

    def test_camera_metrics_none_when_absent(self, tmp_path):
        srt_content = """\
1
00:00:00,000 --> 00:00:00,033
<font size="28">FrameCnt: 1, DiffTime: 33ms
2024-08-07 12:34:24.380
[latitude: 69.189116] [longitude: 35.259334] [rel_alt: 1.100 abs_alt: -2.927] </font>
"""
        path = tmp_path / "no_cam.srt"
        path.write_text(srt_content, encoding="utf-8")
        points = parse_srt(path)
        assert len(points) == 1
        p = points[0]
        assert p.iso is None
        assert p.shutter is None
        assert p.fnum is None
        assert p.ev is None
        assert p.focal_len is None
        assert p.ct is None

    def test_malformed_blocks_skipped(self, tmp_path):
        srt_content = """\
1
00:00:00,000 --> 00:00:00,033
no valid data here

2
00:00:00,033 --> 00:00:00,066
<font size="28">FrameCnt: 2, DiffTime: 33ms
2024-08-07 12:34:24.414
[latitude: 69.189116] [longitude: 35.259334] [rel_alt: 1.100 abs_alt: -2.927] </font>
"""
        path = tmp_path / "malformed.srt"
        path.write_text(srt_content, encoding="utf-8")
        points = parse_srt(path)
        assert len(points) == 1


class TestGetSrtMetadata:
    def test_returns_point_count_and_duration(self, srt_file):
        meta = get_srt_metadata(srt_file)
        assert meta["gps_point_count"] == 3
        assert meta["duration_seconds"] is not None
        assert meta["duration_seconds"] > 0

    def test_empty_file_returns_zero(self, tmp_path):
        path = tmp_path / "empty.srt"
        path.write_text("", encoding="utf-8")
        meta = get_srt_metadata(path)
        assert meta["gps_point_count"] == 0
        assert meta["duration_seconds"] is None


class TestSrtToGpxFile:
    def test_creates_gpx_file(self, srt_file, tmp_path):
        output = tmp_path / "output.gpx"
        result = srt_to_gpx_file(srt_file, output)
        assert result == output
        assert output.exists()

    def test_gpx_contains_trackpoints(self, srt_file, tmp_path):
        output = tmp_path / "output.gpx"
        srt_to_gpx_file(srt_file, output)
        content = output.read_text()
        assert "<trkpt" in content
        assert "69.189116" in content
        assert "35.259334" in content

    def test_gpx_with_sampling(self, srt_file, tmp_path):
        output = tmp_path / "output.gpx"
        srt_to_gpx_file(srt_file, output, sample_rate=2)
        content = output.read_text()
        # With 3 points and sample_rate=2, should get points at index 0 and 2
        assert content.count("<trkpt") == 2

    def test_empty_srt_raises(self, tmp_path):
        srt = tmp_path / "empty.srt"
        srt.write_text("", encoding="utf-8")
        output = tmp_path / "output.gpx"
        with pytest.raises(ValueError, match="No valid GPS data"):
            srt_to_gpx_file(srt, output)

    def test_gpx_with_tz_offset(self, srt_file, tmp_path):
        output = tmp_path / "output.gpx"
        srt_to_gpx_file(srt_file, output, tz_offset=timedelta(hours=3))
        content = output.read_text()
        # Original time: 2024-08-07T12:34:24 → corrected: 2024-08-07T09:34:24
        assert "2024-08-07T09:34:24" in content
        assert "2024-08-07T12:34:24" not in content


class TestEstimateTzOffset:
    """Test timezone offset estimation for various timezones."""

    def _make_srt_and_video(self, tmp_path, srt_last_local_str, video_mtime_utc):
        """Helper: create SRT file with given last timestamp and video file with given mtime."""
        srt_content = f"""\
1
00:00:00,000 --> 00:00:00,033
<font size="28">FrameCnt: 1, DiffTime: 33ms
{srt_last_local_str}
[latitude: 50.0] [longitude: 87.0] [rel_alt: 100.0 abs_alt: 500.0] </font>
"""
        srt_path = tmp_path / "test.srt"
        srt_path.write_text(srt_content, encoding="utf-8")

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake")
        os.utime(video_path, (video_mtime_utc.timestamp(), video_mtime_utc.timestamp()))

        return srt_path, video_path

    def test_utc_plus_3(self, tmp_path):
        """UTC+3 (Moscow, Altai) — SRT local is 3 hours ahead of UTC."""
        srt_path, video_path = self._make_srt_and_video(
            tmp_path,
            "2025-07-28 05:12:24.000",
            datetime(2025, 7, 28, 2, 12, 24, tzinfo=UTC),
        )
        offset, _ = estimate_tz_offset(srt_path, video_path)
        assert offset == timedelta(hours=3)

    def test_utc_plus_0(self, tmp_path):
        """UTC+0 (London, Reykjavik) — no offset."""
        srt_path, video_path = self._make_srt_and_video(
            tmp_path,
            "2025-07-28 12:00:00.000",
            datetime(2025, 7, 28, 12, 0, 0, tzinfo=UTC),
        )
        offset, _ = estimate_tz_offset(srt_path, video_path)
        assert offset == timedelta(0)

    def test_utc_minus_5(self, tmp_path):
        """UTC-5 (New York EST) — SRT local is 5 hours behind UTC."""
        srt_path, video_path = self._make_srt_and_video(
            tmp_path,
            "2025-07-28 07:00:00.000",
            datetime(2025, 7, 28, 12, 0, 0, tzinfo=UTC),
        )
        offset, _ = estimate_tz_offset(srt_path, video_path)
        assert offset == timedelta(hours=-5)

    def test_utc_minus_8(self, tmp_path):
        """UTC-8 (Los Angeles PST) — SRT local is 8 hours behind UTC."""
        srt_path, video_path = self._make_srt_and_video(
            tmp_path,
            "2025-07-28 04:00:00.000",
            datetime(2025, 7, 28, 12, 0, 0, tzinfo=UTC),
        )
        offset, _ = estimate_tz_offset(srt_path, video_path)
        assert offset == timedelta(hours=-8)

    def test_utc_plus_5_30(self, tmp_path):
        """UTC+5:30 (India) — half-hour offset."""
        srt_path, video_path = self._make_srt_and_video(
            tmp_path,
            "2025-07-28 17:30:00.000",
            datetime(2025, 7, 28, 12, 0, 0, tzinfo=UTC),
        )
        offset, _ = estimate_tz_offset(srt_path, video_path)
        assert offset == timedelta(hours=5, minutes=30)

    def test_utc_plus_5_45(self, tmp_path):
        """UTC+5:45 (Nepal) — quarter-hour offset."""
        srt_path, video_path = self._make_srt_and_video(
            tmp_path,
            "2025-07-28 17:45:00.000",
            datetime(2025, 7, 28, 12, 0, 0, tzinfo=UTC),
        )
        offset, _ = estimate_tz_offset(srt_path, video_path)
        assert offset == timedelta(hours=5, minutes=45)

    def test_utc_plus_3_30(self, tmp_path):
        """UTC+3:30 (Iran) — half-hour offset."""
        srt_path, video_path = self._make_srt_and_video(
            tmp_path,
            "2025-07-28 15:30:00.000",
            datetime(2025, 7, 28, 12, 0, 0, tzinfo=UTC),
        )
        offset, _ = estimate_tz_offset(srt_path, video_path)
        assert offset == timedelta(hours=3, minutes=30)

    def test_utc_plus_12(self, tmp_path):
        """UTC+12 (New Zealand) — large positive offset."""
        srt_path, video_path = self._make_srt_and_video(
            tmp_path,
            "2025-07-29 00:00:00.000",
            datetime(2025, 7, 28, 12, 0, 0, tzinfo=UTC),
        )
        offset, _ = estimate_tz_offset(srt_path, video_path)
        assert offset == timedelta(hours=12)

    def test_utc_minus_12(self, tmp_path):
        """UTC-12 (Baker Island) — large negative offset."""
        srt_path, video_path = self._make_srt_and_video(
            tmp_path,
            "2025-07-28 00:00:00.000",
            datetime(2025, 7, 28, 12, 0, 0, tzinfo=UTC),
        )
        offset, _ = estimate_tz_offset(srt_path, video_path)
        assert offset == timedelta(hours=-12)

    def test_small_subsecond_noise_ignored(self, tmp_path):
        """Small sub-second differences between SRT and mtime should not affect offset."""
        srt_path, video_path = self._make_srt_and_video(
            tmp_path,
            "2025-07-28 15:00:00.500",
            datetime(2025, 7, 28, 12, 0, 1, tzinfo=UTC),
        )
        offset, _ = estimate_tz_offset(srt_path, video_path)
        assert offset == timedelta(hours=3)

    def test_empty_srt_returns_none(self, tmp_path):
        """Empty SRT should return None (offset cannot be determined)."""
        srt_path = tmp_path / "empty.srt"
        srt_path.write_text("", encoding="utf-8")
        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake")
        offset, _ = estimate_tz_offset(srt_path, video_path)
        assert offset is None


class TestParseShutter:
    def test_fraction(self):
        assert _parse_shutter("1/3200.0") == pytest.approx(1.0 / 3200.0)

    def test_simple_float(self):
        assert _parse_shutter("0.5") == pytest.approx(0.5)

    def test_fraction_integer_denominator(self):
        assert _parse_shutter("1/100") == pytest.approx(0.01)


class TestTimeseriesCameraMetrics:
    def test_entries_have_camera_metrics(self, srt_file):
        from gopro_overlay.units import units

        from gpstitch.services.srt_parser import srt_to_timeseries

        points = parse_srt(srt_file)
        ts = srt_to_timeseries(points, units)
        # Get first entry by datetime key
        entry = ts.entries[points[0].dt]
        assert entry.iso is not None
        assert entry.iso.magnitude == 100
        assert entry.fnum is not None
        assert entry.fnum.magnitude == pytest.approx(1.7)
        assert entry.shutter is not None
        assert entry.shutter.magnitude == pytest.approx(1.0 / 3200.0)
        assert entry.ct is not None
        assert entry.ct.magnitude == 5310

    def test_entries_without_camera_metrics(self, tmp_path):
        from gopro_overlay.units import units

        from gpstitch.services.srt_parser import srt_to_timeseries

        srt_content = """\
1
00:00:00,000 --> 00:00:00,033
<font size="28">FrameCnt: 1, DiffTime: 33ms
2024-08-07 12:34:24.380
[latitude: 69.189116] [longitude: 35.259334] [rel_alt: 1.100 abs_alt: -2.927] </font>
"""
        path = tmp_path / "no_cam.srt"
        path.write_text(srt_content, encoding="utf-8")
        points = parse_srt(path)
        ts = srt_to_timeseries(points, units)
        entry = ts.entries[points[0].dt]
        # Camera metrics should be None (not in Entry.items)
        assert entry.iso is None
        assert entry.fnum is None
