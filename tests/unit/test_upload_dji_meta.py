"""Unit tests for DJI meta GPS handling in upload flow."""

from unittest.mock import patch

import pytest

from gpstitch.models.schemas import FileInfo, FileRole, VideoMetadata


class TestDjiActionUploadSkipsSecondary:
    """Verify DJI Action videos with embedded GPS skip secondary file detection."""

    def _make_video_metadata(self, has_dji_meta: bool = False, dji_meta_point_count: int | None = None):
        return VideoMetadata(
            width=1920,
            height=1080,
            duration_seconds=5.0,
            frame_count=125,
            frame_rate=25.0,
            has_gps=False,
            has_dji_meta=has_dji_meta,
            dji_meta_point_count=dji_meta_point_count,
        )

    def _make_file_info(self, video_path, video_metadata):
        return FileInfo(
            filename=video_path.name,
            file_path=str(video_path),
            file_type="video",
            role=FileRole.PRIMARY,
            video_metadata=video_metadata,
        )

    @pytest.mark.anyio
    async def test_dji_action_video_skips_secondary_autodetect(self, tmp_path):
        """DJI Action video with has_dji_meta=True should not auto-detect secondary SRT."""
        video_path = tmp_path / "DJI_20260315_0001.MP4"
        video_path.write_bytes(b"fake video")
        srt_path = tmp_path / "DJI_20260315_0001.SRT"
        srt_path.write_text("fake srt")

        video_metadata = self._make_video_metadata(has_dji_meta=True, dji_meta_point_count=125)
        file_info = self._make_file_info(video_path, video_metadata)

        with (
            patch("gpstitch.api.upload.settings") as mock_settings,
            patch("gpstitch.api.upload.file_manager") as mock_fm,
            patch("gpstitch.api.upload.extract_video_metadata", return_value=video_metadata),
            patch("gpstitch.api.upload.get_file_type", return_value="video"),
            patch("gpstitch.api.upload._find_matching_telemetry") as mock_find_telemetry,
        ):
            mock_settings.local_mode = True
            mock_settings.allowed_extensions = {".mp4", ".MP4", ".gpx", ".srt"}
            mock_fm.session_exists.return_value = False
            mock_fm.create_local_session.return_value = "local:test123"
            mock_fm.add_file.return_value = file_info

            from gpstitch.api.upload import use_local_file
            from gpstitch.models.schemas import LocalFileRequest

            request = LocalFileRequest(file_path=str(video_path))
            response = await use_local_file(request)

            mock_find_telemetry.assert_not_called()
            assert len(response.files) == 1

    @pytest.mark.anyio
    async def test_regular_video_still_autodetects_secondary(self, tmp_path):
        """Regular video without DJI meta should still auto-detect secondary telemetry."""
        video_path = tmp_path / "GH010001.MP4"
        video_path.write_bytes(b"fake video")

        video_metadata = self._make_video_metadata(has_dji_meta=False)
        file_info = self._make_file_info(video_path, video_metadata)

        with (
            patch("gpstitch.api.upload.settings") as mock_settings,
            patch("gpstitch.api.upload.file_manager") as mock_fm,
            patch("gpstitch.api.upload.extract_video_metadata", return_value=video_metadata),
            patch("gpstitch.api.upload.get_file_type", return_value="video"),
            patch("gpstitch.api.upload._find_matching_telemetry", return_value=None) as mock_find_telemetry,
            patch("gpstitch.api.upload.analyze_gps_quality", return_value=None),
        ):
            mock_settings.local_mode = True
            mock_settings.allowed_extensions = {".mp4", ".MP4"}
            mock_fm.session_exists.return_value = False
            mock_fm.create_local_session.return_value = "local:test456"
            mock_fm.add_file.return_value = file_info

            from gpstitch.api.upload import use_local_file
            from gpstitch.models.schemas import LocalFileRequest

            request = LocalFileRequest(file_path=str(video_path))
            await use_local_file(request)

            mock_find_telemetry.assert_called_once()
