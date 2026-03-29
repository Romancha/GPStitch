"""Unit tests for renderer - video canvas fitting and CLI command generation."""

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from gpstitch.services.renderer import _fit_video_to_canvas, _resolve_time_alignment, _validate_creation_time


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

    def test_command_starts_with_gpstitch_dashboard(self, mock_file_manager):
        """Generated command should start with gpstitch-dashboard, not gopro-dashboard.py."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.services.renderer import generate_cli_command

        primary = self._make_file_info("/tmp/video.mov", "video", FileRole.PRIMARY)

        mock_file_manager.get_files.return_value = [primary]
        mock_file_manager.get_primary_file.return_value = primary
        mock_file_manager.get_secondary_file.return_value = None

        cmd, _ = generate_cli_command(
            session_id="test-session",
            output_file="/tmp/output.mp4",
            layout="default-1920x1080",
        )

        assert cmd.startswith("gpstitch-dashboard ")
        assert "gopro-dashboard.py" not in cmd

    def test_command_with_gpx_starts_with_gpstitch_dashboard(self, mock_file_manager):
        """Video + GPX command should also start with gpstitch-dashboard."""
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

        assert cmd.startswith("gpstitch-dashboard ")
        assert "gopro-dashboard.py" not in cmd

    @patch("gpstitch.services.renderer._convert_srt_to_gpx", return_value="/tmp/converted.gpx")
    @patch("gpstitch.services.srt_parser.estimate_tz_offset", return_value=(0, "start"))
    def test_wrapper_args_present_when_srt_secondary(self, _mock_tz, _mock_convert, mock_file_manager):
        """Wrapper args --ts-srt-source and --ts-srt-video should be present in generated command."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.services.renderer import generate_cli_command

        primary = self._make_file_info("/tmp/video.mov", "video", FileRole.PRIMARY)
        secondary = self._make_file_info("/tmp/telemetry.srt", "srt", FileRole.SECONDARY)

        mock_file_manager.get_files.return_value = [primary, secondary]
        mock_file_manager.get_primary_file.return_value = primary
        mock_file_manager.get_secondary_file.return_value = secondary

        cmd, _ = generate_cli_command(
            session_id="test-session",
            output_file="/tmp/output.mp4",
            layout="default-1920x1080",
        )

        assert "--ts-srt-source" in cmd
        assert "--ts-srt-video" in cmd

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


class TestValidateCreationTime:
    """Tests for _validate_creation_time — cross-validation of creation_time against GPS data."""

    # Simulate Insta360 bug: creation_time is local PST (UTC-8) stored as UTC.
    # Real UTC should be 19:34:47, but camera wrote 11:34:47 as UTC.
    WRONG_CREATION_TIME = datetime.datetime(2026, 2, 6, 11, 34, 47, tzinfo=datetime.UTC)
    CORRECT_MTIME_TS = datetime.datetime(2026, 2, 6, 19, 34, 47, tzinfo=datetime.UTC).timestamp()
    VIDEO_DURATION = 50.0  # 50 seconds

    # GPS range: 18:10:23 UTC -> 20:02:53 UTC
    GPS_RANGE = (
        datetime.datetime(2026, 2, 6, 18, 10, 23, tzinfo=datetime.UTC).timestamp(),
        datetime.datetime(2026, 2, 6, 20, 2, 53, tzinfo=datetime.UTC).timestamp(),
    )

    def test_creation_time_correct_gopro(self):
        """When creation_time overlaps GPS range (GoPro), keep it as-is."""
        correct_ct = datetime.datetime(2026, 2, 6, 19, 34, 47, tzinfo=datetime.UTC)
        with patch("gpstitch.services.renderer._get_gps_time_range", return_value=self.GPS_RANGE):
            result = _validate_creation_time(
                Path("/tmp/video.mp4"), correct_ct, self.VIDEO_DURATION, Path("/tmp/track.fit")
            )
        assert result == correct_ct

    def test_creation_time_wrong_mtime_correct_insta360(self):
        """When creation_time doesn't overlap but mtime does (Insta360), use mtime."""
        with (
            patch("gpstitch.services.renderer._get_gps_time_range", return_value=self.GPS_RANGE),
            patch("gpstitch.services.renderer.os.stat") as mock_stat,
        ):
            mock_stat.return_value.st_mtime = self.CORRECT_MTIME_TS
            result = _validate_creation_time(
                Path("/tmp/video.mp4"), self.WRONG_CREATION_TIME, self.VIDEO_DURATION, Path("/tmp/track.fit")
            )
        expected = datetime.datetime.fromtimestamp(self.CORRECT_MTIME_TS, tz=datetime.UTC)
        assert result == expected

    def test_mtime_as_recording_end(self):
        """When mtime is at the end of GPS range, only end-overlap triggers, adjust to start."""
        # GPS range: 18:10:23 -> 20:02:53 UTC
        # mtime = 20:02:50 UTC (near end of GPS range)
        # As start: [20:02:50, 20:03:40] — barely overlaps GPS end, so start_overlaps=True
        # Use a longer duration to make the distinction clearer:
        # mtime = 20:03:00 UTC, duration = 120s (2 min)
        # As start: [20:03:00, 20:05:00] — start > gps_max (20:02:53), so start_overlaps=False
        # As end: [20:01:00, 20:03:00] — overlaps GPS range, so end_overlaps=True
        mtime_end = datetime.datetime(2026, 2, 6, 20, 3, 0, tzinfo=datetime.UTC).timestamp()
        video_duration = 120.0
        wrong_ct = datetime.datetime(2026, 2, 6, 3, 0, 0, tzinfo=datetime.UTC)
        with (
            patch("gpstitch.services.renderer._get_gps_time_range", return_value=self.GPS_RANGE),
            patch("gpstitch.services.renderer.os.stat") as mock_stat,
        ):
            mock_stat.return_value.st_mtime = mtime_end
            result = _validate_creation_time(Path("/tmp/video.mp4"), wrong_ct, video_duration, Path("/tmp/track.fit"))
        # mtime is recording end — should be adjusted to start (mtime - duration)
        expected = datetime.datetime.fromtimestamp(mtime_end, tz=datetime.UTC) - datetime.timedelta(
            seconds=video_duration
        )
        assert result == expected

    def test_neither_overlaps_fallback_to_creation_time(self):
        """When neither creation_time nor mtime overlaps, keep creation_time."""
        wrong_ct = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)
        wrong_mtime = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.UTC).timestamp()
        with (
            patch("gpstitch.services.renderer._get_gps_time_range", return_value=self.GPS_RANGE),
            patch("gpstitch.services.renderer.os.stat") as mock_stat,
        ):
            mock_stat.return_value.st_mtime = wrong_mtime
            result = _validate_creation_time(
                Path("/tmp/video.mp4"), wrong_ct, self.VIDEO_DURATION, Path("/tmp/track.fit")
            )
        assert result == wrong_ct

    def test_no_gps_path_returns_creation_time(self):
        """Without GPS file, return creation_time unchanged."""
        result = _validate_creation_time(Path("/tmp/video.mp4"), self.WRONG_CREATION_TIME, self.VIDEO_DURATION, None)
        assert result == self.WRONG_CREATION_TIME

    def test_srt_file_skipped(self):
        """SRT files are not used for validation (they have naive local timestamps)."""
        result = _validate_creation_time(
            Path("/tmp/video.mp4"), self.WRONG_CREATION_TIME, self.VIDEO_DURATION, Path("/tmp/track.srt")
        )
        assert result == self.WRONG_CREATION_TIME

    def test_gps_range_extraction_fails_returns_creation_time(self):
        """If GPS time range extraction fails, return creation_time unchanged."""
        with patch("gpstitch.services.renderer._get_gps_time_range", return_value=None):
            result = _validate_creation_time(
                Path("/tmp/video.mp4"), self.WRONG_CREATION_TIME, self.VIDEO_DURATION, Path("/tmp/track.fit")
            )
        assert result == self.WRONG_CREATION_TIME

    def test_zero_duration_skips_validation(self):
        """When video_duration_sec=0 (ffprobe failed), skip validation entirely."""
        # Even though mtime would overlap and creation_time wouldn't,
        # we can't reliably validate without a known duration.
        with (
            patch("gpstitch.services.renderer._get_gps_time_range", return_value=self.GPS_RANGE) as mock_gps,
            patch("gpstitch.services.renderer.os.stat") as mock_stat,
        ):
            mock_stat.return_value.st_mtime = self.CORRECT_MTIME_TS
            result = _validate_creation_time(
                Path("/tmp/video.mp4"), self.WRONG_CREATION_TIME, 0.0, Path("/tmp/track.fit")
            )
        # Should return creation_time unchanged — no GPS range lookup should happen
        assert result == self.WRONG_CREATION_TIME
        mock_gps.assert_not_called()
        mock_stat.assert_not_called()

    def test_gps_single_point_skips_validation(self):
        """FIT/GPX with 1 point returns None from _get_gps_time_range, validation skipped."""
        with patch("gpstitch.services.renderer._get_gps_time_range", return_value=None):
            result = _validate_creation_time(
                Path("/tmp/video.mp4"), self.WRONG_CREATION_TIME, self.VIDEO_DURATION, Path("/tmp/track.gpx")
            )
        assert result == self.WRONG_CREATION_TIME

    def test_creation_time_at_gps_boundary(self):
        """creation_time exactly at GPS range start, duration extends into range → overlaps."""
        # creation_time = gps_min exactly, duration extends into GPS range
        ct_at_boundary = datetime.datetime.fromtimestamp(self.GPS_RANGE[0], tz=datetime.UTC)
        with patch("gpstitch.services.renderer._get_gps_time_range", return_value=self.GPS_RANGE):
            result = _validate_creation_time(
                Path("/tmp/video.mp4"), ct_at_boundary, self.VIDEO_DURATION, Path("/tmp/track.fit")
            )
        assert result == ct_at_boundary

    def test_both_mtime_overlaps_uses_start(self):
        """mtime in middle of GPS range — both start and end overlap → mtime used as recording start."""
        # GPS range: 18:10:23 -> 20:02:53 UTC
        # mtime = 19:00:00 UTC (middle of GPS range), duration = 50s
        # As start: [19:00:00, 19:00:50] — overlaps ✓
        # As end: [18:59:10, 19:00:00] — overlaps ✓
        # Both overlap → use mtime as-is (recording start)
        wrong_ct = datetime.datetime(2026, 2, 6, 3, 0, 0, tzinfo=datetime.UTC)
        mtime_mid = datetime.datetime(2026, 2, 6, 19, 0, 0, tzinfo=datetime.UTC).timestamp()
        with (
            patch("gpstitch.services.renderer._get_gps_time_range", return_value=self.GPS_RANGE),
            patch("gpstitch.services.renderer.os.stat") as mock_stat,
        ):
            mock_stat.return_value.st_mtime = mtime_mid
            result = _validate_creation_time(
                Path("/tmp/video.mp4"), wrong_ct, self.VIDEO_DURATION, Path("/tmp/track.fit")
            )
        # Both overlaps true → mtime used as start (no subtraction)
        expected = datetime.datetime.fromtimestamp(mtime_mid, tz=datetime.UTC)
        assert result == expected

    def test_non_whole_hour_timezone_offset(self):
        """creation_time off by 5.5 hours (UTC+5:30 India), should fail overlap, mtime should win."""
        # GPS range: 18:10:23 -> 20:02:53 UTC
        # Real recording at 19:30:00 UTC, but camera stored local time 01:00:00+05:30 = 01:00:00Z
        wrong_ct = datetime.datetime(2026, 2, 7, 1, 0, 0, tzinfo=datetime.UTC)  # 5.5h ahead
        correct_mtime = datetime.datetime(2026, 2, 6, 19, 30, 0, tzinfo=datetime.UTC).timestamp()
        with (
            patch("gpstitch.services.renderer._get_gps_time_range", return_value=self.GPS_RANGE),
            patch("gpstitch.services.renderer.os.stat") as mock_stat,
        ):
            mock_stat.return_value.st_mtime = correct_mtime
            result = _validate_creation_time(
                Path("/tmp/video.mp4"), wrong_ct, self.VIDEO_DURATION, Path("/tmp/track.fit")
            )
        expected = datetime.datetime.fromtimestamp(correct_mtime, tz=datetime.UTC)
        assert result == expected

    def test_video_starts_before_gps_data(self):
        """creation_time before GPS range start, but duration extends into range → should overlap."""
        # GPS range: 18:10:23 -> 20:02:53 UTC
        # creation_time = 18:05:00, duration = 600s (10 min) → video ends at 18:15:00
        # Overlap: 18:05:00 <= 20:02:53 AND 18:15:00 >= 18:10:23 → True
        ct_before = datetime.datetime(2026, 2, 6, 18, 5, 0, tzinfo=datetime.UTC)
        with patch("gpstitch.services.renderer._get_gps_time_range", return_value=self.GPS_RANGE):
            result = _validate_creation_time(Path("/tmp/video.mp4"), ct_before, 600.0, Path("/tmp/track.fit"))
        assert result == ct_before


class TestLayoutCommandGeneration:
    """Tests for --layout / --layout-xml in generate_cli_command (GitHub issue #5)."""

    @pytest.fixture
    def mock_file_manager(self, monkeypatch):
        from gpstitch.services import file_manager as fm_module

        manager = MagicMock()
        monkeypatch.setattr(fm_module, "file_manager", manager)
        return manager

    def _setup_video_only(self, mock_file_manager):
        from gpstitch.models.schemas import FileInfo, FileRole

        primary = FileInfo(
            filename="video.mp4",
            file_path="/tmp/video.mp4",
            file_type="video",
            role=FileRole.PRIMARY,
        )
        mock_file_manager.get_files.return_value = [primary]
        mock_file_manager.get_primary_file.return_value = primary
        mock_file_manager.get_secondary_file.return_value = None

    def test_default_layout_uses_layout_flag(self, mock_file_manager):
        """default-1920x1080 should generate --layout default (not --layout-xml)."""
        from gpstitch.services.renderer import generate_cli_command

        self._setup_video_only(mock_file_manager)

        cmd, _ = generate_cli_command(
            session_id="test",
            output_file="/tmp/out.mp4",
            layout="default-1920x1080",
        )

        assert "--layout default" in cmd
        assert "--layout-xml" not in cmd

    def test_speed_awareness_layout_uses_layout_flag(self, mock_file_manager):
        """speed-awareness should generate --layout speed-awareness."""
        from gpstitch.services.renderer import generate_cli_command

        self._setup_video_only(mock_file_manager)

        cmd, _ = generate_cli_command(
            session_id="test",
            output_file="/tmp/out.mp4",
            layout="speed-awareness",
        )

        assert "--layout speed-awareness" in cmd
        assert "--layout-xml" not in cmd

    def test_xml_layout_uses_layout_xml_flag(self, mock_file_manager):
        """Non-builtin layouts like power-1920x1080 must use --layout xml --layout-xml <path>."""
        import re

        from gpstitch.services.renderer import generate_cli_command

        self._setup_video_only(mock_file_manager)

        cmd, _ = generate_cli_command(
            session_id="test",
            output_file="/tmp/out.mp4",
            layout="power-1920x1080",
        )

        # Must NOT pass layout name directly - gopro-dashboard.py rejects it
        assert "--layout power-1920x1080" not in cmd
        # Must use --layout xml --layout-xml <path>
        assert "--layout xml" in cmd
        assert "--layout-xml" in cmd
        # The resolved path must exist on disk
        m = re.search(r"--layout-xml\s+(\S+)", cmd)
        assert m, "No --layout-xml path found"
        assert Path(m.group(1)).exists(), "layout-xml path must exist on disk"

    def test_moto_layout_uses_layout_xml_flag(self, mock_file_manager):
        """moto_1080 layout must use --layout xml --layout-xml <path>."""
        from gpstitch.services.renderer import generate_cli_command

        self._setup_video_only(mock_file_manager)

        cmd, _ = generate_cli_command(
            session_id="test",
            output_file="/tmp/out.mp4",
            layout="moto_1080",
        )

        assert "--layout moto_1080" not in cmd
        assert "--layout xml" in cmd
        assert "--layout-xml" in cmd

    def test_example_layout_uses_layout_xml_flag(self, mock_file_manager):
        """example layout must use --layout xml --layout-xml <path>."""
        from gpstitch.services.renderer import generate_cli_command

        self._setup_video_only(mock_file_manager)

        cmd, _ = generate_cli_command(
            session_id="test",
            output_file="/tmp/out.mp4",
            layout="example",
        )

        assert "--layout example" not in cmd
        assert "--layout xml" in cmd
        assert "--layout-xml" in cmd

    def test_custom_template_uses_layout_xml_path(self, mock_file_manager):
        """When layout_xml_path is provided, use --layout xml --layout-xml <path>."""
        from gpstitch.services.renderer import generate_cli_command

        self._setup_video_only(mock_file_manager)

        cmd, _ = generate_cli_command(
            session_id="test",
            output_file="/tmp/out.mp4",
            layout="default-1920x1080",
            layout_xml_path="/tmp/custom.xml",
        )

        assert "--layout xml" in cmd
        assert "--layout-xml /tmp/custom.xml" in cmd

    def test_gpstitch_local_layout_uses_layout_xml(self, mock_file_manager):
        """GPStitch custom layouts (e.g. dji-drone-*) should use --layout xml --layout-xml."""
        from gpstitch.services.renderer import generate_cli_command

        self._setup_video_only(mock_file_manager)

        cmd, _ = generate_cli_command(
            session_id="test",
            output_file="/tmp/out.mp4",
            layout="dji-drone-1920x1080",
        )

        assert "--layout xml" in cmd
        assert "--layout-xml" in cmd
        # Verify it resolved to the local gpstitch layout, not gopro-overlay
        local_layout_dir = str(Path(__file__).parent.parent.parent.parent / "src" / "gpstitch" / "layouts")
        assert local_layout_dir in cmd or "dji-drone-1920x1080.xml" in cmd

    def test_unknown_layout_raises_error(self, mock_file_manager):
        """Unknown layout name should raise ValueError."""
        from gpstitch.services.renderer import generate_cli_command

        self._setup_video_only(mock_file_manager)

        with pytest.raises(ValueError, match="not found in gopro_overlay"):
            generate_cli_command(
                session_id="test",
                output_file="/tmp/out.mp4",
                layout="nonexistent-layout-xyz",
            )


class TestGenerateCliCommandDjiMeta:
    """Tests for generate_cli_command with DJI Action embedded GPS (DJI meta stream)."""

    @pytest.fixture
    def mock_file_manager(self, monkeypatch):
        from gpstitch.services import file_manager as fm_module

        manager = MagicMock()
        monkeypatch.setattr(fm_module, "file_manager", manager)
        return manager

    def _make_file_info(self, file_path, file_type, role, has_dji_meta=False, dji_meta_point_count=None):
        from gpstitch.models.schemas import FileInfo, VideoMetadata

        video_metadata = None
        if file_type == "video":
            video_metadata = VideoMetadata(
                width=1920,
                height=1080,
                duration_seconds=5.0,
                frame_count=125,
                frame_rate=25.0,
                has_gps=False,
                has_dji_meta=has_dji_meta,
                dji_meta_point_count=dji_meta_point_count,
            )

        return FileInfo(
            filename=file_path.split("/")[-1],
            file_path=file_path,
            file_type=file_type,
            role=role,
            video_metadata=video_metadata,
        )

    @patch("gpstitch.services.renderer._convert_dji_meta_to_gpx")
    def test_dji_meta_video_uses_gpx_only(self, mock_convert, mock_file_manager):
        """DJI Action video with embedded GPS should use --use-gpx-only with temp GPX."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.services.renderer import generate_cli_command

        mock_convert.return_value = "/tmp/gpstitch_djimeta_test_abc12345.gpx"

        primary = self._make_file_info(
            "/tmp/DJI_video.MP4",
            "video",
            FileRole.PRIMARY,
            has_dji_meta=True,
            dji_meta_point_count=125,
        )

        mock_file_manager.get_files.return_value = [primary]
        mock_file_manager.get_primary_file.return_value = primary
        mock_file_manager.get_secondary_file.return_value = None

        cmd, temp_files = generate_cli_command(
            session_id="test-session",
            output_file="/tmp/output.mp4",
            layout="default-1920x1080",
        )

        assert "--use-gpx-only" in cmd
        assert "--gpx" in cmd
        assert "gpstitch_djimeta_test_abc12345.gpx" in cmd
        assert "--video-time-start" in cmd
        assert "file-modified" in cmd
        assert "/tmp/gpstitch_djimeta_test_abc12345.gpx" in temp_files

    @patch("gpstitch.services.renderer._convert_dji_meta_to_gpx")
    def test_dji_meta_video_includes_wrapper_arg(self, mock_convert, mock_file_manager):
        """DJI Action video should include --ts-dji-meta-source wrapper arg."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.services.renderer import generate_cli_command

        mock_convert.return_value = "/tmp/gpstitch_djimeta_test.gpx"

        primary = self._make_file_info(
            "/tmp/DJI_video.MP4",
            "video",
            FileRole.PRIMARY,
            has_dji_meta=True,
            dji_meta_point_count=125,
        )

        mock_file_manager.get_files.return_value = [primary]
        mock_file_manager.get_primary_file.return_value = primary
        mock_file_manager.get_secondary_file.return_value = None

        cmd, _ = generate_cli_command(
            session_id="test-session",
            output_file="/tmp/output.mp4",
            layout="default-1920x1080",
        )

        assert "--ts-dji-meta-source" in cmd
        assert "/tmp/DJI_video.MP4" in cmd

    @patch("gpstitch.services.renderer._convert_dji_meta_to_gpx")
    def test_dji_meta_video_includes_overlay_size(self, mock_convert, mock_file_manager):
        """DJI Action video should include --overlay-size."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.services.renderer import generate_cli_command

        mock_convert.return_value = "/tmp/gpstitch_djimeta_test.gpx"

        primary = self._make_file_info(
            "/tmp/DJI_video.MP4",
            "video",
            FileRole.PRIMARY,
            has_dji_meta=True,
            dji_meta_point_count=125,
        )

        mock_file_manager.get_files.return_value = [primary]
        mock_file_manager.get_primary_file.return_value = primary
        mock_file_manager.get_secondary_file.return_value = None

        cmd, _ = generate_cli_command(
            session_id="test-session",
            output_file="/tmp/output.mp4",
            layout="default-1920x1080",
        )

        assert "--overlay-size 1920x1080" in cmd

    @patch("gpstitch.services.renderer._convert_dji_meta_to_gpx")
    def test_dji_meta_video_with_secondary_gpx_uses_secondary(self, mock_convert, mock_file_manager):
        """DJI Action video with external GPX should use external GPX, not embedded GPS."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.services.renderer import generate_cli_command

        primary = self._make_file_info(
            "/tmp/DJI_video.MP4",
            "video",
            FileRole.PRIMARY,
            has_dji_meta=True,
            dji_meta_point_count=125,
        )
        secondary = self._make_file_info("/tmp/track.gpx", "gpx", FileRole.SECONDARY)

        mock_file_manager.get_files.return_value = [primary, secondary]
        mock_file_manager.get_primary_file.return_value = primary
        mock_file_manager.get_secondary_file.return_value = secondary

        cmd, _ = generate_cli_command(
            session_id="test-session",
            output_file="/tmp/output.mp4",
            layout="default-1920x1080",
            video_time_alignment="file-modified",
        )

        # Should use Mode 2 (Video + GPX), not Mode 4 (DJI meta)
        mock_convert.assert_not_called()
        assert "--gpx" in cmd
        assert "track.gpx" in cmd
        assert "--ts-dji-meta-source" not in cmd

    def test_dji_meta_video_no_dji_meta_uses_gopro_mode(self, mock_file_manager):
        """Video without has_dji_meta should use standard GoPro mode (Mode 1)."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.services.renderer import generate_cli_command

        primary = self._make_file_info(
            "/tmp/GoPro_video.MP4",
            "video",
            FileRole.PRIMARY,
            has_dji_meta=False,
        )

        mock_file_manager.get_files.return_value = [primary]
        mock_file_manager.get_primary_file.return_value = primary
        mock_file_manager.get_secondary_file.return_value = None

        cmd, _ = generate_cli_command(
            session_id="test-session",
            output_file="/tmp/output.mp4",
            layout="default-1920x1080",
        )

        # Should be Mode 1 (GoPro) - no --use-gpx-only, no --ts-dji-meta-source
        assert "--use-gpx-only" not in cmd
        assert "--ts-dji-meta-source" not in cmd


class TestWrapperArgsPreservedInCommandEndpoint:
    """Tests that command endpoint preserves wrapper args (not stripped).

    Since gpstitch-dashboard is now the entry point, wrapper args like --ts-srt-source,
    --ts-srt-video, and --ts-dji-meta-source are valid CLI args and must not be removed.
    """

    @pytest.fixture
    def mock_deps(self, monkeypatch):
        """Mock file_manager for command endpoint tests."""
        import gpstitch.api.command as cmd_module

        manager = MagicMock()
        monkeypatch.setattr(cmd_module, "file_manager", manager)
        manager.session_exists.return_value = True

        from gpstitch.models.schemas import FileInfo, FileRole

        primary = FileInfo(
            filename="video.mov",
            file_path="/tmp/video.mov",
            file_type="video",
            role=FileRole.PRIMARY,
        )
        manager.get_primary_file.return_value = primary
        return manager

    def test_srt_wrapper_args_preserved(self, mock_deps):
        """Command endpoint should preserve --ts-srt-source and --ts-srt-video in output."""
        cmd_with_wrapper_args = (
            "gpstitch-dashboard '/tmp/video.mov' '/tmp/output.mp4'"
            " --ts-srt-source '/tmp/telemetry.srt'"
            " --ts-srt-video '/tmp/video.mov'"
            " --layout default --overlay-size 1920x1080"
        )

        with patch(
            "gpstitch.api.command.generate_cli_command",
            return_value=(cmd_with_wrapper_args, []),
        ):
            import asyncio

            from gpstitch.api.command import generate_command
            from gpstitch.models.schemas import CommandRequest

            request = CommandRequest(
                session_id="test-session",
                layout="default-1920x1080",
                output_filename="/tmp/output.mp4",
            )
            response = asyncio.run(generate_command(request))

        assert "--ts-srt-source" in response.command
        assert "--ts-srt-video" in response.command

    def test_dji_meta_wrapper_arg_preserved(self, mock_deps):
        """Command endpoint should preserve --ts-dji-meta-source in output."""
        cmd_with_wrapper_args = (
            "gpstitch-dashboard '/tmp/DJI_video.MP4' '/tmp/output.mp4'"
            " --ts-dji-meta-source '/tmp/DJI_video.MP4'"
            " --use-gpx-only --gpx '/tmp/temp.gpx'"
        )

        with patch(
            "gpstitch.api.command.generate_cli_command",
            return_value=(cmd_with_wrapper_args, []),
        ):
            import asyncio

            from gpstitch.api.command import generate_command
            from gpstitch.models.schemas import CommandRequest

            request = CommandRequest(
                session_id="test-session",
                layout="default-1920x1080",
                output_filename="/tmp/output.mp4",
            )
            response = asyncio.run(generate_command(request))

        assert "--ts-dji-meta-source" in response.command

    def test_command_passed_through_unchanged(self, mock_deps):
        """Command endpoint should pass generate_cli_command output through without modification."""
        original_cmd = (
            "gpstitch-dashboard '/tmp/video.mov' '/tmp/output.mp4'"
            " --ts-srt-source '/tmp/t.srt' --ts-srt-video '/tmp/video.mov'"
            " --ts-dji-meta-source '/tmp/video.mov'"
            " --layout default --overlay-size 1920x1080"
        )

        with patch(
            "gpstitch.api.command.generate_cli_command",
            return_value=(original_cmd, []),
        ):
            import asyncio

            from gpstitch.api.command import generate_command
            from gpstitch.models.schemas import CommandRequest

            request = CommandRequest(
                session_id="test-session",
                layout="default-1920x1080",
                output_filename="/tmp/output.mp4",
            )
            response = asyncio.run(generate_command(request))

        assert response.command == original_cmd
