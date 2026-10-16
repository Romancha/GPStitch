"""E2E tests for the Smooth animation render option (issue #26)."""

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

GOPRO_VIDEO = Path(__file__).parent.parent / "fixtures" / "videos" / "raw_gopro_with_telemetry.MP4"


def _generated_command(page: Page) -> str:
    page.locator("#btn-generate-cmd").click()
    modal = page.locator("#command-modal")
    expect(modal).to_have_class(re.compile(r"visible"), timeout=5000)
    command = page.locator("#command-output").text_content() or ""
    modal.locator("[data-close-modal]").click()
    expect(modal).not_to_have_class(re.compile(r"visible"))
    return command


@pytest.mark.e2e
class TestSmoothAnimationOption:
    def test_off_by_default(self, app_page: Page):
        checkbox = app_page.locator("#smooth-animation")
        expect(checkbox).to_be_visible()
        expect(checkbox).not_to_be_checked()

    def test_choice_survives_reload(self, app_page: Page):
        checkbox = app_page.locator("#smooth-animation")
        checkbox.check()

        app_page.reload()
        app_page.wait_for_load_state("networkidle")

        expect(app_page.locator("#smooth-animation")).to_be_checked()

    def test_command_follows_option(self, app_page: Page):
        if not GOPRO_VIDEO.exists():
            pytest.skip("Test fixture not found")

        video_input = app_page.locator("#video-path-input")
        video_input.fill(str(GOPRO_VIDEO))
        app_page.locator("#video-load-btn").click()
        expect(app_page.locator("#file-context")).to_be_visible(timeout=10000)

        assert "--ts-overlay-fps" not in _generated_command(app_page)

        app_page.locator("#smooth-animation").check()
        assert "--ts-overlay-fps 25" in _generated_command(app_page)
