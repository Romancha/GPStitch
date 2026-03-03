"""Smoke tests for basic application functionality."""

import re

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
class TestAppLoads:
    """Test that the application loads correctly."""

    def test_homepage_loads(self, app_page: Page):
        """Verify the homepage loads with correct title."""
        expect(app_page).to_have_title("GPStitch")

    def test_main_sections_visible(self, app_page: Page):
        """Verify main UI sections are visible."""
        # Header
        expect(app_page.locator(".unified-header")).to_be_visible()
        expect(app_page.locator("h1")).to_have_text("GPStitch")

        # Sidebar with file uploader
        expect(app_page.locator("#sidebar")).to_be_visible()
        expect(app_page.locator("#file-uploader-container")).to_be_visible()

        # Preview area
        expect(app_page.locator(".preview-area")).to_be_visible()

        # Right panel with config
        expect(app_page.locator("#right-panel")).to_be_visible()

        # Status bar
        expect(app_page.locator(".status-bar")).to_be_visible()


@pytest.mark.e2e
class TestModeToggle:
    """Test mode switching between Quick and Advanced modes."""

    def test_quick_mode_is_default(self, app_page: Page):
        """Verify Quick Mode is active by default."""
        quick_btn = app_page.locator("#mode-quick")
        advanced_btn = app_page.locator("#mode-advanced")

        expect(quick_btn).to_have_class(re.compile(r"active"))
        expect(advanced_btn).not_to_have_class(re.compile(r"active"))

    def test_switch_to_advanced_mode(self, app_page: Page):
        """Verify switching to Advanced Mode updates UI."""
        advanced_btn = app_page.locator("#mode-advanced")
        advanced_btn.click()

        # Advanced mode button should be active
        expect(advanced_btn).to_have_class(re.compile(r"active"))
        expect(app_page.locator("#mode-quick")).not_to_have_class(re.compile(r"active"))

        # Widget palette should be visible in advanced mode
        expect(app_page.locator("#widget-palette-container")).to_be_visible()

        # Advanced toolbar should be visible
        expect(app_page.locator("#advanced-toolbar")).to_be_visible()

    def test_switch_back_to_quick_mode(self, app_page: Page):
        """Verify switching back to Quick Mode."""
        # First switch to advanced
        app_page.locator("#mode-advanced").click()
        expect(app_page.locator("#mode-advanced")).to_have_class(re.compile(r"active"))

        # Then switch back to quick
        app_page.locator("#mode-quick").click()
        expect(app_page.locator("#mode-quick")).to_have_class(re.compile(r"active"))

        # Quick toolbar should be visible
        expect(app_page.locator("#quick-toolbar")).to_be_visible()


@pytest.mark.e2e
class TestConfigPanel:
    """Test configuration panel functionality."""

    def test_config_dropdowns_populated(self, app_page: Page):
        """Verify config dropdowns have options loaded."""
        # Layout selector
        layout_select = app_page.locator("#layout-select")
        expect(layout_select).to_be_visible()
        # Should have at least one option loaded from API
        app_page.wait_for_timeout(500)  # Wait for API response
        options = layout_select.locator("option")
        assert options.count() > 0, "Layout select should have options"

        # Unit selectors
        expect(app_page.locator("#units-speed")).to_be_visible()
        expect(app_page.locator("#units-altitude")).to_be_visible()
        expect(app_page.locator("#units-distance")).to_be_visible()
        expect(app_page.locator("#units-temperature")).to_be_visible()

        # Map style selector
        expect(app_page.locator("#map-style")).to_be_visible()

    def test_no_console_errors_on_load(self, app_page: Page):
        """Verify no JavaScript errors on page load."""
        # Access console logs captured by fixture
        errors = [log for log in getattr(app_page, "console_logs", []) if log.get("type") == "error"]
        # Filter out expected/benign errors if any
        critical_errors = [e for e in errors if "favicon" not in e.get("text", "").lower()]
        assert len(critical_errors) == 0, f"Console errors found: {critical_errors}"
