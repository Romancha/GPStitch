"""Tests for DJI meta GPS patch — load protobuf GPS instead of intermediate GPX."""

from pathlib import Path
from unittest.mock import patch

import pytest

from gpstitch.services.dji_meta_parser import DjiMetaPoint


def _make_dji_points(count=3):
    """Create sample DjiMetaPoint list for testing."""
    from datetime import datetime, timedelta

    base_time = datetime(2026, 3, 15, 23, 54, 17)
    return [
        DjiMetaPoint(
            frame_idx=i,
            timestamp=base_time + timedelta(seconds=i),
            lat=55.7558 + i * 0.0001,
            lon=37.6173 + i * 0.0001,
            alt_m=150.0 + i,
            velocity_2d=(1.0 + i * 0.1, 0.5 + i * 0.1),
        )
        for i in range(count)
    ]


@pytest.fixture(autouse=True)
def _reset_loading_module():
    """Save and restore load_external after each test."""
    import gopro_overlay.loading as loading_module

    original_fn = loading_module.load_external
    yield
    loading_module.load_external = original_fn
    if hasattr(loading_module, "_ts_dji_meta_patched"):
        delattr(loading_module, "_ts_dji_meta_patched")


class TestPatchDjiMetaLoad:
    def test_patch_replaces_load_external(self):
        import gopro_overlay.loading as loading_module

        original = loading_module.load_external
        points = _make_dji_points(5)

        with patch("gpstitch.services.dji_meta_parser.parse_dji_meta_file", return_value=points):
            from gpstitch.patches.gpx_patches import patch_dji_meta_load

            patch_dji_meta_load("/fake/video.mp4")

        assert loading_module.load_external is not original
        assert loading_module._ts_dji_meta_patched is True

    def test_patched_load_returns_timeseries_with_gps(self):
        points = _make_dji_points(5)

        with patch("gpstitch.services.dji_meta_parser.parse_dji_meta_file", return_value=points):
            from gpstitch.patches.gpx_patches import patch_dji_meta_load

            patch_dji_meta_load("/fake/video.mp4")

        import gopro_overlay.loading as loading_module
        from gopro_overlay.units import units

        ts = loading_module.load_external(Path("/nonexistent/dummy.gpx"), units)

        # Should have entries
        assert ts.min is not None
        assert ts.max is not None

        # Check GPS data on entry
        entry = ts.get(ts.min)
        assert entry.point is not None
        assert entry.alt is not None
        assert entry.speed is not None

    def test_patched_load_ignores_gpx_filepath(self):
        points = _make_dji_points(3)

        with patch("gpstitch.services.dji_meta_parser.parse_dji_meta_file", return_value=points):
            from gpstitch.patches.gpx_patches import patch_dji_meta_load

            patch_dji_meta_load("/fake/video.mp4")

        import gopro_overlay.loading as loading_module
        from gopro_overlay.units import units

        # Should not raise FileNotFoundError — GPX path is ignored
        ts = loading_module.load_external(Path("/nonexistent/file.gpx"), units)
        assert ts is not None

    def test_patch_is_idempotent(self):
        points = _make_dji_points(3)

        with patch("gpstitch.services.dji_meta_parser.parse_dji_meta_file", return_value=points):
            from gpstitch.patches.gpx_patches import patch_dji_meta_load

            patch_dji_meta_load("/fake/video.mp4")
            patch_dji_meta_load("/fake/video.mp4")

        import gopro_overlay.loading as loading_module
        from gopro_overlay.units import units

        ts = loading_module.load_external(Path("/dummy.gpx"), units)
        assert ts is not None

    def test_patch_raises_on_no_gps_data(self):
        with patch("gpstitch.services.dji_meta_parser.parse_dji_meta_file", return_value=[]):
            from gpstitch.patches.gpx_patches import patch_dji_meta_load

            with pytest.raises(ValueError, match="No valid GPS data"):
                patch_dji_meta_load("/fake/video.mp4")

    def test_patched_timeseries_has_correct_point_count(self):
        """With sample_rate=1 and few points, all should be in timeseries."""
        points = _make_dji_points(5)

        with (
            patch("gpstitch.services.dji_meta_parser.parse_dji_meta_file", return_value=points),
            patch("gpstitch.services.srt_parser.calc_sample_rate", return_value=1),
        ):
            from gpstitch.patches.gpx_patches import patch_dji_meta_load

            patch_dji_meta_load("/fake/video.mp4")

        import gopro_overlay.loading as loading_module
        from gopro_overlay.units import units

        ts = loading_module.load_external(Path("/dummy.gpx"), units)

        # Verify timeseries spans expected duration
        duration = (ts.max - ts.min).total_seconds()
        assert duration == pytest.approx(4.0, abs=1.0)  # 5 points, 1 second apart
