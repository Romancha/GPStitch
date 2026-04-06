"""Integration test: timezone auto-correction for non-GoPro cameras.

Uses a real MOV file (IMG_2927_tz_test.MOV) whose creation_time has been
shifted to simulate Insta360-style local-time-as-UTC, paired with the
existing hiking_activity.gpx fixture.

MOV creation_time: 2024-08-08T19:52:19Z (actually local UTC+3)
GPX range:         2024-08-08T16:51:57Z -> 2024-08-08T16:52:55Z
Expected:          tz-corrected with offset -3.0h
"""

from gpstitch.api.time_sync import _analyze_sync


class TestTimezoneAutoCorrection:
    def test_tz_correction_detects_utc_plus3_offset(self, integration_test_mov_tz_test, integration_test_run_gpx):
        """Real MOV + GPX: auto-detects +3h timezone offset and corrects."""
        result = _analyze_sync(
            video_path=integration_test_mov_tz_test,
            time_offset_seconds=0,
            gpx_path=integration_test_run_gpx,
        )

        assert result.source == "tz-corrected"
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
        result = _analyze_sync(
            video_path=integration_test_mov_tz_test,
            time_offset_seconds=5,
            gpx_path=integration_test_run_gpx,
        )

        assert result.source == "tz-corrected"
        assert result.tz_correction_hours == -3.0
        # 16:52:19 + 5s = 16:52:24
        assert "2024-08-08T16:52:24" in result.video_start

    def test_tz_correction_overlap_has_points(self, integration_test_mov_tz_overlap, integration_test_run_gpx):
        """After tz-correction, video overlaps GPS track and has data points.

        Uses IMG_2927_tz_overlap_test.MOV (creation_time=19:52:16Z).
        Corrected window: 16:52:16 → 16:52:19 captures GPS points at 16:52:16 and 16:52:18.
        """
        result = _analyze_sync(
            video_path=integration_test_mov_tz_overlap,
            time_offset_seconds=0,
            gpx_path=integration_test_run_gpx,
        )

        assert result.source == "tz-corrected"
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
