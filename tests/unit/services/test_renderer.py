"""Unit tests for renderer - video canvas fitting and CLI command generation."""

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from gpstitch.services.renderer import _fit_video_to_canvas, _resolve_time_alignment


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


class TestGenerateCliCommandNewModes:
    """Tests for generate_cli_command with new time alignment modes (auto, gpx-timestamps, manual)."""

    @pytest.fixture
    def mock_file_manager(self, monkeypatch):
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

    def test_auto_mode_maps_to_file_modified(self, mock_file_manager):
        """Auto mode should map to --video-time-start file-modified in CLI."""
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
            video_time_alignment="auto",
        )

        assert "--use-gpx-only" in cmd
        assert "--video-time-start" in cmd
        assert "file-modified" in cmd
        assert "--gpx-merge" not in cmd

    def test_manual_mode_maps_to_file_modified(self, mock_file_manager):
        """Manual mode should map to --video-time-start file-modified in CLI."""
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
            video_time_alignment="manual",
        )

        assert "--use-gpx-only" in cmd
        assert "--video-time-start" in cmd
        assert "file-modified" in cmd

    def test_gpx_timestamps_mode_uses_gpx_merge(self, mock_file_manager):
        """GPX-timestamps mode should use --gpx-merge (no time alignment)."""
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
            video_time_alignment="gpx-timestamps",
        )

        assert "--gpx-merge" in cmd
        assert "--use-gpx-only" not in cmd
        assert "--video-time-start" not in cmd

    def test_auto_mode_gpx_only_primary_maps_to_file_modified(self, mock_file_manager):
        """Auto mode with GPX-only primary should map to --video-time-start file-modified."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.services.renderer import generate_cli_command

        primary = self._make_file_info("/tmp/track.gpx", "gpx", FileRole.PRIMARY)

        mock_file_manager.get_files.return_value = [primary]
        mock_file_manager.get_primary_file.return_value = primary
        mock_file_manager.get_secondary_file.return_value = None

        cmd, _ = generate_cli_command(
            session_id="test-session",
            output_file="/tmp/output.mp4",
            layout="default-1920x1080",
            video_time_alignment="auto",
        )

        assert "--video-time-start" in cmd
        assert "file-modified" in cmd


class TestPreviewPipelineAlignment:
    """Tests that time_offset_seconds is accepted by preview pipeline."""

    def test_render_preview_accepts_time_offset_parameter(self):
        """render_preview should accept time_offset_seconds parameter."""
        import inspect

        from gpstitch.services.renderer import render_preview

        sig = inspect.signature(render_preview)
        assert "time_offset_seconds" in sig.parameters
        param = sig.parameters["time_offset_seconds"]
        assert param.default == 0


class TestResolveTimeAlignment:
    """Tests for _resolve_time_alignment with new auto/gpx-timestamps/manual modes."""

    @pytest.fixture
    def mock_ffmpeg_gopro(self):
        gopro = MagicMock()
        duration = MagicMock()
        duration.millis.return_value = 120000
        gopro.find_recording.return_value.video.duration = duration
        return gopro

    @pytest.fixture
    def creation_time(self):
        return datetime.datetime(2024, 8, 8, 17, 13, 0, tzinfo=datetime.UTC)

    @pytest.fixture
    def file_ctime(self):
        return datetime.datetime(2024, 8, 8, 11, 0, 0, tzinfo=datetime.UTC)

    def test_auto_mode_with_creation_time(self, mock_ffmpeg_gopro, creation_time):
        """Auto mode should use creation_time from video metadata when available."""
        with patch(
            "gpstitch.services.renderer._extract_creation_time",
            return_value=creation_time,
        ):
            start_date, duration, source = _resolve_time_alignment(Path("/tmp/video.mov"), "auto", mock_ffmpeg_gopro)

        assert start_date == creation_time
        assert source == "media-created"
        assert duration is not None

    def test_auto_mode_fallback_to_st_ctime(self, mock_ffmpeg_gopro, file_ctime):
        """Auto mode should fallback to st_ctime when no creation_time in metadata."""
        mock_fstat = MagicMock()
        mock_fstat.ctime = file_ctime

        with (
            patch("gpstitch.services.renderer._extract_creation_time", return_value=None),
            patch("gopro_overlay.ffmpeg_gopro.filestat", return_value=mock_fstat),
        ):
            start_date, duration, source = _resolve_time_alignment(Path("/tmp/video.mov"), "auto", mock_ffmpeg_gopro)

        assert start_date == file_ctime
        assert source == "file-created"
        assert duration is not None

    def test_gpx_timestamps_mode(self, mock_ffmpeg_gopro):
        """GPX-timestamps mode should return no alignment (None, None, None)."""
        start_date, duration, source = _resolve_time_alignment(
            Path("/tmp/video.mov"), "gpx-timestamps", mock_ffmpeg_gopro
        )

        assert start_date is None
        assert duration is None
        assert source is None

    def test_none_alignment_defaults_to_auto(self, mock_ffmpeg_gopro, creation_time):
        """None alignment should default to auto mode."""
        start_date, duration, source = _resolve_time_alignment(Path("/tmp/video.mov"), None, mock_ffmpeg_gopro)

        assert start_date is None
        assert duration is None
        assert source is None

    def test_manual_mode_with_offset(self, mock_ffmpeg_gopro, creation_time):
        """Manual mode should apply offset to auto-detected time."""
        with patch(
            "gpstitch.services.renderer._extract_creation_time",
            return_value=creation_time,
        ):
            start_date, duration, source = _resolve_time_alignment(
                Path("/tmp/video.mov"),
                "manual",
                mock_ffmpeg_gopro,
                time_offset_seconds=60,
            )

        expected = creation_time + datetime.timedelta(seconds=60)
        assert start_date == expected
        assert source == "media-created"

    def test_manual_mode_with_negative_offset(self, mock_ffmpeg_gopro, creation_time):
        """Manual mode should support negative offsets."""
        with patch(
            "gpstitch.services.renderer._extract_creation_time",
            return_value=creation_time,
        ):
            start_date, duration, source = _resolve_time_alignment(
                Path("/tmp/video.mov"),
                "manual",
                mock_ffmpeg_gopro,
                time_offset_seconds=-30,
            )

        expected = creation_time + datetime.timedelta(seconds=-30)
        assert start_date == expected

    def test_manual_mode_zero_offset(self, mock_ffmpeg_gopro, creation_time):
        """Manual mode with zero offset should return unshifted time."""
        with patch(
            "gpstitch.services.renderer._extract_creation_time",
            return_value=creation_time,
        ):
            start_date, duration, source = _resolve_time_alignment(
                Path("/tmp/video.mov"),
                "manual",
                mock_ffmpeg_gopro,
                time_offset_seconds=0,
            )

        assert start_date == creation_time
