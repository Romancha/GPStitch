"""E2E test fixtures for Playwright-based UI testing."""

import socket
import threading
import time
from contextlib import closing
from pathlib import Path

import httpx
import pytest
import uvicorn
from playwright.sync_api import Page

from tests.fixtures.data import SAMPLE_GPX_CONTENT


def find_free_port() -> int:
    """Find a free port on localhost."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


class ServerThread(threading.Thread):
    """Thread running uvicorn server."""

    def __init__(self, app: str, host: str, port: int):
        super().__init__(daemon=True)
        self.config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(self.config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True


@pytest.fixture(scope="session")
def app_port() -> int:
    """Get a free port for the test server."""
    return find_free_port()


@pytest.fixture(scope="session")
def base_url(app_port: int) -> str:
    """Base URL for the application."""
    return f"http://127.0.0.1:{app_port}"


@pytest.fixture(scope="session")
def live_server(app_port: int):
    """Start FastAPI server in a background thread."""
    server_thread = ServerThread(
        app="gpstitch.app:app",
        host="127.0.0.1",
        port=app_port,
    )
    server_thread.start()

    # Wait for server to be ready
    for _ in range(50):
        try:
            response = httpx.get(f"http://127.0.0.1:{app_port}/")
            if response.status_code == 200:
                break
        except httpx.ConnectError:
            time.sleep(0.1)
    else:
        raise RuntimeError("Server failed to start")

    yield server_thread

    server_thread.stop()


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure browser context for all tests."""
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "locale": "en-US",
    }


@pytest.fixture
def app_page(page: Page, base_url: str, live_server) -> Page:
    """Page navigated to the app root with console log capture."""
    # Capture console logs for test assertions
    console_logs: list[dict] = []
    page.on("console", lambda msg: console_logs.append({"type": msg.type, "text": msg.text}))
    page.console_logs = console_logs  # type: ignore[attr-defined]

    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    return page


# =============================================================================
# Test Data Fixtures
# =============================================================================


@pytest.fixture
def sample_video_path(tmp_path: Path) -> Path:
    """Create a minimal test video file."""
    # Create a dummy MP4 file (not a real video, but enough for upload testing)
    video_path = tmp_path / "test_video.mp4"
    # Minimal MP4 header bytes
    video_path.write_bytes(
        b"\x00\x00\x00\x1c\x66\x74\x79\x70\x69\x73\x6f\x6d"
        b"\x00\x00\x02\x00\x69\x73\x6f\x6d\x69\x73\x6f\x32"
        b"\x6d\x70\x34\x31"
    )
    return video_path


@pytest.fixture
def sample_gpx_path(tmp_path: Path) -> Path:
    """Create a sample GPX file for testing."""
    gpx_path = tmp_path / "test_track.gpx"
    gpx_path.write_text(SAMPLE_GPX_CONTENT, encoding="utf-8")
    return gpx_path


# =============================================================================
# Auto-screenshot on Failure
# =============================================================================


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture screenshot on test failure."""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed and "page" in item.funcargs:
        page = item.funcargs["page"]
        screenshot_dir = Path("test-results/screenshots")
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"{item.name}_FAILED.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
