"""E2E test for rendering with cairo-based layouts.

Reproduces GitHub issue #5 (second part): rendering with layouts that use
cairo widgets (e.g. cairo-gauge-*, cairo-circuit-map) fails when pycairo
is not installed as a dependency.

Layout "example" from gopro-overlay uses cairo widgets and will trigger:
    IOError("This widget needs pycairo to be installed - please see docs")
if pycairo is missing.
"""

import contextlib
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "videos"
GOPRO_VIDEO = _FIXTURES / "raw_gopro_with_telemetry.MP4"


def _load_video(page: Page, video_path: Path):
    """Load a video file via the local file path input."""
    video_input = page.locator("#video-path-input")
    expect(video_input).to_be_visible()
    video_input.fill(str(video_path))
    page.locator("#video-load-btn").click()
    page.wait_for_timeout(3000)
    file_context = page.locator("#file-context")
    expect(file_context).to_be_visible(timeout=5000)


def _select_layout(page: Page, layout_value: str):
    """Select a layout from the layout dropdown."""
    layout_select = page.locator("#layout-select")
    expect(layout_select).to_be_visible()
    layout_select.select_option(value=layout_value)
    # Wait for preview to regenerate with new layout
    page.wait_for_timeout(2000)


def _start_render_and_wait(page: Page, timeout_ms: int = 60000) -> str:
    """Click Render Video, handle overwrite dialog, wait for completion."""
    render_btn = page.locator("#btn-render")
    expect(render_btn).to_be_visible()
    render_btn.click()

    # Handle overwrite confirmation dialog if it appears
    overwrite_btn = page.locator("#overwrite-confirm-btn")
    try:
        overwrite_btn.wait_for(state="visible", timeout=2000)
        overwrite_btn.click()
    except Exception:
        pass

    # Wait for render modal
    render_modal = page.locator("#render-modal")
    expect(render_modal).to_be_visible(timeout=5000)

    # Poll until terminal state
    status_el = page.locator("#render-status")
    status_el.wait_for(state="visible", timeout=5000)

    progress_text = page.locator("#render-progress-text")
    with contextlib.suppress(Exception):
        expect(progress_text).to_have_text(
            re.compile(r"Completed!|Failed:.*|Cancelled"),
            timeout=timeout_ms,
        )

    return status_el.text_content()


def _get_render_error(page: Page) -> str:
    """Get the error text from render progress."""
    return page.locator("#render-progress-text").text_content() or ""


def _cleanup_output(video_path: Path):
    """Remove the _overlay.mp4 output file if it exists."""
    overlay = video_path.parent / f"{video_path.stem}_overlay.mp4"
    if overlay.exists():
        overlay.unlink()


@pytest.mark.e2e
class TestCairoLayoutRender:
    """Render with layouts that use cairo widgets (issue #5)."""

    def test_render_with_cairo_layout_succeeds(self, app_page: Page):
        """Load GoPro video -> select 'example' layout (uses cairo widgets) -> render.

        The 'example' layout from gopro-overlay contains cairo-gauge-* and
        cairo-circuit-map components that require pycairo to be installed.

        This test fails if gopro-overlay[cairo] extra is not in dependencies.
        """
        if not GOPRO_VIDEO.exists():
            pytest.skip(f"Test fixture not found: {GOPRO_VIDEO}")

        _cleanup_output(GOPRO_VIDEO)
        try:
            _load_video(app_page, GOPRO_VIDEO)

            # Verify GPS badge (GoPro has embedded telemetry)
            gps_badge = app_page.locator(".gps-badge")
            expect(gps_badge).to_be_visible(timeout=3000)

            # Select a layout that uses cairo widgets
            _select_layout(app_page, "example")

            # Render
            status = _start_render_and_wait(app_page, timeout_ms=120000)
            error = _get_render_error(app_page)

            # Must not fail with "pycairo to be installed" error (issue #5)
            assert "pycairo" not in error.lower(), f"Render failed due to missing pycairo dependency: {error}"
            assert "cairo" not in error.lower() or status == "Completed", (
                f"Render failed with cairo-related error: {error}"
            )

            if status == "Completed":
                # Verify output file when render fully succeeds
                output = GOPRO_VIDEO.parent / f"{GOPRO_VIDEO.stem}_overlay.mp4"
                assert output.exists(), f"Output file not created: {output}"
                assert output.stat().st_size > 0, "Output file is empty"
        finally:
            _cleanup_output(GOPRO_VIDEO)
