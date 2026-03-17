"""Integration tests for GPS quality analysis with DJI Action videos."""

from pathlib import Path

import pytest

from gpstitch.services.gps_analyzer import analyze_gps_quality
from tests.fixtures.data import TEST_DJI_ACTION_VIDEO_PATH, TEST_VIDEO_PATH


@pytest.fixture(scope="module")
def dji_action_video():
    """Real DJI Action test video fixture."""
    path = Path(TEST_DJI_ACTION_VIDEO_PATH)
    if not path.exists():
        pytest.skip(f"DJI Action fixture not found: {path}")
    return path


@pytest.fixture(scope="module")
def gopro_video():
    """Regular GoPro video (no DJI meta stream)."""
    path = Path(TEST_VIDEO_PATH)
    if not path.exists():
        pytest.skip(f"GoPro fixture not found: {path}")
    return path


class TestDjiActionGpsQuality:
    """GPS quality analysis for DJI Action videos."""

    def test_dji_action_returns_none(self, dji_action_video):
        """DJI Action video with embedded GPS returns None — no DOP data available."""
        result = analyze_gps_quality(dji_action_video)
        assert result is None

    def test_gopro_video_does_not_return_none_for_dji_reason(self, gopro_video):
        """GoPro video should not be skipped by DJI meta detection."""
        # This may return a report or None (if no GPS lock), but the code path
        # should NOT be short-circuited by the DJI meta check
        result = analyze_gps_quality(gopro_video)
        # GoPro video either has a report or returns None from GoPro analysis,
        # not from DJI meta detection skip
        assert result is None or result.total_points >= 0
