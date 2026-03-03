"""Unit tests for metadata extraction service."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from gpstitch.services.metadata import get_display_dimensions, get_file_type, get_video_rotation


class TestGetDisplayDimensions:
    """Tests for display dimension calculation with rotation."""

    def test_no_rotation(self):
        """No rotation should return original dimensions."""
        assert get_display_dimensions(1920, 1080, 0) == (1920, 1080)

    def test_rotation_90(self):
        """90-degree rotation should swap width and height."""
        assert get_display_dimensions(1920, 1080, 90) == (1080, 1920)

    def test_rotation_180(self):
        """180-degree rotation should keep original dimensions."""
        assert get_display_dimensions(1920, 1080, 180) == (1920, 1080)

    def test_rotation_270(self):
        """270-degree rotation should swap width and height."""
        assert get_display_dimensions(1920, 1080, 270) == (1080, 1920)


class TestGetVideoRotation:
    """Tests for video rotation detection from ffprobe data."""

    def test_rotation_from_side_data(self):
        """Should detect rotation from side_data_list."""
        ffprobe_output = {
            "streams": [
                {
                    "codec_type": "video",
                    "side_data_list": [{"rotation": -90}],
                }
            ]
        }
        mock_ffmpeg_cls = MagicMock()
        mock_ffmpeg_cls.return_value.ffprobe.return_value.invoke.return_value.stdout = json.dumps(ffprobe_output)

        with patch("gopro_overlay.ffmpeg.FFMPEG", mock_ffmpeg_cls):
            rotation = get_video_rotation(Path("/fake/video.mov"))

        assert rotation == 90

    def test_rotation_from_tags(self):
        """Should detect rotation from tags.rotate."""
        ffprobe_output = {
            "streams": [
                {
                    "codec_type": "video",
                    "tags": {"rotate": "270"},
                }
            ]
        }
        mock_ffmpeg_cls = MagicMock()
        mock_ffmpeg_cls.return_value.ffprobe.return_value.invoke.return_value.stdout = json.dumps(ffprobe_output)

        with patch("gopro_overlay.ffmpeg.FFMPEG", mock_ffmpeg_cls):
            rotation = get_video_rotation(Path("/fake/video.mov"))

        assert rotation == 270

    def test_no_rotation_data(self):
        """Should return 0 when no rotation info is present."""
        ffprobe_output = {
            "streams": [
                {
                    "codec_type": "video",
                }
            ]
        }
        mock_ffmpeg_cls = MagicMock()
        mock_ffmpeg_cls.return_value.ffprobe.return_value.invoke.return_value.stdout = json.dumps(ffprobe_output)

        with patch("gopro_overlay.ffmpeg.FFMPEG", mock_ffmpeg_cls):
            rotation = get_video_rotation(Path("/fake/video.mov"))

        assert rotation == 0

    def test_unexpected_rotation_value_returns_zero(self):
        """Should return 0 for rotation values outside {0, 90, 180, 270}."""
        ffprobe_output = {
            "streams": [
                {
                    "codec_type": "video",
                    "side_data_list": [{"rotation": -45}],
                }
            ]
        }
        mock_ffmpeg_cls = MagicMock()
        mock_ffmpeg_cls.return_value.ffprobe.return_value.invoke.return_value.stdout = json.dumps(ffprobe_output)

        with patch("gopro_overlay.ffmpeg.FFMPEG", mock_ffmpeg_cls):
            rotation = get_video_rotation(Path("/fake/video.mov"))

        assert rotation == 0

    def test_ffprobe_error(self):
        """Should return 0 when ffprobe raises an exception."""
        mock_ffmpeg_cls = MagicMock()
        mock_ffmpeg_cls.return_value.ffprobe.return_value.invoke.side_effect = RuntimeError("ffprobe failed")

        with patch("gopro_overlay.ffmpeg.FFMPEG", mock_ffmpeg_cls):
            rotation = get_video_rotation(Path("/fake/video.mov"))

        assert rotation == 0


class TestGetFileType:
    """Tests for file type detection."""

    def test_mov_detected_as_video(self):
        """MOV extension should be detected as video."""
        assert get_file_type(Path("test.mov")) == "video"

    def test_mov_uppercase(self):
        """Uppercase MOV extension should be detected as video."""
        assert get_file_type(Path("test.MOV")) == "video"

    def test_mp4_detected_as_video(self):
        """MP4 extension should be detected as video."""
        assert get_file_type(Path("test.mp4")) == "video"

    def test_gpx_detected(self):
        """GPX extension should be detected."""
        assert get_file_type(Path("test.gpx")) == "gpx"

    def test_fit_detected(self):
        """FIT extension should be detected."""
        assert get_file_type(Path("test.fit")) == "fit"

    def test_unknown_extension(self):
        """Unknown extension should return 'unknown'."""
        assert get_file_type(Path("test.txt")) == "unknown"
