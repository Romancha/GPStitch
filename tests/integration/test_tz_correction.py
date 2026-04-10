"""Integration test: timezone auto-correction for non-GoPro cameras.

Uses a real MOV file (IMG_2927_tz_test.MOV) whose creation_time has been
shifted to simulate Insta360-style local-time-as-UTC, paired with the
existing hiking_activity.gpx fixture.

MOV creation_time: 2024-08-08T19:52:19Z (actually local UTC+3)
GPX range:         2024-08-08T16:51:57Z -> 2024-08-08T16:52:55Z
Expected:          corrected with offset -3.0h via system-tz or exhaustive cascade

Short-video-in-long-GPS-track scenario (Issue #9):
Video creation_time: 2026-04-09T09:45:39Z (local PDT written as UTC)
Video duration:      ~108s
GPX range:           2026-04-09T16:37:20Z -> 2026-04-09T17:58:15Z
System TZ:           PDT (UTC-7)
Expected:            corrected to 16:45:39Z via system-tz (+7h)
"""

import datetime
from unittest.mock import patch

from gpstitch.api.time_sync import _analyze_sync


def _mock_system_tz_utc_plus3():
    """Mock _get_system_tz_offset to return UTC+3 (simulates user in UTC+3 timezone)."""
    return patch(
        "gpstitch.services.renderer._get_system_tz_offset",
        return_value=datetime.timedelta(hours=3),
    )


class TestTimezoneAutoCorrection:
    def test_tz_correction_detects_utc_plus3_offset(self, integration_test_mov_tz_test, integration_test_run_gpx):
        """Real MOV + GPX: auto-detects +3h timezone offset and corrects via system-tz."""
        with _mock_system_tz_utc_plus3():
            result = _analyze_sync(
                video_path=integration_test_mov_tz_test,
                time_offset_seconds=0,
                gpx_path=integration_test_run_gpx,
            )

        assert result.source == "system-tz"
        assert result.tz_correction_hours == -3.0
        # Corrected video_start should be 16:52:19 UTC
        assert "2024-08-08T16:52:19" in result.video_start

    def test_no_correction_without_gpx(self, integration_test_mov_tz_test):
        """Without GPX file, no tz-correction is possible — falls back to media-created."""
        result = _analyze_sync(
            video_path=integration_test_mov_tz_test,
            time_offset_seconds=0,
            gpx_path=None,
        )

        assert result.source == "media-created"
        assert result.tz_correction_hours is None

    def test_time_offset_applied_on_top_of_correction(self, integration_test_mov_tz_test, integration_test_run_gpx):
        """Time offset is applied after tz-correction."""
        with _mock_system_tz_utc_plus3():
            result = _analyze_sync(
                video_path=integration_test_mov_tz_test,
                time_offset_seconds=5,
                gpx_path=integration_test_run_gpx,
            )

        assert result.source == "system-tz"
        assert result.tz_correction_hours == -3.0
        # 16:52:19 + 5s = 16:52:24
        assert "2024-08-08T16:52:24" in result.video_start

    def test_tz_correction_overlap_has_points(self, integration_test_mov_tz_overlap, integration_test_run_gpx):
        """After tz-correction, video overlaps GPS track and has data points.

        Uses IMG_2927_tz_overlap_test.MOV (creation_time=19:52:16Z).
        Corrected window: 16:52:16 → 16:52:19 captures GPS points at 16:52:16 and 16:52:18.
        """
        with _mock_system_tz_utc_plus3():
            result = _analyze_sync(
                video_path=integration_test_mov_tz_overlap,
                time_offset_seconds=0,
                gpx_path=integration_test_run_gpx,
            )

        assert result.source == "system-tz"
        assert result.tz_correction_hours == -3.0
        assert result.overlap is not None
        assert result.overlap.points >= 2

    def test_original_mov_no_correction(self, integration_test_mov_video, integration_test_run_gpx):
        """Original MOV (correct creation_time) should NOT trigger tz-correction."""
        result = _analyze_sync(
            video_path=integration_test_mov_video,
            time_offset_seconds=0,
            gpx_path=integration_test_run_gpx,
        )

        assert result.source == "media-created"
        assert result.tz_correction_hours is None


def _mock_system_tz_pdt():
    """Mock _get_system_tz_offset to return UTC-7 (PDT)."""
    return patch(
        "gpstitch.services.renderer._get_system_tz_offset",
        return_value=datetime.timedelta(hours=-7),
    )


def _mock_system_tz_utc():
    """Mock _get_system_tz_offset to return UTC+0."""
    return patch(
        "gpstitch.services.renderer._get_system_tz_offset",
        return_value=datetime.timedelta(hours=0),
    )


# Short-video-in-long-track scenario constants (Issue #9)
_SHORT_VIDEO_CREATION_TIME = datetime.datetime(2026, 4, 9, 9, 45, 39, tzinfo=datetime.UTC)
_SHORT_VIDEO_DURATION_SEC = 108.34


def _mock_short_video_metadata():
    """Mock video metadata extraction to return short-video fixture values."""
    return (
        patch(
            "gpstitch.api.time_sync._extract_creation_time",
            return_value=_SHORT_VIDEO_CREATION_TIME,
        ),
        patch(
            "gpstitch.api.time_sync._get_video_duration",
            return_value=_SHORT_VIDEO_DURATION_SEC,
        ),
    )


class TestShortVideoLongTrackTzCorrection:
    """Integration tests for short-video-in-long-GPS-track scenario (Issue #9).

    Short video (108s) inside a long GPS track (~80 min).
    Video creation_time is local PDT written as UTC.
    Uses real GPX parsing with mocked video metadata.
    """

    def test_system_tz_pdt_corrects_to_utc(self, integration_test_mov_video, integration_test_long_gps_track_tz_test):
        """System TZ PDT (-7h) → corrects creation_time by +7h.

        creation_time 09:45:39Z + 7h = 16:45:39Z, which falls inside GPS 16:37:20-17:58:15.
        """
        mock_ct, mock_dur = _mock_short_video_metadata()
        with mock_ct, mock_dur, _mock_system_tz_pdt():
            result = _analyze_sync(
                video_path=integration_test_mov_video,
                time_offset_seconds=0,
                gpx_path=integration_test_long_gps_track_tz_test,
            )

        assert result.source == "system-tz"
        assert result.tz_correction_hours == 7.0
        assert "2026-04-09T16:45:39" in result.video_start
        assert result.overlap is not None
        assert result.overlap.points > 0
        assert result.suggested_manual_offset_seconds is None

    def test_system_tz_utc_fails_with_suggestion(
        self, integration_test_mov_video, integration_test_long_gps_track_tz_test
    ):
        """When system TZ is UTC (0h), exhaustive finds 2 candidates (+7h, +8h) → failed path.

        Video 09:45:39-09:47:27 (108s). GPS 16:37:20-17:58:15.
        +7h → 16:45:39-16:47:27 (inside GPS) ✓
        +8h → 17:45:39-17:47:27 (inside GPS) ✓
        System TZ=UTC means correction=0h, not among candidates → ambiguous → failed.
        """
        mock_ct, mock_dur = _mock_short_video_metadata()
        with mock_ct, mock_dur, _mock_system_tz_utc():
            result = _analyze_sync(
                video_path=integration_test_mov_video,
                time_offset_seconds=0,
                gpx_path=integration_test_long_gps_track_tz_test,
            )

        assert result.source == "failed"
        assert result.tz_correction_hours is None
        assert result.suggested_manual_offset_seconds is not None
        # The suggestion should be one of the valid offsets (7h=25200s or 8h=28800s)
        assert result.suggested_manual_offset_seconds in (25200, 28800)
