"""Integration tests for Novatek/Viofo embedded GPS end to end (issue #27).

The reporter's dashcam video has no GoPro GPMF stream, so preview failed with
"Unable to locate metadata stream in '...' — is it a GoPro file". The GPS is in
`freeGPS` blocks instead. These tests cover the wiring around
`services/novatek_parser.py`: metadata detection, preview framemeta, and the
render path's GPX handoff.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


class TestMetadataDetection:
    """extract_video_metadata() must flag the embedded telemetry for the UI."""

    def test_reports_novatek_gps(self, integration_test_viofo_video):
        from gpstitch.services.metadata import extract_video_metadata

        meta = extract_video_metadata(integration_test_viofo_video)

        assert meta is not None
        assert meta.has_novatek_gps is True
        assert meta.novatek_gps_point_count == 7
        # has_gps stays GPMF-only, as it does for DJI meta videos; the embedded
        # telemetry surfaces through has_novatek_gps / has_embedded_gps instead.
        assert meta.has_gps is False

    def test_gopro_video_is_not_flagged_as_novatek(self, integration_test_video):
        from gpstitch.services.metadata import extract_video_metadata

        meta = extract_video_metadata(integration_test_video)

        assert meta is not None
        assert meta.has_novatek_gps is False

    def test_video_without_gps_is_not_flagged(self, integration_test_mov_video):
        from gpstitch.services.metadata import extract_video_metadata

        meta = extract_video_metadata(integration_test_mov_video)

        assert meta is not None
        assert meta.has_novatek_gps is False


class TestPreviewFramemeta:
    """_load_video_framemeta() must fall back to Novatek GPS."""

    def test_builds_framemeta_from_embedded_gps(self, integration_test_viofo_video):
        from gpstitch.services.renderer import _load_video_framemeta

        framemeta = _load_video_framemeta(
            integration_test_viofo_video,
            video_time_alignment=None,
            time_offset_seconds=0,
            gpx_path=None,
            gps_dop_max=20,
            gps_speed_max=200,
        )

        assert len(framemeta) > 0

    def test_framemeta_carries_the_real_coordinates(self, integration_test_viofo_video):
        from gpstitch.services.renderer import _load_video_framemeta

        framemeta = _load_video_framemeta(
            integration_test_viofo_video,
            video_time_alignment=None,
            time_offset_seconds=0,
            gpx_path=None,
            gps_dop_max=20,
            gps_speed_max=200,
        )
        entry = framemeta.get(framemeta.min)

        assert entry.point.lat == pytest.approx(34.1732, abs=1e-3)
        assert entry.point.lon == pytest.approx(108.9088, abs=1e-3)

    def test_external_gpx_still_wins_over_embedded_gps(self, integration_test_viofo_video, integration_test_run_gpx):
        """Issue #18 precedence: an explicitly supplied file beats embedded GPS."""
        from gpstitch.services.renderer import _load_video_framemeta

        framemeta = _load_video_framemeta(
            integration_test_viofo_video,
            video_time_alignment=None,
            time_offset_seconds=0,
            gpx_path=Path(integration_test_run_gpx),
            gps_dop_max=20,
            gps_speed_max=200,
        )
        entry = framemeta.get(framemeta.min)

        # The hiking GPX is nowhere near the dashcam's Xi'an coordinates.
        assert entry.point.lat != pytest.approx(34.1732, abs=1e-3)


class TestPreviewRender:
    """The failing user-visible operation from the issue."""

    def test_preview_renders_without_an_external_gpx(self, integration_test_viofo_video):
        from gpstitch.services.renderer import render_preview

        png_bytes, width, height = render_preview(
            integration_test_viofo_video,
            layout="default-1920x1080",
            frame_time_ms=0,
        )

        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert width > 0 and height > 0


class TestRenderHandoff:
    """gopro-dashboard.py only accepts GPX/FIT, so the render path exports one."""

    def test_gpx_export_round_trips_through_the_loader(self, integration_test_viofo_video, tmp_path):
        from gopro_overlay.loading import load_external
        from gopro_overlay.units import units

        from gpstitch.services.novatek_parser import novatek_to_gpx_file

        gpx_path = novatek_to_gpx_file(integration_test_viofo_video, tmp_path / "novatek.gpx")
        timeseries = load_external(gpx_path, units)
        entry = timeseries.get(timeseries.min)

        assert entry.point.lat == pytest.approx(34.1732, abs=1e-3)

    def test_wrapper_patch_replaces_load_external(self, integration_test_viofo_video):
        import gopro_overlay.loading as loading_module
        from gopro_overlay.units import units

        from gpstitch.patches.gpx_patches import patch_novatek_load

        original = loading_module.load_external
        try:
            patch_novatek_load(str(integration_test_viofo_video))
            timeseries = loading_module.load_external(Path("/nonexistent/ignored.gpx"), units)
        finally:
            loading_module.load_external = original
            if hasattr(loading_module, "_ts_novatek_patched"):
                delattr(loading_module, "_ts_novatek_patched")

        assert len(timeseries.items()) > 0
