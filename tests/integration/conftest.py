"""Integration test fixtures."""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Original mtime of DJI test video (git clone does not preserve file timestamps).
# Value from: DJI_20250723102139_0001_D.MP4 recorded 2025-07-23, mtime = end of recording.
_DJI_VIDEO_ORIGINAL_MTIME = datetime(2025, 7, 23, 7, 21, 42, tzinfo=UTC).timestamp()


@pytest.fixture(scope="module")
def integration_test_video():
    """Real GoPro test video for integration tests (module-scoped for efficiency)."""
    from tests.fixtures.data import TEST_VIDEO_PATH

    path = Path(TEST_VIDEO_PATH)
    if not path.exists():
        pytest.skip(f"Integration test video not found: {path}")
    return path


@pytest.fixture(scope="module")
def integration_test_mov_video():
    """MOV video without GPS for integration tests (module-scoped for efficiency)."""
    from tests.fixtures.data import TEST_MOV_VIDEO_PATH

    path = Path(TEST_MOV_VIDEO_PATH)
    if not path.exists():
        pytest.skip(f"Integration test MOV video not found: {path}")
    return path


@pytest.fixture(scope="module")
def integration_test_run_gpx():
    """Real GPX file with run activity data (module-scoped for efficiency)."""
    from tests.fixtures.data import TEST_RUN_GPX_PATH

    path = Path(TEST_RUN_GPX_PATH)
    if not path.exists():
        pytest.skip(f"Integration test GPX not found: {path}")
    return path


@pytest.fixture(scope="module")
def integration_test_dji_video():
    """Real DJI test video for integration tests (module-scoped for efficiency)."""
    from tests.fixtures.data import TEST_DJI_VIDEO_PATH

    path = Path(TEST_DJI_VIDEO_PATH)
    if not path.exists():
        pytest.skip(f"Integration test DJI video not found: {path}")
    # Restore original mtime that git clone does not preserve
    os.utime(path, (_DJI_VIDEO_ORIGINAL_MTIME, _DJI_VIDEO_ORIGINAL_MTIME))
    return path


@pytest.fixture(scope="module")
def integration_test_dji_srt():
    """Real DJI SRT telemetry file for integration tests (module-scoped for efficiency)."""
    from tests.fixtures.data import TEST_DJI_SRT_PATH

    path = Path(TEST_DJI_SRT_PATH)
    if not path.exists():
        pytest.skip(f"Integration test DJI SRT not found: {path}")
    return path


# Original mtime of DJI Action test video with embedded GPS.
# Set to match the first GPS timestamp so file-modified alignment works.
_DJI_ACTION_VIDEO_ORIGINAL_MTIME = datetime(2026, 3, 15, 23, 58, 14, tzinfo=UTC).timestamp()


@pytest.fixture(scope="module")
def integration_test_dji_action_video():
    """Real DJI Action video with embedded GPS for integration tests."""
    from tests.fixtures.data import TEST_DJI_ACTION_VIDEO_PATH

    path = Path(TEST_DJI_ACTION_VIDEO_PATH)
    if not path.exists():
        pytest.skip(f"Integration test DJI Action video not found: {path}")
    # Restore original mtime that git clone does not preserve
    os.utime(path, (_DJI_ACTION_VIDEO_ORIGINAL_MTIME, _DJI_ACTION_VIDEO_ORIGINAL_MTIME))
    return path


# MOV fixture with creation_time set to local time (UTC+3) stored as UTC.
# Real creation: 2024-08-08T16:52:19 UTC, but metadata says 19:52:19Z.
# mtime also set to wrong time so mtime fallback doesn't trigger.
_MOV_TZ_TEST_WRONG_MTIME = datetime(2024, 8, 8, 19, 52, 19, tzinfo=UTC).timestamp()


@pytest.fixture(scope="module")
def integration_test_mov_tz_test():
    """MOV video with local time stored as UTC for timezone auto-correction tests."""
    from tests.fixtures.data import TEST_MOV_TZ_TEST_PATH

    path = Path(TEST_MOV_TZ_TEST_PATH)
    if not path.exists():
        pytest.skip(f"Integration test MOV tz-test not found: {path}")
    # Restore wrong mtime (git clone does not preserve file timestamps)
    os.utime(path, (_MOV_TZ_TEST_WRONG_MTIME, _MOV_TZ_TEST_WRONG_MTIME))
    return path


# Same as above but creation_time=19:52:16Z so corrected window [16:52:16, 16:52:19]
# overlaps GPS points at 16:52:16 and 16:52:18.
_MOV_TZ_OVERLAP_TEST_WRONG_MTIME = datetime(2024, 8, 8, 19, 52, 16, tzinfo=UTC).timestamp()


@pytest.fixture(scope="module")
def integration_test_mov_tz_overlap():
    """MOV with shifted creation_time that overlaps GPS points after tz-correction."""
    from tests.fixtures.data import TEST_MOV_TZ_OVERLAP_TEST_PATH

    path = Path(TEST_MOV_TZ_OVERLAP_TEST_PATH)
    if not path.exists():
        pytest.skip(f"Integration test MOV tz-overlap not found: {path}")
    os.utime(path, (_MOV_TZ_OVERLAP_TEST_WRONG_MTIME, _MOV_TZ_OVERLAP_TEST_WRONG_MTIME))
    return path
