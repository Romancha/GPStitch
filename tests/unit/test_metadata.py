"""Unit tests for metadata extraction service."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from gpstitch.services.metadata import extract_video_metadata, get_display_dimensions, get_file_type, get_video_rotation


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


class TestExtractVideoMetadataDjiMeta:
    """Tests for DJI meta detection in extract_video_metadata."""

    def _mock_recording(self):
        """Create a mock recording with video info."""
        mock_video = MagicMock()
        mock_video.dimension.x = 1920
        mock_video.dimension.y = 1080
        mock_video.duration.millis.return_value = 5000
        mock_video.frame_count = 125
        mock_video.frame_rate.return_value = 25.0
        mock_recording = MagicMock()
        mock_recording.video = mock_video
        mock_recording.data = None  # no GoPro GPS
        return mock_recording

    @patch("gpstitch.services.metadata.get_video_rotation", return_value=0)
    def test_dji_action_video_has_dji_meta_true(self, _mock_rotation):
        """DJI Action video with djmd stream should have has_dji_meta=True."""
        mock_recording = self._mock_recording()

        # Import dji_meta_parser BEFORE patching FFMPEG to avoid poisoning
        # the module-level FFMPEG binding (see: import-time mock capture bug)
        import gpstitch.services.dji_meta_parser  # noqa: F811

        with (
            patch("gopro_overlay.ffmpeg.FFMPEG"),
            patch("gopro_overlay.ffmpeg_gopro.FFMPEGGoPro") as mock_gopro_cls,
            patch.object(gpstitch.services.dji_meta_parser, "detect_dji_meta_stream", return_value=2),
            patch.object(
                gpstitch.services.dji_meta_parser,
                "get_dji_meta_metadata",
                return_value={"gps_point_count": 125, "duration_seconds": 5.0},
            ),
        ):
            mock_gopro_cls.return_value.find_recording.return_value = mock_recording
            metadata = extract_video_metadata(Path("/fake/DJI_ACTION.MP4"))

        assert metadata is not None
        assert metadata.has_dji_meta is True
        assert metadata.dji_meta_point_count == 125

    @patch("gpstitch.services.metadata.get_video_rotation", return_value=0)
    def test_regular_video_has_dji_meta_false(self, _mock_rotation):
        """Regular video without djmd stream should have has_dji_meta=False."""
        mock_recording = self._mock_recording()
        mock_recording.data = MagicMock()  # has GoPro GPS

        import gpstitch.services.dji_meta_parser  # noqa: F811

        with (
            patch("gopro_overlay.ffmpeg.FFMPEG"),
            patch("gopro_overlay.ffmpeg_gopro.FFMPEGGoPro") as mock_gopro_cls,
            patch.object(gpstitch.services.dji_meta_parser, "detect_dji_meta_stream", return_value=None),
        ):
            mock_gopro_cls.return_value.find_recording.return_value = mock_recording
            metadata = extract_video_metadata(Path("/fake/gopro.MP4"))

        assert metadata is not None
        assert metadata.has_dji_meta is False
        assert metadata.dji_meta_point_count is None

    @patch("gpstitch.services.metadata.get_video_rotation", return_value=0)
    def test_dji_meta_detection_failure_doesnt_break_extraction(self, _mock_rotation):
        """If DJI meta detection raises, metadata extraction should still succeed."""
        mock_recording = self._mock_recording()

        import gpstitch.services.dji_meta_parser  # noqa: F811

        with (
            patch("gopro_overlay.ffmpeg.FFMPEG"),
            patch("gopro_overlay.ffmpeg_gopro.FFMPEGGoPro") as mock_gopro_cls,
            patch.object(gpstitch.services.dji_meta_parser, "detect_dji_meta_stream", side_effect=RuntimeError("boom")),
        ):
            mock_gopro_cls.return_value.find_recording.return_value = mock_recording
            metadata = extract_video_metadata(Path("/fake/video.MP4"))

        assert metadata is not None
        assert metadata.has_dji_meta is False
        assert metadata.dji_meta_point_count is None
