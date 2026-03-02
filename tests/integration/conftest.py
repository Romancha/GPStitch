"""Integration test fixtures."""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Original mtime of DJI test video (git clone does not preserve file timestamps).
# Value from: DJI_20250721102743_0001_D.MP4 recorded 2025-07-21, mtime = end of recording.
_DJI_VIDEO_ORIGINAL_MTIME = datetime(2025, 7, 21, 7, 27, 45, tzinfo=UTC).timestamp()


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
