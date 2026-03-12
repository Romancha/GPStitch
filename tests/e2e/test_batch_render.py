"""Batch Render workflow E2E tests."""

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
class TestBatchRenderUI:
    """Test Batch Render UI elements and interactions."""

    def test_batch_render_button_visible(self, app_page: Page):
        """Verify Batch Render button is visible in header."""
        batch_btn = app_page.locator("#btn-batch-render")
        expect(batch_btn).to_be_visible()
        expect(batch_btn).to_have_text("Batch Render")

    def test_batch_render_modal_opens(self, app_page: Page):
        """Test that clicking Batch Render opens the modal."""
        batch_btn = app_page.locator("#btn-batch-render")
        batch_btn.click()

        # Modal should appear
        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        # Modal should have title
        modal_title = modal.locator("#batch-modal-title")
        expect(modal_title).to_have_text("Batch Render")

    def test_batch_modal_has_file_input(self, app_page: Page):
        """Test that batch modal has file paths textarea."""
        app_page.locator("#btn-batch-render").click()

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        # File paths textarea should exist
        files_input = modal.locator("#batch-files-input")
        expect(files_input).to_be_visible()

    def test_batch_modal_close_button(self, app_page: Page):
        """Test that batch modal can be closed with X button."""
        app_page.locator("#btn-batch-render").click()

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        # Close button
        close_btn = modal.locator("#batch-modal-close")
        expect(close_btn).to_be_visible()
        close_btn.click()

        app_page.wait_for_timeout(300)
        expect(modal).not_to_be_visible()

    def test_batch_modal_cancel_button(self, app_page: Page):
        """Test that batch modal can be closed with Cancel button."""
        app_page.locator("#btn-batch-render").click()

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        # Cancel button
        cancel_btn = modal.locator("#batch-cancel-btn")
        expect(cancel_btn).to_be_visible()
        cancel_btn.click()

        app_page.wait_for_timeout(300)
        expect(modal).not_to_be_visible()

    def test_batch_modal_start_button_exists(self, app_page: Page):
        """Test that batch modal has start button."""
        app_page.locator("#btn-batch-render").click()

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        # Start button
        start_btn = modal.locator("#batch-start-btn")
        expect(start_btn).to_be_visible()
        expect(start_btn).to_contain_text("Start")


@pytest.mark.e2e
class TestBatchRenderSharedGpx:
    """Test Shared GPX field in Batch Render modal."""

    def test_shared_gpx_field_visible(self, app_page: Page):
        """Test that shared GPX input field is visible in batch modal."""
        app_page.locator("#btn-batch-render").click()

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        shared_gpx = modal.locator("#batch-shared-gpx")
        expect(shared_gpx).to_be_visible()

    def test_time_offset_field_visible(self, app_page: Page):
        """Test that time offset input field is visible in batch modal."""
        app_page.locator("#btn-batch-render").click()

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        time_offset = modal.locator("#batch-time-offset")
        expect(time_offset).to_be_visible()
        expect(time_offset).to_have_value("0")

    def test_shared_gpx_changes_help_text(self, app_page: Page):
        """Test that entering shared GPX changes help text and hint."""
        app_page.locator("#btn-batch-render").click()

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        help_text = modal.locator("#batch-help-text")
        files_hint = modal.locator("#batch-files-hint")

        # Initially shows per-file GPX hint
        expect(files_hint).to_contain_text("video.mp4, track.gpx")

        # Enter a shared GPX path
        shared_gpx = modal.locator("#batch-shared-gpx")
        shared_gpx.fill("/path/to/shared.gpx")
        app_page.wait_for_timeout(200)

        # Hint should change to video-only format
        expect(files_hint).to_contain_text("one per line")
        expect(help_text).to_contain_text("Per-file GPX pairs are ignored")

        # Clear shared GPX
        shared_gpx.fill("")
        app_page.wait_for_timeout(200)

        # Should revert to original hint
        expect(files_hint).to_contain_text("video.mp4, track.gpx")

    def test_shared_gpx_disables_per_file_gpx_parsing(self, app_page: Page):
        """Test that per-file GPX is ignored when shared GPX is set."""
        app_page.locator("#btn-batch-render").click()

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        # Set shared GPX
        shared_gpx = modal.locator("#batch-shared-gpx")
        shared_gpx.fill("/path/to/shared.gpx")

        # Enter video with per-file GPX pair
        files_input = modal.locator("#batch-files-input")
        files_input.fill("/path/to/video1.mp4, /path/to/per_file.gpx\n/path/to/video2.mp4")
        app_page.wait_for_timeout(200)

        # File count should be 2
        file_count = modal.locator("#batch-file-count")
        expect(file_count).to_contain_text("2")

    def test_shared_gpx_fields_reset_on_reopen(self, app_page: Page):
        """Test that shared GPX and time offset reset when modal is reopened."""
        app_page.locator("#btn-batch-render").click()

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        # Fill in values
        modal.locator("#batch-shared-gpx").fill("/path/to/shared.gpx")
        modal.locator("#batch-time-offset").fill("30")

        # Close modal
        modal.locator("#batch-modal-close").click()
        app_page.wait_for_timeout(300)

        # Reopen
        app_page.locator("#btn-batch-render").click()
        expect(modal).to_be_visible()

        # Fields should be reset
        expect(modal.locator("#batch-shared-gpx")).to_have_value("")
        expect(modal.locator("#batch-time-offset")).to_have_value("0")


@pytest.mark.e2e
class TestBatchRenderWithFiles:
    """Test Batch Render with actual file paths."""

    @pytest.fixture
    def test_video_path(self) -> Path:
        """Get path to the first test video with telemetry."""
        video_path = Path(__file__).parent.parent / "fixtures" / "videos" / "raw_gopro_with_telemetry.MP4"
        if not video_path.exists():
            pytest.skip(f"Test video not found: {video_path}")
        return video_path

    @pytest.fixture
    def test_video_path_2(self) -> Path:
        """Get path to the second test video with telemetry."""
        video_path = Path(__file__).parent.parent / "fixtures" / "videos" / "raw_gopro_with_telemetry_2.MP4"
        if not video_path.exists():
            pytest.skip(f"Test video 2 not found: {video_path}")
        return video_path

    def test_add_single_file_path(self, app_page: Page, test_video_path: Path):
        """Test adding a single file path to batch."""
        app_page.locator("#btn-batch-render").click()

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        # Enter file path in textarea
        files_input = modal.locator("#batch-files-input")
        files_input.fill(str(test_video_path))

        # File count should update
        app_page.wait_for_timeout(300)
        file_count = modal.locator("#batch-file-count")
        expect(file_count).to_contain_text("1")

    def test_add_multiple_file_paths(self, app_page: Page, test_video_path: Path, test_video_path_2: Path):
        """Test adding multiple file paths to batch."""
        app_page.locator("#btn-batch-render").click()

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        # Enter multiple file paths (one per line)
        files_input = modal.locator("#batch-files-input")
        files_input.fill(f"{test_video_path}\n{test_video_path_2}")

        # File count should update to 2
        app_page.wait_for_timeout(300)
        file_count = modal.locator("#batch-file-count")
        expect(file_count).to_contain_text("2")

    def test_file_count_updates_on_input(self, app_page: Page, test_video_path: Path):
        """Test that file count updates as user types."""
        app_page.locator("#btn-batch-render").click()

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        files_input = modal.locator("#batch-files-input")
        file_count = modal.locator("#batch-file-count")

        # Initially 0
        expect(file_count).to_contain_text("0")

        # Add one path
        files_input.fill(str(test_video_path))
        app_page.wait_for_timeout(200)
        expect(file_count).to_contain_text("1")

        # Clear
        files_input.fill("")
        app_page.wait_for_timeout(200)
        expect(file_count).to_contain_text("0")

    def test_batch_with_gpx_pair(self, app_page: Page, test_video_path: Path):
        """Test batch input with video + GPX pair format."""
        app_page.locator("#btn-batch-render").click()

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        # Format: video.mp4, track.gpx
        files_input = modal.locator("#batch-files-input")
        files_input.fill(f"{test_video_path}, /path/to/track.gpx")

        app_page.wait_for_timeout(300)
        # Should count as 1 file (the pair)
        file_count = modal.locator("#batch-file-count")
        expect(file_count).to_contain_text("1")


@pytest.mark.e2e
@pytest.mark.slow
class TestBatchRenderExecution:
    """Test Batch Render execution (slow tests that actually start rendering)."""

    @pytest.fixture
    def test_video_path(self) -> Path:
        """Get path to the first test video with telemetry."""
        video_path = Path(__file__).parent.parent / "fixtures" / "videos" / "raw_gopro_with_telemetry.MP4"
        if not video_path.exists():
            pytest.skip(f"Test video not found: {video_path}")
        return video_path

    @pytest.fixture
    def test_video_path_2(self) -> Path:
        """Get path to the second test video with telemetry."""
        video_path = Path(__file__).parent.parent / "fixtures" / "videos" / "raw_gopro_with_telemetry_2.MP4"
        if not video_path.exists():
            pytest.skip(f"Test video 2 not found: {video_path}")
        return video_path

    @pytest.fixture(autouse=True)
    def fresh_page_state(self, app_page: Page):
        """Ensure clean page state before each test."""
        # Force hide any modal overlays via JavaScript
        app_page.evaluate("""
            document.querySelectorAll('.modal-overlay').forEach(m => {
                m.style.display = 'none';
            });
        """)
        app_page.wait_for_timeout(100)

    def _dismiss_batch_pre_check_dialogs(self, app_page: Page):
        """Dismiss pre-check dialogs (overwrite + GPS) that appear after batch start.

        The batch flow shows: overwrite dialog (if conflicts) → GPS quality dialog → render.
        Both are async awaits, so we must wait for each to appear before dismissing.
        """
        # First check if overwrite dialog appears (may not if no existing files)
        overwrite_btn = app_page.locator("#overwrite-confirm-btn")
        try:
            overwrite_btn.wait_for(state="visible", timeout=3000)
            overwrite_btn.click()
            app_page.wait_for_timeout(300)
        except Exception:
            pass

        # GPS quality dialog always appears - wait for it
        gps_continue = app_page.locator("#gps-batch-render-btn")
        gps_continue.wait_for(state="visible", timeout=30000)
        gps_continue.click()
        app_page.wait_for_timeout(500)

    def test_batch_render_starts_and_cancel(self, app_page: Page, test_video_path: Path, test_video_path_2: Path):
        """Test that batch render can be started (cancelled immediately to avoid long wait)."""
        app_page.locator("#btn-batch-render").click()

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        # Add two files
        files_input = modal.locator("#batch-files-input")
        files_input.fill(f"{test_video_path}\n{test_video_path_2}")
        app_page.wait_for_timeout(300)

        # Verify file count
        file_count = modal.locator("#batch-file-count")
        expect(file_count).to_contain_text("2")

        # Start batch render
        start_btn = modal.locator("#batch-start-btn")
        start_btn.click()

        # Dismiss GPS warning and overwrite dialogs that appear after start
        self._dismiss_batch_pre_check_dialogs(app_page)

        # Wait for batch to start processing
        app_page.wait_for_timeout(1500)

        # Cancel batch to avoid long wait
        cancel_btn = app_page.locator("#batch-cancel-btn")
        if cancel_btn.is_visible():
            cancel_btn.click()
            app_page.wait_for_timeout(500)

    def test_batch_progress_shows_in_modal(self, app_page: Page, test_video_path: Path, test_video_path_2: Path):
        """Test that batch progress is displayed in modal during rendering."""
        # Force click to bypass any overlay (from previous test's render modal)
        app_page.locator("#btn-batch-render").click(force=True)

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        # Add files
        files_input = modal.locator("#batch-files-input")
        files_input.fill(f"{test_video_path}\n{test_video_path_2}")
        app_page.wait_for_timeout(300)

        # Start batch
        start_btn = modal.locator("#batch-start-btn")
        start_btn.click()

        # Dismiss GPS warning and overwrite dialogs that appear after start
        self._dismiss_batch_pre_check_dialogs(app_page)

        # Wait for progress to appear
        app_page.wait_for_timeout(2000)

        # Modal should still be visible during progress
        expect(modal).to_be_visible()

        # Cancel to clean up
        cancel_btn = modal.locator("#batch-cancel-btn")
        if cancel_btn.is_visible():
            cancel_btn.click()
            app_page.wait_for_timeout(500)

    def test_batch_status_in_status_bar(self, app_page: Page, test_video_path: Path):
        """Test that batch status appears in status bar."""
        app_page.locator("#btn-batch-render").click()

        modal = app_page.locator("#batch-render-modal")
        expect(modal).to_be_visible()

        # Add file
        files_input = modal.locator("#batch-files-input")
        files_input.fill(str(test_video_path))
        app_page.wait_for_timeout(300)

        # Start batch
        start_btn = modal.locator("#batch-start-btn")
        start_btn.click()

        # Dismiss GPS warning and overwrite dialogs that appear after start
        self._dismiss_batch_pre_check_dialogs(app_page)

        # Wait for status bar to update
        app_page.wait_for_timeout(1500)

        # Status bar should show rendering status
        status_bar = app_page.locator(".status-bar")
        expect(status_bar).to_be_visible()

        # Cancel to clean up
        cancel_btn = modal.locator("#batch-cancel-btn")
        if cancel_btn.is_visible():
            cancel_btn.click()
