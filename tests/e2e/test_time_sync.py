"""E2E tests for time sync UI components."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
class TestTimeSyncDropdown:
    """Test the time sync dropdown shows new alignment options."""

    def test_time_sync_dropdown_has_new_options(self, app_page: Page):
        """Verify the time sync dropdown contains the new alignment options."""
        dropdown = app_page.locator("#video-time-alignment")
        expect(dropdown).to_be_attached()

        auto_option = dropdown.locator('option[value="auto"]')
        gpx_option = dropdown.locator('option[value="gpx-timestamps"]')
        manual_option = dropdown.locator('option[value="manual"]')

        expect(auto_option).to_be_attached()
        expect(gpx_option).to_be_attached()
        expect(manual_option).to_be_attached()

        expect(auto_option).to_have_text("Auto (recommended)")
        expect(gpx_option).to_have_text("Use GPX timestamps")
        expect(manual_option).to_have_text("Manual offset...")

    def test_old_options_removed(self, app_page: Page):
        """Verify old filesystem-based options are no longer present."""
        dropdown = app_page.locator("#video-time-alignment")
        expect(dropdown).to_be_attached()

        file_created = dropdown.locator('option[value="file-created"]')
        file_modified = dropdown.locator('option[value="file-modified"]')

        assert file_created.count() == 0, "file-created option should be removed"
        assert file_modified.count() == 0, "file-modified option should be removed"

    def test_auto_is_default_selection(self, app_page: Page):
        """Verify 'auto' is the default selected value."""
        dropdown = app_page.locator("#video-time-alignment")
        expect(dropdown).to_be_attached()
        expect(dropdown).to_have_value("auto")


@pytest.mark.e2e
class TestManualOffsetPanel:
    """Test the manual offset panel visibility and controls."""

    def test_manual_offset_hidden_by_default(self, app_page: Page):
        """Manual offset panel should be hidden when 'auto' is selected."""
        offset_panel = app_page.locator("#manual-offset-panel")
        expect(offset_panel).to_be_attached()
        expect(offset_panel).to_be_hidden()

    def test_manual_offset_shows_when_manual_selected(self, app_page: Page):
        """Manual offset panel display style changes to 'block' when 'manual' is selected."""
        # Use JS to change the dropdown value and trigger change event
        # since the parent panel is hidden (no GPX file loaded)
        app_page.evaluate("""() => {
            const dropdown = document.getElementById('video-time-alignment');
            dropdown.value = 'manual';
            dropdown.dispatchEvent(new Event('change'));
        }""")

        # Check style.display directly since parent panel is hidden
        display = app_page.evaluate("() => document.getElementById('manual-offset-panel').style.display")
        assert display == "block", f"Expected display 'block', got '{display}'"

        # Verify offset controls exist in DOM
        expect(app_page.locator("#offset-minus")).to_be_attached()
        expect(app_page.locator("#offset-plus")).to_be_attached()
        expect(app_page.locator("#time-offset-seconds")).to_be_attached()

    def test_manual_offset_hides_when_auto_selected(self, app_page: Page):
        """Manual offset panel display style changes to 'none' when switching back to 'auto'."""
        # Show the panel via JS
        app_page.evaluate("""() => {
            const dropdown = document.getElementById('video-time-alignment');
            dropdown.value = 'manual';
            dropdown.dispatchEvent(new Event('change'));
        }""")

        display = app_page.evaluate("() => document.getElementById('manual-offset-panel').style.display")
        assert display == "block"

        # Switch back to auto via JS
        app_page.evaluate("""() => {
            const dropdown = document.getElementById('video-time-alignment');
            dropdown.value = 'auto';
            dropdown.dispatchEvent(new Event('change'));
        }""")

        display = app_page.evaluate("() => document.getElementById('manual-offset-panel').style.display")
        assert display == "none", f"Expected display 'none', got '{display}'"

    def test_time_sync_hint_exists(self, app_page: Page):
        """Verify the time sync hint element exists in the DOM."""
        hint = app_page.locator("#time-sync-hint")
        expect(hint).to_be_attached()
        expect(hint).to_be_hidden()
