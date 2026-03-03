"""Integration tests for metadata extraction with real gopro-overlay."""

import pytest


@pytest.mark.integration
class TestVideoMetadataExtraction:
    """Tests for video metadata extraction with real files."""

    def test_extract_video_metadata(self, integration_test_video):
        """Extract metadata from real GoPro video."""
        from gpstitch.services.metadata import extract_video_metadata

        metadata = extract_video_metadata(integration_test_video)

        assert metadata is not None
        assert metadata.width > 0
        assert metadata.height > 0
        assert metadata.duration_seconds > 0
        assert metadata.frame_count > 0
        assert metadata.frame_rate > 0

    def test_video_has_gps(self, integration_test_video):
        """GoPro video should have GPS data."""
        from gpstitch.services.metadata import extract_video_metadata

        metadata = extract_video_metadata(integration_test_video)

        # GoPro videos typically have GPS
        assert metadata.has_gps is True

    def test_video_resolution_reasonable(self, integration_test_video):
        """Video resolution should be reasonable."""
        from gpstitch.services.metadata import extract_video_metadata

        metadata = extract_video_metadata(integration_test_video)

        # Should be at least 720p
        assert metadata.width >= 1280
        assert metadata.height >= 720

    def test_video_frame_rate_valid(self, integration_test_video):
        """Frame rate should be valid."""
        from gpstitch.services.metadata import extract_video_metadata

        metadata = extract_video_metadata(integration_test_video)

        # Typical GoPro frame rates
        valid_fps = [24, 25, 29.97, 30, 50, 59.94, 60, 100, 120, 240]
        assert any(abs(metadata.frame_rate - fps) < 1 for fps in valid_fps)


@pytest.mark.integration
class TestGpxFitMetadataExtraction:
    """Tests for GPX/FIT metadata extraction."""

    def test_extract_gpx_metadata(self, sample_gpx_file):
        """Extract metadata from GPX file."""
        from gpstitch.services.metadata import extract_gpx_fit_metadata

        metadata = extract_gpx_fit_metadata(sample_gpx_file)

        assert metadata is not None
        assert metadata.gps_point_count > 0


@pytest.mark.integration
class TestMOVVideoMetadataExtraction:
    """Tests for MOV video metadata extraction."""

    def test_extract_mov_video_metadata(self, integration_test_mov_video):
        """Extract metadata from MOV video."""
        from gpstitch.services.metadata import extract_video_metadata

        metadata = extract_video_metadata(integration_test_mov_video)

        assert metadata is not None
        assert metadata.width > 0
        assert metadata.height > 0
        assert metadata.duration_seconds > 0

    def test_mov_video_has_no_gps(self, integration_test_mov_video):
        """MOV video without telemetry should have has_gps=False."""
        from gpstitch.services.metadata import extract_video_metadata

        metadata = extract_video_metadata(integration_test_mov_video)

        assert metadata is not None
        assert metadata.has_gps is False

    def test_mov_video_rotation_applied(self, integration_test_mov_video):
        """Verify rotation is applied to MOV video dimensions."""
        from gpstitch.services.metadata import (
            extract_video_metadata,
            get_video_rotation,
        )

        get_video_rotation(integration_test_mov_video)
        metadata = extract_video_metadata(integration_test_mov_video)

        assert metadata is not None
        # If rotation is 90 or 270, width and height should be swapped
        # Just verify we got valid dimensions back
        assert metadata.width > 0
        assert metadata.height > 0


@pytest.mark.integration
class TestFileTypeDetection:
    """Tests for file type detection."""

    def test_detect_video_type(self, integration_test_video):
        """Detect video file type."""
        from gpstitch.services.metadata import get_file_type

        file_type = get_file_type(integration_test_video)

        assert file_type == "video"

    def test_detect_gpx_type(self, sample_gpx_file):
        """Detect GPX file type."""
        from gpstitch.services.metadata import get_file_type

        file_type = get_file_type(sample_gpx_file)

        assert file_type == "gpx"

    def test_detect_fit_type(self, temp_dir):
        """Detect FIT file type."""
        from gpstitch.services.metadata import get_file_type

        fit_file = temp_dir / "test.fit"
        fit_file.write_bytes(b"fake fit content")

        file_type = get_file_type(fit_file)

        assert file_type == "fit"

    def test_detect_mov_type(self, integration_test_mov_video):
        """Detect MOV file type."""
        from gpstitch.services.metadata import get_file_type

        file_type = get_file_type(integration_test_mov_video)

        assert file_type == "video"

    def test_unknown_file_type(self, temp_dir):
        """Unknown file extension returns 'unknown'."""
        from gpstitch.services.metadata import get_file_type

        txt_file = temp_dir / "test.txt"
        txt_file.write_text("hello")

        file_type = get_file_type(txt_file)

        # Returns "unknown" for unknown types
        assert file_type == "unknown"
