"""Tests for gpx_patches — SRT camera metrics in video render."""

from pathlib import Path

import pytest

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
[iso: 200] [shutter: 1/1600.0] [fnum: 2.8] [ev: -1] [color_md: default] [focal_len: 24.00] [latitude: 69.189200] [longitude: 35.259400] [rel_alt: 5.500 abs_alt: 1.573] [ct: 5500] </font>

3
00:00:00,066 --> 00:00:00,099
<font size="28">FrameCnt: 3, DiffTime: 33ms
2024-08-07 12:34:24.448
[iso: 300] [shutter: 1/800.0] [fnum: 2.8] [ev: 0] [color_md: default] [focal_len: 24.00] [latitude: 69.189300] [longitude: 35.259500] [rel_alt: 10.000 abs_alt: 6.073] [ct: 5600] </font>
"""


@pytest.fixture
def srt_file(tmp_path):
    path = tmp_path / "test.srt"
    path.write_text(SAMPLE_SRT, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _reset_loading_module():
    """Save and restore load_external after each test."""
    import gopro_overlay.loading as loading_module

    original_fn = loading_module.load_external
    yield
    loading_module.load_external = original_fn
    if hasattr(loading_module, "_ts_srt_patched"):
        delattr(loading_module, "_ts_srt_patched")


class TestPatchGpxLoadForSrt:
    def test_patch_replaces_load_external(self, srt_file):
        import gopro_overlay.loading as loading_module

        original = loading_module.load_external

        from gpstitch.patches.gpx_patches import patch_gpx_load_for_srt

        patch_gpx_load_for_srt(str(srt_file))

        assert loading_module.load_external is not original
        assert loading_module._ts_srt_patched is True

    def test_patched_load_returns_timeseries_with_camera_metrics(self, srt_file):
        from gpstitch.patches.gpx_patches import patch_gpx_load_for_srt

        patch_gpx_load_for_srt(str(srt_file))

        import gopro_overlay.loading as loading_module
        from gopro_overlay.units import units

        ts = loading_module.load_external(Path("/nonexistent/dummy.gpx"), units)

        # Should have entries
        assert ts.min is not None
        assert ts.max is not None

        # Check camera metrics are present on the first entry
        entry = ts.get(ts.min)
        assert entry.iso is not None
        assert entry.fnum is not None
        assert entry.ev is not None
        assert entry.ct is not None

    def test_patched_load_ignores_gpx_filepath(self, srt_file):
        from gpstitch.patches.gpx_patches import patch_gpx_load_for_srt

        patch_gpx_load_for_srt(str(srt_file))

        import gopro_overlay.loading as loading_module
        from gopro_overlay.units import units

        # Should not raise FileNotFoundError — GPX path is ignored
        ts = loading_module.load_external(Path("/nonexistent/file.gpx"), units)
        assert ts is not None

    def test_patch_is_idempotent(self, srt_file):
        from gpstitch.patches.gpx_patches import patch_gpx_load_for_srt

        patch_gpx_load_for_srt(str(srt_file))
        patch_gpx_load_for_srt(str(srt_file))

        import gopro_overlay.loading as loading_module
        from gopro_overlay.units import units

        ts = loading_module.load_external(Path("/dummy.gpx"), units)
        assert ts is not None

    def test_patch_raises_on_empty_srt(self, tmp_path):
        empty_srt = tmp_path / "empty.srt"
        empty_srt.write_text("", encoding="utf-8")

        from gpstitch.patches.gpx_patches import patch_gpx_load_for_srt

        with pytest.raises(ValueError, match="No valid GPS data"):
            patch_gpx_load_for_srt(str(empty_srt))

    def test_patch_applies_timezone_offset(self, srt_file, tmp_path):
        """When video_path is provided, timestamps should be shifted by tz offset."""
        import os
        from datetime import UTC, datetime

        # Create a fake video file with mtime = first SRT point in UTC+3
        # SRT time is 12:34:24 local, so UTC is 09:34:24 (offset = +3h)
        # Set video mtime to 09:34:24 UTC (= mtime role "start")
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"\x00")
        utc_time = datetime(2024, 8, 7, 9, 34, 24, tzinfo=UTC)
        os.utime(video_file, (utc_time.timestamp(), utc_time.timestamp()))

        from gpstitch.patches.gpx_patches import patch_gpx_load_for_srt

        patch_gpx_load_for_srt(str(srt_file), str(video_file))

        import gopro_overlay.loading as loading_module
        from gopro_overlay.units import units

        ts = loading_module.load_external(Path("/dummy.gpx"), units)
        entry = ts.get(ts.min)

        # The timestamp should be shifted back by 3 hours (local → UTC-aware)
        # SRT: 2024-08-07 12:34:24.380 local → 2024-08-07 09:34:24.380 UTC
        expected_dt = datetime(2024, 8, 7, 9, 34, 24, 380000, tzinfo=UTC)
        assert entry.dt.tzinfo is not None, "Timestamp should be UTC-aware"
        assert abs((entry.dt - expected_dt).total_seconds()) < 1
        # Camera metrics should still be present
        assert entry.iso is not None
