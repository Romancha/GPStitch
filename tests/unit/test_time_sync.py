"""Unit tests for time_sync API — _analyze_sync() source detection and tz_correction_hours."""

import datetime
from pathlib import Path
from unittest.mock import patch

from gpstitch.api.time_sync import _analyze_sync
from gpstitch.services.renderer import CorrectionResult


class TestAnalyzeSyncTzCorrection:
    """Tests for _analyze_sync() detecting timezone auto-correction from _validate_creation_time()."""

    # GPS range: 18:10:23 -> 20:02:53 UTC on 2026-02-06
    GPS_RANGE = (
        datetime.datetime(2026, 2, 6, 18, 10, 23, tzinfo=datetime.UTC).timestamp(),
        datetime.datetime(2026, 2, 6, 20, 2, 53, tzinfo=datetime.UTC).timestamp(),
    )

    VIDEO_DURATION = 50.0

    # Insta360 scenario: creation_time is local (UTC+7) stored as UTC
    # Camera records at 02:06:38 local (UTC+7) = 19:06:38 UTC
    WRONG_CT_INSTA360 = datetime.datetime(2026, 2, 7, 2, 6, 38, tzinfo=datetime.UTC)
    CORRECTED_CT_INSTA360 = CorrectionResult(
        time=datetime.datetime(2026, 2, 6, 19, 6, 38, tzinfo=datetime.UTC),
        correction_type="system-tz",
        tz_correction_hours=-7.0,
    )

    def _mock_video_duration(self):
        """Mock _get_video_duration to return VIDEO_DURATION."""
        return patch("gpstitch.api.time_sync._get_video_duration", return_value=self.VIDEO_DURATION)

    def _mock_extract_creation_time(self, ct):
        """Mock _extract_creation_time to return given creation_time."""
        return patch("gpstitch.api.time_sync._extract_creation_time", return_value=ct)

    def _mock_validate_creation_time(self, result):
        """Mock _validate_creation_time to return given CorrectionResult."""
        return patch("gpstitch.api.time_sync._validate_creation_time", return_value=result)

    def _mock_gps_range(self, gps_range=None):
        """Mock _get_gps_time_range."""
        return patch("gpstitch.api.time_sync._get_gps_time_range", return_value=gps_range or self.GPS_RANGE)

    def _mock_calculate_overlap(self):
        """Mock _calculate_overlap to return None (not relevant for this test)."""
        return patch("gpstitch.api.time_sync._calculate_overlap", return_value=None)

    def test_tz_corrected_source_and_hours(self):
        """When _validate_creation_time applies system-tz correction, source='system-tz' and hours set."""
        with (
            self._mock_video_duration(),
            self._mock_extract_creation_time(self.WRONG_CT_INSTA360),
            self._mock_validate_creation_time(self.CORRECTED_CT_INSTA360),
            self._mock_gps_range(),
            self._mock_calculate_overlap(),
        ):
            result = _analyze_sync(Path("/tmp/video.mp4"), 0, Path("/tmp/track.fit"))

        assert result.source == "system-tz"
        assert result.tz_correction_hours == -7.0
        assert result.video_start == self.CORRECTED_CT_INSTA360.time.isoformat()

    def test_tz_corrected_non_whole_hour(self):
        """UTC+5:45 (Nepal) correction: source='exhaustive', hours==-5.75."""
        wrong_ct = datetime.datetime(2026, 2, 7, 0, 51, 38, tzinfo=datetime.UTC)
        corrected = CorrectionResult(
            time=datetime.datetime(2026, 2, 6, 19, 6, 38, tzinfo=datetime.UTC),
            correction_type="exhaustive",
            tz_correction_hours=-5.75,
        )

        with (
            self._mock_video_duration(),
            self._mock_extract_creation_time(wrong_ct),
            self._mock_validate_creation_time(corrected),
            self._mock_gps_range(),
            self._mock_calculate_overlap(),
        ):
            result = _analyze_sync(Path("/tmp/video.mp4"), 0, Path("/tmp/track.fit"))

        assert result.source == "exhaustive"
        assert result.tz_correction_hours == -5.75

    def test_mtime_correction_source_mtime(self):
        """When _validate_creation_time uses mtime, source='mtime'."""
        wrong_ct = datetime.datetime(2026, 2, 6, 11, 34, 47, tzinfo=datetime.UTC)
        mtime_result = CorrectionResult(
            time=datetime.datetime(2026, 2, 6, 19, 34, 50, tzinfo=datetime.UTC),
            correction_type="mtime",
        )

        with (
            self._mock_video_duration(),
            self._mock_extract_creation_time(wrong_ct),
            self._mock_validate_creation_time(mtime_result),
            self._mock_gps_range(),
            self._mock_calculate_overlap(),
        ):
            result = _analyze_sync(Path("/tmp/video.mp4"), 0, Path("/tmp/track.fit"))

        assert result.source == "mtime"
        assert result.tz_correction_hours is None

    def test_no_correction_source_media_created(self):
        """When creation_time is unchanged (GoPro), source='media-created'."""
        correct_ct = datetime.datetime(2026, 2, 6, 19, 34, 47, tzinfo=datetime.UTC)
        no_correction = CorrectionResult(time=correct_ct)

        with (
            self._mock_video_duration(),
            self._mock_extract_creation_time(correct_ct),
            self._mock_validate_creation_time(no_correction),
            self._mock_gps_range(),
            self._mock_calculate_overlap(),
        ):
            result = _analyze_sync(Path("/tmp/video.mp4"), 0, Path("/tmp/track.fit"))

        assert result.source == "media-created"
        assert result.tz_correction_hours is None

    def test_no_creation_time_source_file_created(self):
        """When no creation_time available, source='file-created', no tz_correction."""
        file_ctime = datetime.datetime(2026, 2, 6, 19, 34, 47, tzinfo=datetime.UTC)

        with (
            self._mock_video_duration(),
            self._mock_extract_creation_time(None),
            self._mock_gps_range(),
            self._mock_calculate_overlap(),
            patch("gopro_overlay.ffmpeg_gopro.filestat") as mock_filestat,
        ):
            mock_filestat.return_value.ctime = file_ctime
            result = _analyze_sync(Path("/tmp/video.mp4"), 0, Path("/tmp/track.fit"))

        assert result.source == "file-created"
        assert result.tz_correction_hours is None

    def test_system_tz_source_and_correction_reason(self):
        """When correction_type='system-tz', source='system-tz', correction_reason mentions system timezone."""
        with (
            self._mock_video_duration(),
            self._mock_extract_creation_time(self.WRONG_CT_INSTA360),
            self._mock_validate_creation_time(self.CORRECTED_CT_INSTA360),
            self._mock_gps_range(),
            self._mock_calculate_overlap(),
        ):
            result = _analyze_sync(Path("/tmp/video.mp4"), 0, Path("/tmp/track.fit"))

        assert result.source == "system-tz"
        assert result.tz_correction_hours == -7.0
        assert result.correction_reason is not None
        assert "system timezone" in result.correction_reason.lower()
        assert result.suggested_manual_offset_seconds is None

    def test_exhaustive_source_and_correction_reason(self):
        """When correction_type='exhaustive', source='exhaustive', correction_reason describes overlap search."""
        wrong_ct = datetime.datetime(2026, 2, 7, 0, 51, 38, tzinfo=datetime.UTC)
        corrected = CorrectionResult(
            time=datetime.datetime(2026, 2, 6, 19, 6, 38, tzinfo=datetime.UTC),
            correction_type="exhaustive",
            tz_correction_hours=-5.75,
        )

        with (
            self._mock_video_duration(),
            self._mock_extract_creation_time(wrong_ct),
            self._mock_validate_creation_time(corrected),
            self._mock_gps_range(),
            self._mock_calculate_overlap(),
        ):
            result = _analyze_sync(Path("/tmp/video.mp4"), 0, Path("/tmp/track.fit"))

        assert result.source == "exhaustive"
        assert result.tz_correction_hours == -5.75
        assert result.correction_reason is not None
        assert "overlap" in result.correction_reason.lower() or "search" in result.correction_reason.lower()
        assert result.suggested_manual_offset_seconds is None

    def test_failed_source_with_suggested_offset(self):
        """When auto-correction fails with a suggestion, source='failed', suggested offset set."""
        correct_ct = datetime.datetime(2026, 2, 6, 11, 34, 47, tzinfo=datetime.UTC)
        failed_result = CorrectionResult(
            time=correct_ct,
            correction_type=None,
            suggested_offset_seconds=25200,  # 7 hours in seconds
        )

        with (
            self._mock_video_duration(),
            self._mock_extract_creation_time(correct_ct),
            self._mock_validate_creation_time(failed_result),
            self._mock_gps_range(),
            self._mock_calculate_overlap(),
        ):
            result = _analyze_sync(Path("/tmp/video.mp4"), 0, Path("/tmp/track.fit"))

        assert result.source == "failed"
        assert result.tz_correction_hours is None
        assert result.suggested_manual_offset_seconds == 25200

    def test_no_correction_gopro_has_no_new_fields(self):
        """GoPro (no correction): source='media-created', no correction_reason, no suggestion."""
        correct_ct = datetime.datetime(2026, 2, 6, 19, 34, 47, tzinfo=datetime.UTC)
        no_correction = CorrectionResult(time=correct_ct)

        with (
            self._mock_video_duration(),
            self._mock_extract_creation_time(correct_ct),
            self._mock_validate_creation_time(no_correction),
            self._mock_gps_range(),
            self._mock_calculate_overlap(),
        ):
            result = _analyze_sync(Path("/tmp/video.mp4"), 0, Path("/tmp/track.fit"))

        assert result.source == "media-created"
        assert result.correction_reason is None
        assert result.suggested_manual_offset_seconds is None

    def test_tz_corrected_with_time_offset_applied(self):
        """Time offset is applied on top of system-tz corrected time."""
        with (
            self._mock_video_duration(),
            self._mock_extract_creation_time(self.WRONG_CT_INSTA360),
            self._mock_validate_creation_time(self.CORRECTED_CT_INSTA360),
            self._mock_gps_range(),
            self._mock_calculate_overlap(),
        ):
            result = _analyze_sync(Path("/tmp/video.mp4"), 30, Path("/tmp/track.fit"))

        assert result.source == "system-tz"
        assert result.tz_correction_hours == -7.0
        # video_start should have the +30s offset applied
        expected_start = self.CORRECTED_CT_INSTA360.time + datetime.timedelta(seconds=30)
        assert result.video_start == expected_start.isoformat()
