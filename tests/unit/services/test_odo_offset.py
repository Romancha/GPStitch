"""Tests for calculate_odo_offset function."""

import datetime
from pathlib import Path

import pytest


def _create_gpx_file(points: list[tuple[float, float, str]], tmp_path: Path) -> Path:
    """Create a GPX file with trackpoints at given (lat, lon, time_iso) positions."""
    trkpts = []
    for lat, lon, time_str in points:
        trkpts.append(f'<trkpt lat="{lat}" lon="{lon}"><time>{time_str}</time></trkpt>')

    gpx_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <trkseg>
      {"".join(trkpts)}
    </trkseg>
  </trk>
</gpx>"""

    gpx_path = tmp_path / "test_track.gpx"
    gpx_path.write_text(gpx_content, encoding="utf-8")
    return gpx_path


@pytest.fixture
def gpx_track(tmp_path):
    """Create a GPX track with known distances.

    Track: 4 points along a roughly north-south line, each ~111m apart (0.001 degrees lat).
    Times: 2024-07-01 10:00:00 to 10:00:03 UTC, 1 second apart.
    """
    points = [
        (47.0000, 8.0000, "2024-07-01T10:00:00Z"),
        (47.0010, 8.0000, "2024-07-01T10:00:01Z"),
        (47.0020, 8.0000, "2024-07-01T10:00:02Z"),
        (47.0030, 8.0000, "2024-07-01T10:00:03Z"),
    ]
    return _create_gpx_file(points, tmp_path)


class TestCalculateOdoOffset:
    """Tests for calculate_odo_offset function."""

    def test_beginning_of_track(self, gpx_track):
        """Video starting at or before track start should have 0 offset."""
        from gpstitch.services.renderer import calculate_odo_offset

        start = datetime.datetime(2024, 7, 1, 10, 0, 0, tzinfo=datetime.UTC)
        offset = calculate_odo_offset(gpx_track, start)
        assert offset == 0.0

    def test_before_track_start(self, gpx_track):
        """Video starting before track should have 0 offset."""
        from gpstitch.services.renderer import calculate_odo_offset

        start = datetime.datetime(2024, 7, 1, 9, 0, 0, tzinfo=datetime.UTC)
        offset = calculate_odo_offset(gpx_track, start)
        assert offset == 0.0

    def test_middle_of_track(self, gpx_track):
        """Video starting in the middle should have positive offset."""
        from gpstitch.services.renderer import calculate_odo_offset

        # At the second point (10:00:01)
        start = datetime.datetime(2024, 7, 1, 10, 0, 1, tzinfo=datetime.UTC)
        offset = calculate_odo_offset(gpx_track, start)
        # At the second point, codo is approximately 222 meters (2 segments of ~111m)
        assert offset > 180.0
        assert offset < 270.0

    def test_end_of_track(self, gpx_track):
        """Video starting at end of track should have full track distance."""
        from gpstitch.services.renderer import calculate_odo_offset

        start = datetime.datetime(2024, 7, 1, 10, 0, 3, tzinfo=datetime.UTC)
        offset = calculate_odo_offset(gpx_track, start)
        # Should be approximately 333 meters (3 x 111m)
        assert offset > 250.0
        assert offset < 400.0

    def test_after_track_end(self, gpx_track):
        """Video starting after track end should get the full track distance."""
        from gpstitch.services.renderer import calculate_odo_offset

        start = datetime.datetime(2024, 7, 1, 12, 0, 0, tzinfo=datetime.UTC)
        offset = calculate_odo_offset(gpx_track, start)
        # Should equal the total track distance (~333m)
        assert offset > 250.0
        assert offset < 400.0

    def test_offset_increases_over_time(self, gpx_track):
        """Offset should increase monotonically with later start times."""
        from gpstitch.services.renderer import calculate_odo_offset

        t0 = datetime.datetime(2024, 7, 1, 10, 0, 0, tzinfo=datetime.UTC)
        t1 = datetime.datetime(2024, 7, 1, 10, 0, 1, tzinfo=datetime.UTC)
        t2 = datetime.datetime(2024, 7, 1, 10, 0, 2, tzinfo=datetime.UTC)

        o0 = calculate_odo_offset(gpx_track, t0)
        o1 = calculate_odo_offset(gpx_track, t1)
        o2 = calculate_odo_offset(gpx_track, t2)

        assert o0 <= o1 <= o2
        assert o2 > o0  # Some actual distance was covered

    def test_empty_gpx(self, tmp_path):
        """Empty GPX should return 0."""
        from gpstitch.services.renderer import calculate_odo_offset

        gpx_content = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg></trkseg></trk>
</gpx>"""
        gpx_path = tmp_path / "empty.gpx"
        gpx_path.write_text(gpx_content, encoding="utf-8")

        start = datetime.datetime(2024, 7, 1, 10, 0, 0, tzinfo=datetime.UTC)
        offset = calculate_odo_offset(gpx_path, start)
        assert offset == 0.0

    def test_timezone_naive_video_time(self, gpx_track):
        """Function should handle timezone-naive video start times."""
        from gpstitch.services.renderer import calculate_odo_offset

        # Naive datetime (no tzinfo)
        start = datetime.datetime(2024, 7, 1, 10, 0, 1)
        offset = calculate_odo_offset(gpx_track, start)
        # Should still work and return a positive value
        assert offset >= 0.0


class TestRenderJobConfigOdoOffset:
    """Tests for odo_offset field in RenderJobConfig."""

    def test_default_none(self):
        from gpstitch.models.job import RenderJobConfig

        config = RenderJobConfig(session_id="test", layout="default", output_file="/tmp/out.mp4")
        assert config.odo_offset is None

    def test_set_value(self):
        from gpstitch.models.job import RenderJobConfig

        config = RenderJobConfig(
            session_id="test", layout="default", output_file="/tmp/out.mp4", odo_offset=1234.5
        )
        assert config.odo_offset == 1234.5

    def test_zero_value(self):
        from gpstitch.models.job import RenderJobConfig

        config = RenderJobConfig(
            session_id="test", layout="default", output_file="/tmp/out.mp4", odo_offset=0.0
        )
        assert config.odo_offset == 0.0

    def test_serialization(self):
        from gpstitch.models.job import RenderJobConfig

        config = RenderJobConfig(
            session_id="test", layout="default", output_file="/tmp/out.mp4", odo_offset=5678.9
        )
        data = config.model_dump()
        assert data["odo_offset"] == 5678.9

        # Deserialize
        config2 = RenderJobConfig.model_validate(data)
        assert config2.odo_offset == 5678.9
