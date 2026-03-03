"""Pytest configuration and fixtures."""

import shutil
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from gpstitch.app import app
from tests.fixtures.factories import (
    create_editor_layout,
    create_file_info,
    create_gpx_fit_metadata,
    create_job,
    create_render_config,
    create_video_metadata,
    create_widget_instance,
)


def pytest_collection_modifyitems(items):
    """Reorder tests to run e2e tests last.

    This prevents Playwright from polluting the event loop for async tests.
    See: https://github.com/microsoft/playwright-pytest/issues/167
    """
    e2e_tests = []
    other_tests = []

    for item in items:
        if "e2e" in str(item.fspath):
            e2e_tests.append(item)
        else:
            other_tests.append(item)

    items[:] = other_tests + e2e_tests


# =============================================================================
# API Client Fixtures
# =============================================================================


@pytest.fixture
async def async_client():
    """Create an async test client."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# =============================================================================
# Temp Directory Fixtures
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests. Cleanup after test."""
    tmp = Path(tempfile.mkdtemp(prefix="telemetry_test_"))
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


# =============================================================================
# Settings Fixtures
# =============================================================================


@pytest.fixture
def mock_settings(temp_dir, monkeypatch):
    """Create isolated settings with temp directories."""
    from gpstitch.config import Settings

    settings = Settings(
        temp_dir=temp_dir,
        templates_dir=temp_dir / "templates",
        local_mode=True,
        file_ttl_seconds=3600,
    )

    # Patch settings in all modules that import it
    monkeypatch.setattr("gpstitch.config.settings", settings)
    monkeypatch.setattr("gpstitch.services.file_manager.settings", settings)
    monkeypatch.setattr("gpstitch.services.template_service.settings", settings)
    monkeypatch.setattr("gpstitch.services.job_manager.settings", settings)

    return settings


# =============================================================================
# Service Fixtures (Clean instances with isolated storage)
# =============================================================================


@pytest.fixture
def clean_file_manager(mock_settings):
    """Create a fresh FileManager with isolated temp_dir."""
    from gpstitch.services.file_manager import FileManager

    manager = FileManager()
    yield manager

    # Cleanup all sessions
    import contextlib

    for session_id in list(manager.get_all_session_ids()):
        with contextlib.suppress(Exception):
            manager.cleanup_session(session_id)


@pytest.fixture
def clean_job_manager(temp_dir):
    """Create a fresh JobManager with isolated state_dir."""
    from gpstitch.services.job_manager import JobManager

    state_dir = temp_dir / "jobs"
    manager = JobManager(state_dir=state_dir)
    yield manager


@pytest.fixture
def clean_template_service(temp_dir):
    """Create a fresh TemplateService with isolated templates_dir."""
    from gpstitch.services.template_service import TemplateService

    templates_dir = temp_dir / "templates"
    service = TemplateService(templates_dir=templates_dir)
    yield service


# =============================================================================
# Test Data Fixtures (using factories)
# =============================================================================


@pytest.fixture
def sample_video_metadata():
    """Sample VideoMetadata."""
    return create_video_metadata()


@pytest.fixture
def sample_gpx_metadata():
    """Sample GpxFitMetadata."""
    return create_gpx_fit_metadata()


@pytest.fixture
def sample_job_config():
    """Sample RenderJobConfig."""
    return create_render_config()


@pytest.fixture
def sample_editor_layout():
    """Sample EditorLayout with widgets."""
    return create_editor_layout()


@pytest.fixture
def sample_xml_layout():
    """Sample XML layout string."""
    from tests.fixtures.data import SAMPLE_LAYOUT_XML

    return SAMPLE_LAYOUT_XML


# =============================================================================
# Test File Fixtures
# =============================================================================


@pytest.fixture
def sample_video_file(temp_dir):
    """Create a dummy video file in temp_dir."""
    video_path = temp_dir / "test_video.mp4"
    video_path.write_bytes(b"fake video content for testing")
    return video_path


@pytest.fixture
def sample_gpx_file(temp_dir):
    """Create a sample GPX file in temp_dir."""
    from tests.fixtures.data import SAMPLE_GPX_CONTENT

    gpx_path = temp_dir / "test_track.gpx"
    gpx_path.write_text(SAMPLE_GPX_CONTENT, encoding="utf-8")
    return gpx_path


@pytest.fixture
def real_test_video():
    """Path to real GoPro test video (skip if not available)."""
    from tests.fixtures.data import TEST_VIDEO_PATH

    path = Path(TEST_VIDEO_PATH)
    if not path.exists():
        pytest.skip(f"Test video not found: {path}")
    return path


# =============================================================================
# Mock Fixtures for External Dependencies
# =============================================================================


@pytest.fixture
def mock_ffmpeg(monkeypatch):
    """Mock FFMPEGGoPro for tests that don't need real video processing."""
    from unittest.mock import MagicMock, Mock

    mock = MagicMock()
    mock.return_value.video_info.return_value = Mock(
        video_width=1920,
        video_height=1080,
        duration=60.0,
        frame_count=1800,
        fps=30.0,
    )
    mock.return_value.has_gps.return_value = True

    monkeypatch.setattr("gpstitch.services.metadata.FFMPEGGoPro", mock)
    return mock


@pytest.fixture
def mock_gopro_overlay_load(monkeypatch):
    """Mock gopro_overlay.loading functions."""
    from unittest.mock import MagicMock

    mock_load = MagicMock()
    mock_load.return_value = MagicMock()

    monkeypatch.setattr("gopro_overlay.loading.GoproLoader", mock_load)
    return mock_load


# Re-export factory functions as fixtures for convenience
@pytest.fixture
def video_metadata_factory():
    """Factory for creating VideoMetadata."""
    return create_video_metadata


@pytest.fixture
def file_info_factory():
    """Factory for creating FileInfo."""
    return create_file_info


@pytest.fixture
def job_factory():
    """Factory for creating Jobs."""
    return create_job


@pytest.fixture
def widget_factory():
    """Factory for creating WidgetInstance."""
    return create_widget_instance


@pytest.fixture
def layout_factory():
    """Factory for creating EditorLayout."""
    return create_editor_layout
