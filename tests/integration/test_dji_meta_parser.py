"""Integration tests for DJI meta protobuf parser with real fixture MP4."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from gpstitch.services.dji_meta_parser import (
    detect_dji_meta_stream,
    dji_meta_to_gpx_file,
    get_dji_meta_metadata,
    load_dji_meta_timeseries,
    parse_dji_meta_file,
)
from tests.fixtures.data import TEST_DJI_ACTION_VIDEO_PATH, TEST_VIDEO_PATH


@pytest.fixture(scope="module")
def dji_action_video():
    """Real DJI Action test video fixture."""
    path = Path(TEST_DJI_ACTION_VIDEO_PATH)
    if not path.exists():
        pytest.skip(f"DJI Action fixture not found: {path}")
    return path


@pytest.fixture(scope="module")
def gopro_video():
    """Regular GoPro video (no DJI meta stream)."""
    path = Path(TEST_VIDEO_PATH)
    if not path.exists():
        pytest.skip(f"GoPro fixture not found: {path}")
    return path


class TestDetectDjiMetaStreamIntegration:
    """Test stream detection with real video files."""

    def test_detect_dji_action_fixture(self, dji_action_video):
        """Should detect DJI meta stream in DJI Action fixture MP4."""
        stream_idx = detect_dji_meta_stream(dji_action_video)
        assert stream_idx is not None
        assert stream_idx == 2  # Known stream index in fixture

    def test_no_dji_meta_in_gopro(self, gopro_video):
        """Should return None for regular GoPro video."""
        stream_idx = detect_dji_meta_stream(gopro_video)
        assert stream_idx is None


class TestParseDjiMetaFileIntegration:
    """Test full parse pipeline with real fixture."""

    def test_parse_fixture_returns_points(self, dji_action_video):
        """Should parse GPS points from DJI Action fixture."""
        points = parse_dji_meta_file(dji_action_video)
        assert len(points) > 0
        # Fixture has 125 frames at 25fps, all with GPS data
        assert len(points) == 125

    def test_parse_fixture_gps_values(self, dji_action_video):
        """Verify GPS coordinates are in expected range (Cologne area)."""
        points = parse_dji_meta_file(dji_action_video)

        first = points[0]
        assert first.lat == pytest.approx(50.8907650, abs=1e-4)
        assert first.lon == pytest.approx(6.6743936, abs=1e-4)
        assert first.alt_m == pytest.approx(122.745, abs=1.0)

        last = points[-1]
        assert last.lat == pytest.approx(50.8903126, abs=1e-4)
        assert last.lon == pytest.approx(6.6745551, abs=1e-4)

    def test_parse_fixture_timestamps(self, dji_action_video):
        """Verify timestamps span the expected duration."""
        points = parse_dji_meta_file(dji_action_video)

        first_ts = points[0].timestamp
        last_ts = points[-1].timestamp
        duration = (last_ts - first_ts).total_seconds()
        # 125 frames at 25fps = 5 seconds, timestamps have 1-second resolution
        assert 4.0 <= duration <= 6.0

    def test_parse_fixture_velocity(self, dji_action_video):
        """Verify velocity data is present and reasonable."""
        points = parse_dji_meta_file(dji_action_video)

        # Check first point velocity
        vx, vy = points[0].velocity_2d
        assert abs(vx) < 100  # reasonable m/s range
        assert abs(vy) < 100

    def test_parse_regular_mp4_raises(self, gopro_video):
        """Should raise ValueError for video without DJI meta stream."""
        with pytest.raises(ValueError, match="No DJI meta stream"):
            parse_dji_meta_file(gopro_video)


class TestGetDjiMetaMetadataIntegration:
    """Test metadata extraction with real fixture."""

    def test_metadata_from_fixture(self, dji_action_video):
        """Should return correct metadata from DJI Action fixture."""
        meta = get_dji_meta_metadata(dji_action_video)

        assert meta["gps_point_count"] == 125
        assert meta["device_name"] == "DJI AC004"
        assert meta["sample_rate_hz"] == pytest.approx(25.0)
        assert meta["duration_seconds"] is not None
        assert 4.0 <= meta["duration_seconds"] <= 6.0

    def test_metadata_from_gopro(self, gopro_video):
        """Should return empty dict for video without DJI meta."""
        meta = get_dji_meta_metadata(gopro_video)
        assert meta == {}


class TestLoadDjiMetaTimeseriesIntegration:
    """Test timeseries loading from real fixture."""

    def test_load_timeseries_full_rate(self, dji_action_video):
        """Should load GPS points as timeseries entries (deduped by timestamp)."""
        from gopro_overlay.units import units

        ts = load_dji_meta_timeseries(dji_action_video, units)
        # 125 frames at 25fps with 1-second timestamp resolution -> ~6 unique timestamps
        # Timeseries deduplicates by timestamp (dict keyed by datetime)
        assert len(ts) >= 5

    def test_load_timeseries_thinned(self, dji_action_video):
        """Should thin data with sample_rate (25fps -> ~1Hz)."""
        from gopro_overlay.units import units

        ts = load_dji_meta_timeseries(dji_action_video, units, sample_rate=25)
        assert len(ts) == 5  # 125 / 25 = 5

    def test_timeseries_has_speed(self, dji_action_video):
        """Entries should have speed calculated from velocity."""
        from gopro_overlay.units import units

        ts = load_dji_meta_timeseries(dji_action_video, units)
        entry = ts.items()[0]
        assert hasattr(entry, "speed")
        assert entry.speed.magnitude >= 0.0

    def test_timeseries_has_gps_coordinates(self, dji_action_video):
        """Entries should have correct GPS coordinates."""
        from gopro_overlay.units import units

        ts = load_dji_meta_timeseries(dji_action_video, units)
        entry = ts.items()[0]
        assert entry.point.lat == pytest.approx(50.8907650, abs=1e-4)
        assert entry.point.lon == pytest.approx(6.6743936, abs=1e-4)


class TestDjiMetaToGpxFileIntegration:
    """Test GPX export with real fixture."""

    def test_gpx_from_fixture(self, dji_action_video, tmp_path):
        """Should produce valid GPX from DJI Action fixture."""
        output = tmp_path / "dji_action.gpx"
        result = dji_meta_to_gpx_file(dji_action_video, output)
        assert result == output
        assert output.exists()

        # Parse and validate GPX structure
        tree = ET.parse(str(output))
        root = tree.getroot()
        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        trkpts = root.findall(".//gpx:trkpt", ns)
        assert len(trkpts) == 125

    def test_gpx_coordinates_match_parsed(self, dji_action_video, tmp_path):
        """GPX coordinates should match parsed DjiMetaPoint values."""
        output = tmp_path / "dji_action.gpx"
        dji_meta_to_gpx_file(dji_action_video, output)

        tree = ET.parse(str(output))
        root = tree.getroot()
        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        first_trkpt = root.find(".//gpx:trkpt", ns)
        assert float(first_trkpt.get("lat")) == pytest.approx(50.890765, abs=1e-4)
        assert float(first_trkpt.get("lon")) == pytest.approx(6.674394, abs=1e-4)

        ele = first_trkpt.find("gpx:ele", ns)
        assert ele is not None
        assert float(ele.text) == pytest.approx(122.7, abs=1.0)

        time_el = first_trkpt.find("gpx:time", ns)
        assert time_el is not None
        assert "2026-03-15" in time_el.text

    def test_gpx_with_thinning(self, dji_action_video, tmp_path):
        """Should thin GPX output with sample_rate."""
        output = tmp_path / "dji_action_thinned.gpx"
        dji_meta_to_gpx_file(dji_action_video, output, sample_rate=25)

        tree = ET.parse(str(output))
        root = tree.getroot()
        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        trkpts = root.findall(".//gpx:trkpt", ns)
        assert len(trkpts) == 5  # 125 / 25 = 5
