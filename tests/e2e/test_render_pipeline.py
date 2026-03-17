"""E2E tests for full render pipeline: load file via UI -> render -> verify success.

Tests all supported file combinations with real test fixtures:
- GoPro video with embedded telemetry (standalone)
- MOV video + external GPX
- DJI video + SRT telemetry (auto-detected)
- DJI Action video with embedded GPS (DJI meta stream)
"""

import contextlib
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

# Absolute paths to test fixtures
_FIXTURES = Path(__file__).parent.parent / "fixtures" / "videos"
GOPRO_VIDEO = _FIXTURES / "raw_gopro_with_telemetry.MP4"
GOPRO_VIDEO_2 = _FIXTURES / "raw_gopro_with_telemetry_2.MP4"
MOV_VIDEO = _FIXTURES / "IMG_2927.MOV"
RUN_GPX = _FIXTURES / "hiking_activity.gpx"
DJI_VIDEO = _FIXTURES / "DJI_20250723102139_0001_D.MP4"
DJI_SRT = _FIXTURES / "DJI_20250723102139_0001_D.SRT"
DJI_ACTION_VIDEO = _FIXTURES / "DJI_20260315180109_0003_D_5s_fixture.MP4"


def _load_video(page: Page, video_path: Path):
    """Load a video file via the local file path input."""
    video_input = page.locator("#video-path-input")
    expect(video_input).to_be_visible()
    video_input.fill(str(video_path))
    page.locator("#video-load-btn").click()
    # Wait for file metadata extraction and preview generation
    page.wait_for_timeout(3000)
    # Verify file loaded successfully
    file_context = page.locator("#file-context")
    expect(file_context).to_be_visible(timeout=5000)


def _load_gps(page: Page, gps_path: Path):
    """Load a GPS/SRT file via the local file path input."""
    gps_input = page.locator("#gps-path-input")
    expect(gps_input).to_be_visible()
    gps_input.fill(str(gps_path))
    page.locator("#gps-load-btn").click()
    page.wait_for_timeout(2000)


def _start_render_and_wait(page: Page, timeout_ms: int = 60000):
    """Click Render Video, handle overwrite dialog, wait for completion.

    Returns the render status text.
    """
    # Click Render Video
    render_btn = page.locator("#btn-render")
    expect(render_btn).to_be_visible()
    render_btn.click()

    # Handle overwrite confirmation dialog if it appears
    overwrite_btn = page.locator("#overwrite-confirm-btn")
    try:
        overwrite_btn.wait_for(state="visible", timeout=2000)
        overwrite_btn.click()
    except Exception:
        pass  # No overwrite dialog — first run or file doesn't exist

    # Wait for render modal to appear
    render_modal = page.locator("#render-modal")
    expect(render_modal).to_be_visible(timeout=5000)

    # Wait for terminal state: Completed, Failed, or Cancelled
    status_el = page.locator("#render-status")
    status_el.wait_for(state="visible", timeout=5000)

    # Poll until terminal state (progress text changes to "Completed!" or "Failed: ...")
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
class TestGoproRenderPipeline:
    """Full render pipeline for GoPro videos with embedded telemetry."""

    def test_gopro_video_renders_successfully(self, app_page: Page):
        """Load GoPro video -> render -> verify completed."""
        if not GOPRO_VIDEO.exists():
            pytest.skip(f"Test fixture not found: {GOPRO_VIDEO}")

        _cleanup_output(GOPRO_VIDEO)
        try:
            _load_video(app_page, GOPRO_VIDEO)

            # Verify GPS badge (GoPro has embedded telemetry)
            gps_badge = app_page.locator(".gps-badge")
            expect(gps_badge).to_be_visible(timeout=3000)

            # Verify preview generated
            preview_img = app_page.locator("#preview-image")
            expect(preview_img).to_be_visible()
            src = preview_img.get_attribute("src")
            assert src and len(src) > 100, "Preview image should have base64 data"

            # Render
            status = _start_render_and_wait(app_page, timeout_ms=120000)
            error = _get_render_error(app_page)
            assert status == "Completed", f"Render failed: {error}"

            # Verify output file exists
            output = GOPRO_VIDEO.parent / f"{GOPRO_VIDEO.stem}_overlay.mp4"
            assert output.exists(), f"Output file not created: {output}"
            assert output.stat().st_size > 0, "Output file is empty"
        finally:
            _cleanup_output(GOPRO_VIDEO)

    def test_gopro_video_2_renders_successfully(self, app_page: Page):
        """Load second GoPro video -> render -> verify completed."""
        if not GOPRO_VIDEO_2.exists():
            pytest.skip(f"Test fixture not found: {GOPRO_VIDEO_2}")

        _cleanup_output(GOPRO_VIDEO_2)
        try:
            _load_video(app_page, GOPRO_VIDEO_2)

            # Verify GPS badge
            gps_badge = app_page.locator(".gps-badge")
            expect(gps_badge).to_be_visible(timeout=3000)

            # Render
            status = _start_render_and_wait(app_page, timeout_ms=120000)
            error = _get_render_error(app_page)
            assert status == "Completed", f"Render failed: {error}"

            output = GOPRO_VIDEO_2.parent / f"{GOPRO_VIDEO_2.stem}_overlay.mp4"
            assert output.exists(), f"Output file not created: {output}"
            assert output.stat().st_size > 0, "Output file is empty"
        finally:
            _cleanup_output(GOPRO_VIDEO_2)


@pytest.mark.e2e
class TestMovGpxRenderPipeline:
    """Full render pipeline for MOV video + external GPX."""

    def test_mov_with_gpx_renders_successfully(self, app_page: Page):
        """Load MOV video + GPX -> render -> verify completed."""
        if not MOV_VIDEO.exists() or not RUN_GPX.exists():
            pytest.skip("Test fixtures not found")

        _cleanup_output(MOV_VIDEO)
        try:
            _load_video(app_page, MOV_VIDEO)

            # MOV has no GPS — no GPS badge expected
            file_context = app_page.locator("#file-context")
            expect(file_context).to_be_visible()

            # Load GPX as secondary
            _load_gps(app_page, RUN_GPX)

            # Verify GPS file info appears
            gps_file_info = app_page.locator("#gps-file-info")
            expect(gps_file_info).to_be_visible(timeout=3000)

            # Verify preview generated
            preview_img = app_page.locator("#preview-image")
            expect(preview_img).to_be_visible()

            # Render
            status = _start_render_and_wait(app_page, timeout_ms=120000)
            error = _get_render_error(app_page)
            assert status == "Completed", f"Render failed: {error}"

            output = MOV_VIDEO.parent / f"{MOV_VIDEO.stem}_overlay.mp4"
            assert output.exists(), f"Output file not created: {output}"
            assert output.stat().st_size > 0, "Output file is empty"
        finally:
            _cleanup_output(MOV_VIDEO)

    def test_mov_with_gpx_loads_files(self, app_page: Page):
        """Verify MOV + GPX loads correctly and both files are recognized."""
        if not MOV_VIDEO.exists() or not RUN_GPX.exists():
            pytest.skip("Test fixtures not found")

        _load_video(app_page, MOV_VIDEO)

        # Verify video loaded
        file_context = app_page.locator("#file-context")
        expect(file_context).to_be_visible()
        file_details = app_page.locator(".file-context-details")
        expect(file_details).to_contain_text(re.compile(r"\d+x\d+"))

        # Load GPX as secondary
        _load_gps(app_page, RUN_GPX)

        # Verify GPS file loaded
        gps_file_info = app_page.locator("#gps-file-info")
        expect(gps_file_info).to_be_visible(timeout=3000)


@pytest.mark.e2e
class TestDjiSrtRenderPipeline:
    """Full render pipeline for DJI video + SRT telemetry."""

    def test_dji_with_srt_renders_successfully(self, app_page: Page):
        """Load DJI video (SRT auto-detected) -> render -> verify completed."""
        if not DJI_VIDEO.exists() or not DJI_SRT.exists():
            pytest.skip("Test fixtures not found")

        _cleanup_output(DJI_VIDEO)
        try:
            _load_video(app_page, DJI_VIDEO)

            # SRT should be auto-detected and loaded as secondary
            # Verify file context shows the video
            file_context = app_page.locator("#file-context")
            expect(file_context).to_be_visible()

            # Verify SRT auto-detection: GPS file info should appear
            gps_file_info = app_page.locator("#gps-file-info")
            expect(gps_file_info).to_be_visible(timeout=5000)

            # Wait for preview/time-sync to settle before render
            app_page.wait_for_timeout(3000)

            # Render
            status = _start_render_and_wait(app_page, timeout_ms=120000)
            error = _get_render_error(app_page)
            assert status == "Completed", f"Render failed: {error}"

            output = DJI_VIDEO.parent / f"{DJI_VIDEO.stem}_overlay.mp4"
            assert output.exists(), f"Output file not created: {output}"
            assert output.stat().st_size > 0, "Output file is empty"
        finally:
            _cleanup_output(DJI_VIDEO)

    def test_dji_srt_auto_detection(self, app_page: Page):
        """Verify DJI SRT is auto-detected when loading DJI video."""
        if not DJI_VIDEO.exists() or not DJI_SRT.exists():
            pytest.skip("Test fixtures not found")

        _load_video(app_page, DJI_VIDEO)

        # Verify video loaded
        file_context = app_page.locator("#file-context")
        expect(file_context).to_be_visible()

        # SRT should be auto-detected and loaded as secondary
        gps_file_info = app_page.locator("#gps-file-info")
        expect(gps_file_info).to_be_visible(timeout=5000)

        # Verify file details show DJI video info
        file_details = app_page.locator(".file-context-details")
        expect(file_details).to_be_visible()
        expect(file_details).to_contain_text(re.compile(r"\d+x\d+"))

    def test_dji_command_uses_gpx_only_flag(self, app_page: Page):
        """Verify generated command for DJI+SRT includes --use-gpx-only."""
        if not DJI_VIDEO.exists() or not DJI_SRT.exists():
            pytest.skip("Test fixtures not found")

        _load_video(app_page, DJI_VIDEO)

        # Wait for SRT auto-detection
        gps_file_info = app_page.locator("#gps-file-info")
        expect(gps_file_info).to_be_visible(timeout=5000)

        # Click "Get Command" to generate CLI command
        cmd_btn = app_page.locator("#btn-generate-cmd")
        expect(cmd_btn).to_be_visible()
        cmd_btn.click()

        # Wait for command modal to appear
        cmd_modal = app_page.locator("#command-modal")
        expect(cmd_modal).to_have_class(re.compile(r"visible"), timeout=5000)

        # Read command text
        cmd_output = app_page.locator("#command-output")
        cmd_text = cmd_output.text_content() or ""
        assert len(cmd_text) > 0, "Command output should not be empty"

        # Verify critical flags for DJI+SRT
        assert "--use-gpx-only" in cmd_text, f"DJI+SRT command must include --use-gpx-only, got:\n{cmd_text}"
        assert "--gpx" in cmd_text, "Command must include --gpx flag"
        assert ".gpx" in cmd_text, "SRT should be converted to GPX"


@pytest.mark.e2e
class TestDjiActionRenderPipeline:
    """Full render pipeline for DJI Action video with embedded GPS (DJI meta stream)."""

    def test_dji_action_gps_autodetected_on_upload(self, app_page: Page):
        """Load DJI Action video -> verify GPS autodetected (no secondary file needed)."""
        if not DJI_ACTION_VIDEO.exists():
            pytest.skip(f"Test fixture not found: {DJI_ACTION_VIDEO}")

        _load_video(app_page, DJI_ACTION_VIDEO)

        # Verify video loaded
        file_context = app_page.locator("#file-context")
        expect(file_context).to_be_visible()

        # DJI Action with embedded GPS should show GPS badge
        gps_badge = app_page.locator(".gps-badge")
        expect(gps_badge).to_be_visible(timeout=5000)

        # Verify file details show video info (resolution, FPS)
        file_details = app_page.locator(".file-context-details")
        expect(file_details).to_be_visible()
        expect(file_details).to_contain_text(re.compile(r"\d+x\d+"))

    def test_dji_action_renders_successfully(self, app_page: Page):
        """Load DJI Action video -> render -> verify completed."""
        if not DJI_ACTION_VIDEO.exists():
            pytest.skip(f"Test fixture not found: {DJI_ACTION_VIDEO}")

        _cleanup_output(DJI_ACTION_VIDEO)
        try:
            _load_video(app_page, DJI_ACTION_VIDEO)

            # Verify GPS autodetected
            gps_badge = app_page.locator(".gps-badge")
            expect(gps_badge).to_be_visible(timeout=5000)

            # Wait for preview to settle
            app_page.wait_for_timeout(3000)

            # Render
            status = _start_render_and_wait(app_page, timeout_ms=120000)
            error = _get_render_error(app_page)
            assert status == "Completed", f"Render failed: {error}"

            # Verify output file exists
            output = DJI_ACTION_VIDEO.parent / f"{DJI_ACTION_VIDEO.stem}_overlay.mp4"
            assert output.exists(), f"Output file not created: {output}"
            assert output.stat().st_size > 0, "Output file is empty"
        finally:
            _cleanup_output(DJI_ACTION_VIDEO)

    def test_dji_action_command_uses_gpx_only_flag(self, app_page: Page):
        """Verify generated command for DJI Action includes --use-gpx-only."""
        if not DJI_ACTION_VIDEO.exists():
            pytest.skip(f"Test fixture not found: {DJI_ACTION_VIDEO}")

        _load_video(app_page, DJI_ACTION_VIDEO)

        # Verify GPS autodetected
        gps_badge = app_page.locator(".gps-badge")
        expect(gps_badge).to_be_visible(timeout=5000)

        # Click "Get Command" to generate CLI command
        cmd_btn = app_page.locator("#btn-generate-cmd")
        expect(cmd_btn).to_be_visible()
        cmd_btn.click()

        # Wait for command modal to appear
        cmd_modal = app_page.locator("#command-modal")
        expect(cmd_modal).to_have_class(re.compile(r"visible"), timeout=5000)

        # Read command text
        cmd_output = app_page.locator("#command-output")
        cmd_text = cmd_output.text_content() or ""
        assert len(cmd_text) > 0, "Command output should not be empty"

        # Verify critical flags for DJI Action embedded GPS
        assert "--use-gpx-only" in cmd_text, f"DJI Action command must include --use-gpx-only, got:\n{cmd_text}"
        assert "--gpx" in cmd_text, "Command must include --gpx flag"
        assert ".gpx" in cmd_text, "DJI meta GPS should be converted to GPX"
