"""Integration tests for DJI Action preview rendering with embedded GPS."""

from pathlib import Path

import pytest


@pytest.mark.integration
class TestDjiMetaPreviewRendering:
    """Tests for preview rendering with DJI Action embedded GPS (DJI meta stream)."""

    def test_render_preview_with_dji_meta_gps(self, integration_test_dji_action_video):
        """DJI Action video with embedded GPS should render preview without external GPX."""
        from gpstitch.services.renderer import render_preview

        png_bytes, width, height = render_preview(
            file_path=integration_test_dji_action_video,
            layout="default-1920x1080",
            frame_time_ms=0,
        )

        assert len(png_bytes) > 0
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert width == 1920
        assert height == 1080

    def test_render_preview_dji_meta_correct_dimensions(self, integration_test_dji_action_video):
        """Preview should have correct canvas dimensions."""
        from gpstitch.services.renderer import render_preview

        png_bytes, width, height = render_preview(
            file_path=integration_test_dji_action_video,
            layout="default-1920x1080",
            frame_time_ms=0,
        )

        from io import BytesIO

        from PIL import Image

        image = Image.open(BytesIO(png_bytes))
        assert image.size == (1920, 1080)

    def test_render_preview_dji_meta_with_external_gpx_override(self, integration_test_dji_action_video):
        """External GPX should take precedence over embedded DJI meta GPS.

        When gpx_path is provided, the renderer should use the external GPX
        rather than the embedded DJI meta stream.
        """
        import tempfile

        from gpstitch.services.dji_meta_parser import dji_meta_to_gpx_file
        from gpstitch.services.renderer import render_preview

        # Generate a GPX from the DJI meta data itself (same coordinates)
        # to avoid time alignment issues with unrelated GPX files
        with tempfile.NamedTemporaryFile(suffix=".gpx", delete=False) as f:
            gpx_path = Path(f.name)

        try:
            dji_meta_to_gpx_file(integration_test_dji_action_video, gpx_path, sample_rate=25)

            # Use gpx-timestamps to avoid time alignment issues
            png_bytes, width, height = render_preview(
                file_path=integration_test_dji_action_video,
                layout="default-1920x1080",
                frame_time_ms=0,
                gpx_path=gpx_path,
                video_time_alignment="gpx-timestamps",
            )

            assert len(png_bytes) > 0
            assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
            assert width == 1920
            assert height == 1080
        finally:
            gpx_path.unlink(missing_ok=True)


@pytest.mark.integration
class TestDjiMetaLoadHelper:
    """Tests for the _load_dji_meta_for_preview helper."""

    def test_load_dji_meta_for_preview_returns_timeseries(self, integration_test_dji_action_video):
        """Helper should return a processed Timeseries with GPS data."""
        from gopro_overlay.units import units

        from gpstitch.services.renderer import _load_dji_meta_for_preview

        timeseries = _load_dji_meta_for_preview(integration_test_dji_action_video, units)

        entries = timeseries.items()
        assert len(entries) > 0

        # Should have GPS coordinates
        first = entries[0]
        assert first.point is not None
        assert first.point.lat != 0.0
        assert first.point.lon != 0.0

    def test_load_dji_meta_for_preview_thinned(self, integration_test_dji_action_video):
        """Helper should thin high-frequency data (25fps) down to ~1Hz."""
        from gopro_overlay.units import units

        from gpstitch.services.renderer import _load_dji_meta_for_preview

        timeseries = _load_dji_meta_for_preview(integration_test_dji_action_video, units)

        entries = timeseries.items()
        # 5-second fixture at 25fps = 125 raw points, thinned to ~1Hz = ~5 points
        assert len(entries) < 20, f"Expected thinned data (<20 entries), got {len(entries)}"
        assert len(entries) >= 2, f"Expected at least 2 entries, got {len(entries)}"
