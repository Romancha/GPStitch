"""Unit tests for renderer - video canvas fitting and CLI command generation."""

from unittest.mock import MagicMock

import pytest
from PIL import Image

from gpstitch.services.renderer import _fit_video_to_canvas


class TestFitVideoToCanvas:
    """Tests for _fit_video_to_canvas pillarbox/letterbox function."""

    def test_same_dimensions_returns_original(self):
        """When video matches canvas exactly, return as-is."""
        video = Image.new("RGBA", (1920, 1080), (255, 0, 0, 255))
        result = _fit_video_to_canvas(video, 1920, 1080)
        assert result.size == (1920, 1080)
        # Should return the original image object (not a copy)
        assert result is video

    def test_portrait_video_on_landscape_canvas_pillarbox(self):
        """Portrait video (1080x1920) on landscape canvas (3840x2160) gets pillarboxed."""
        video = Image.new("RGBA", (1080, 1920), (255, 0, 0, 255))
        result = _fit_video_to_canvas(video, 3840, 2160)
        assert result.size == (3840, 2160)

        # Check black bars on left and right sides
        # Video should be centered: scale = min(3840/1080, 2160/1920) = min(3.555, 1.125) = 1.125
        # New dimensions: 1080*1.125=1215, 1920*1.125=2160
        # Offset x: (3840 - 1215) // 2 = 1312
        left_pixel = result.getpixel((0, 1080))  # Left bar
        right_pixel = result.getpixel((3839, 1080))  # Right bar
        center_pixel = result.getpixel((1920, 1080))  # Center (video area)

        assert left_pixel == (0, 0, 0, 255), "Left bar should be black"
        assert right_pixel == (0, 0, 0, 255), "Right bar should be black"
        assert center_pixel == (255, 0, 0, 255), "Center should be video color"

    def test_landscape_video_on_portrait_canvas_letterbox(self):
        """Landscape video (1920x1080) on portrait canvas (1080x1920) gets letterboxed."""
        video = Image.new("RGBA", (1920, 1080), (0, 255, 0, 255))
        result = _fit_video_to_canvas(video, 1080, 1920)
        assert result.size == (1080, 1920)

        # Video should be letterboxed (black bars top and bottom)
        # scale = min(1080/1920, 1920/1080) = min(0.5625, 1.777) = 0.5625
        # New dimensions: 1920*0.5625=1080, 1080*0.5625=607
        # Offset y: (1920 - 607) // 2 = 656
        top_pixel = result.getpixel((540, 0))  # Top bar
        bottom_pixel = result.getpixel((540, 1919))  # Bottom bar
        center_pixel = result.getpixel((540, 960))  # Center (video area)

        assert top_pixel == (0, 0, 0, 255), "Top bar should be black"
        assert bottom_pixel == (0, 0, 0, 255), "Bottom bar should be black"
        assert center_pixel == (0, 255, 0, 255), "Center should be video color"

    def test_small_video_scaled_up(self):
        """Small video (640x480) on large canvas (1920x1080) scales up preserving ratio."""
        video = Image.new("RGBA", (640, 480), (0, 0, 255, 255))
        result = _fit_video_to_canvas(video, 1920, 1080)
        assert result.size == (1920, 1080)

        # 640:480 = 4:3, canvas 1920:1080 = 16:9
        # scale = min(1920/640, 1080/480) = min(3.0, 2.25) = 2.25
        # New: 640*2.25=1440, 480*2.25=1080 -> offset_x = (1920-1440)//2 = 240
        left_bar = result.getpixel((0, 540))
        right_bar = result.getpixel((1919, 540))
        center = result.getpixel((960, 540))

        assert left_bar == (0, 0, 0, 255), "Left bar should be black"
        assert right_bar == (0, 0, 0, 255), "Right bar should be black"
        assert center == (0, 0, 255, 255), "Center should be video color"

    def test_same_aspect_ratio_different_size(self):
        """Video with same aspect ratio but different size fills canvas entirely."""
        video = Image.new("RGBA", (960, 540), (128, 128, 128, 255))
        result = _fit_video_to_canvas(video, 1920, 1080)
        assert result.size == (1920, 1080)

        # Same 16:9 ratio, so no black bars
        corner = result.getpixel((0, 0))
        center = result.getpixel((960, 540))
        assert corner == (128, 128, 128, 255), "Corner should be video color (no bars)"
        assert center == (128, 128, 128, 255), "Center should be video color"


class TestGenerateCliCommand:
    """Tests for generate_cli_command with vertical video and time alignment."""

    @pytest.fixture
    def mock_file_manager(self, monkeypatch):
        """Create mock file_manager for command generation tests."""
        from gpstitch.services import file_manager as fm_module

        manager = MagicMock()
        monkeypatch.setattr(fm_module, "file_manager", manager)
        return manager

    def _make_file_info(self, file_path, file_type, role):
        from gpstitch.models.schemas import FileInfo

        return FileInfo(
            filename=file_path.split("/")[-1],
            file_path=file_path,
            file_type=file_type,
            role=role,
        )

    def test_video_gpx_with_time_alignment_uses_gpx_only(self, mock_file_manager):
        """Video + GPX with time alignment should use --use-gpx-only, not --gpx-merge."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.services.renderer import generate_cli_command

        primary = self._make_file_info("/tmp/video.mov", "video", FileRole.PRIMARY)
        secondary = self._make_file_info("/tmp/track.gpx", "gpx", FileRole.SECONDARY)

        mock_file_manager.get_files.return_value = [primary, secondary]
        mock_file_manager.get_primary_file.return_value = primary
        mock_file_manager.get_secondary_file.return_value = secondary

        cmd, _ = generate_cli_command(
            session_id="test-session",
            output_file="/tmp/output.mp4",
            layout="default-3840x2160",
            video_time_alignment="file-modified",
        )

        assert "--use-gpx-only" in cmd
        assert "--video-time-start" in cmd
        assert "file-modified" in cmd
        assert "--gpx-merge" not in cmd

    def test_video_gpx_without_time_alignment_uses_gpx_merge(self, mock_file_manager):
        """Video + GPX without time alignment should use --gpx-merge."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.services.renderer import generate_cli_command

        primary = self._make_file_info("/tmp/video.mov", "video", FileRole.PRIMARY)
        secondary = self._make_file_info("/tmp/track.gpx", "gpx", FileRole.SECONDARY)

        mock_file_manager.get_files.return_value = [primary, secondary]
        mock_file_manager.get_primary_file.return_value = primary
        mock_file_manager.get_secondary_file.return_value = secondary

        cmd, _ = generate_cli_command(
            session_id="test-session",
            output_file="/tmp/output.mp4",
            layout="default-3840x2160",
        )

        assert "--gpx-merge" in cmd
        assert "--use-gpx-only" not in cmd
        assert "--video-time-start" not in cmd

    def test_video_mode_includes_overlay_size(self, mock_file_manager):
        """Video mode should include --overlay-size matching canvas dimensions."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.services.renderer import generate_cli_command

        primary = self._make_file_info("/tmp/video.mov", "video", FileRole.PRIMARY)

        mock_file_manager.get_files.return_value = [primary]
        mock_file_manager.get_primary_file.return_value = primary
        mock_file_manager.get_secondary_file.return_value = None

        cmd, _ = generate_cli_command(
            session_id="test-session",
            output_file="/tmp/output.mp4",
            layout="default-3840x2160",
        )

        assert "--overlay-size 3840x2160" in cmd

    def test_video_gpx_mode_includes_overlay_size(self, mock_file_manager):
        """Video + GPX mode should include --overlay-size matching canvas dimensions."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.services.renderer import generate_cli_command

        primary = self._make_file_info("/tmp/video.mov", "video", FileRole.PRIMARY)
        secondary = self._make_file_info("/tmp/track.gpx", "gpx", FileRole.SECONDARY)

        mock_file_manager.get_files.return_value = [primary, secondary]
        mock_file_manager.get_primary_file.return_value = primary
        mock_file_manager.get_secondary_file.return_value = secondary

        cmd, _ = generate_cli_command(
            session_id="test-session",
            output_file="/tmp/output.mp4",
            layout="default-3840x2160",
            video_time_alignment="file-modified",
        )

        assert "--overlay-size 3840x2160" in cmd

    def test_video_only_no_video_time_start(self, mock_file_manager):
        """Video-only mode should not include --video-time-start (requires --use-gpx-only)."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.services.renderer import generate_cli_command

        primary = self._make_file_info("/tmp/video.mp4", "video", FileRole.PRIMARY)

        mock_file_manager.get_files.return_value = [primary]
        mock_file_manager.get_primary_file.return_value = primary
        mock_file_manager.get_secondary_file.return_value = None

        cmd, _ = generate_cli_command(
            session_id="test-session",
            output_file="/tmp/output.mp4",
            layout="default-1920x1080",
            video_time_alignment="file-modified",
        )

        # --video-time-start is not valid without --use-gpx-only
        assert "--video-time-start" not in cmd
