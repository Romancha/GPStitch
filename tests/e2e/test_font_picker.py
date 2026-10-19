"""E2E tests for the overlay font picker (issue #25)."""

import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, Route, expect

from tests.fixtures.data import install_sample_font

GOPRO_VIDEO = Path(__file__).parent.parent / "fixtures" / "videos" / "raw_gopro_with_telemetry.MP4"


@pytest.fixture
def font_files(tmp_path) -> dict[str, str]:
    return {name: str(install_sample_font(tmp_path / name)) for name in ("Alpha.ttf", "Beta.ttf")}


@pytest.fixture
def installed_fonts(font_files: dict[str, str]) -> list[dict]:
    """Fonts the mocked /api/options/fonts returns; tests may add to it."""
    return [
        {"id": "a1", "path": font_files["Alpha.ttf"], "index": 0, "family": "Alpha Sans", "style": "Regular"},
        {"id": "a2", "path": font_files["Alpha.ttf"], "index": 0, "family": "Alpha Sans", "style": "Bold"},
        {"id": "b1", "path": font_files["Beta.ttf"], "index": 0, "family": "Beta Mono", "style": "Regular"},
    ]


@pytest.fixture
def picker_page(app_page: Page, installed_fonts: list[dict]) -> Page:
    """App page whose font list is a fixed set backed by real font files.

    The ids are unknown to the server, so previews fall back to plain family names.
    """

    def fulfill(route: Route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"fonts": installed_fonts}))

    app_page.route("**/api/options/fonts", fulfill)
    app_page.reload()
    app_page.wait_for_load_state("networkidle")
    return app_page


def _pick(page: Page, query: str):
    page.locator("#font-picker-trigger").click()
    page.locator(".font-picker-search").fill(query)
    page.keyboard.press("Enter")


def _quick_config(page: Page) -> dict:
    return page.evaluate("() => JSON.parse(localStorage.getItem('gopro_unified_quick_config') || '{}')")


def _generated_command(page: Page) -> str:
    page.locator("#btn-generate-cmd").click()
    modal = page.locator("#command-modal")
    expect(modal).to_have_class(re.compile(r"visible"), timeout=5000)
    command = page.locator("#command-output").text_content() or ""
    modal.locator("[data-close-modal]").click()
    expect(modal).not_to_have_class(re.compile(r"visible"))
    return command


@pytest.mark.e2e
class TestFontPicker:
    def test_auto_by_default(self, picker_page: Page):
        expect(picker_page.locator("#font-picker-trigger")).to_have_text("Auto")

    def test_lists_fonts_grouped_by_family(self, picker_page: Page):
        picker_page.locator("#font-picker-trigger").click()

        options = picker_page.locator(".font-picker-option")
        expect(options).to_have_count(4)  # Auto + 3 faces
        expect(options.nth(0)).to_have_class(re.compile(r"selected"))
        expect(picker_page.locator(".font-picker-option.family-start")).to_have_count(2)
        expect(picker_page.locator(".font-picker-search")).to_have_attribute("placeholder", "Search 3 fonts...")

    def test_search_filters_by_family_and_style(self, picker_page: Page):
        picker_page.locator("#font-picker-trigger").click()
        picker_page.locator(".font-picker-search").fill("alpha bold")

        options = picker_page.locator(".font-picker-option")
        expect(options).to_have_count(1)
        expect(options.first).to_have_attribute("data-style", "Bold")

        picker_page.locator(".font-picker-search").fill("zzz")
        expect(picker_page.locator(".font-picker-message")).to_have_text("No fonts match")

    def test_pick_with_keyboard_and_survives_reload(self, picker_page: Page, font_files: dict[str, str]):
        picker_page.locator("#font-picker-trigger").click()
        picker_page.locator(".font-picker-search").fill("alpha")
        picker_page.keyboard.press("ArrowDown")
        picker_page.keyboard.press("Enter")

        expect(picker_page.locator(".font-picker-popover")).to_be_hidden()
        expect(picker_page.locator("#font-picker-trigger")).to_contain_text("Alpha Sans")
        expect(picker_page.locator("#font-picker-trigger")).to_contain_text("Bold")
        config = _quick_config(picker_page)
        assert (config["font"], config["fontIndex"]) == (font_files["Alpha.ttf"], 0)

        picker_page.reload()
        picker_page.wait_for_load_state("networkidle")

        expect(picker_page.locator("#font-picker-trigger")).to_contain_text("Alpha Sans")

    def test_recent_fonts_listed_first(self, picker_page: Page):
        _pick(picker_page, "beta")

        picker_page.locator("#font-picker-trigger").click()

        headers = picker_page.locator(".font-picker-header")
        expect(headers).to_have_text(["Recent", "All fonts"])
        expect(picker_page.locator(".font-picker-option").nth(1)).to_have_attribute("data-family", "Beta Mono")

    def test_escape_closes_and_auto_resets(self, picker_page: Page):
        _pick(picker_page, "beta")

        picker_page.locator("#font-picker-trigger").click()
        picker_page.keyboard.press("Escape")
        expect(picker_page.locator(".font-picker-popover")).to_be_hidden()

        _pick(picker_page, "auto")
        expect(picker_page.locator("#font-picker-trigger")).to_have_text("Auto")
        assert _quick_config(picker_page)["font"] is None

    def test_uninstalled_saved_font_falls_back_to_auto(self, picker_page: Page):
        picker_page.evaluate(
            """() => {
                const config = JSON.parse(localStorage.getItem('gopro_unified_quick_config') || '{}');
                localStorage.setItem('gopro_unified_quick_config',
                    JSON.stringify({ ...config, font: '/gone/Removed.ttf', fontIndex: 0 }));
            }"""
        )
        picker_page.reload()
        picker_page.wait_for_load_state("networkidle")

        expect(picker_page.locator("#font-picker-trigger")).to_have_text("Auto")
        assert _quick_config(picker_page)["font"] is None

    def test_font_installed_while_open_shows_up(self, picker_page: Page, installed_fonts: list[dict], tmp_path):
        path = str(install_sample_font(tmp_path / "Gamma.ttf"))
        installed_fonts.append({"id": "g1", "path": path, "index": 0, "family": "Gamma Serif", "style": "Regular"})

        picker_page.locator("#font-picker-trigger").click()

        expect(picker_page.locator('.font-picker-option[data-family="Gamma Serif"]')).to_have_count(1)

    def test_render_requests_carry_picked_font(self, picker_page: Page, font_files: dict[str, str]):
        _pick(picker_page, "beta")
        bodies = {}

        def capture(route: Route):
            bodies[route.request.url.rsplit("/", 1)[-1]] = route.request.post_data_json
            route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "stopped by test"}))

        picker_page.route("**/api/render/start", capture)
        picker_page.route("**/api/render/batch", capture)
        picker_page.evaluate(
            """async () => {
                await window.app.renderModal.startRender({ output_file: '/tmp/font_test_out.mp4' });
                await window.app.batchRenderModal._executeBatchRender([{ video_path: '/tmp/font_test.mp4' }])
                    .catch(() => {});
            }"""
        )

        for endpoint in ("start", "batch"):
            assert (bodies[endpoint]["font"], bodies[endpoint]["font_index"]) == (font_files["Beta.ttf"], 0)

    def test_command_uses_picked_font(self, picker_page: Page, font_files: dict[str, str]):
        if not GOPRO_VIDEO.exists():
            pytest.skip("Test fixture not found")

        picker_page.locator("#video-path-input").fill(str(GOPRO_VIDEO))
        picker_page.locator("#video-load-btn").click()
        expect(picker_page.locator("#file-context")).to_be_visible(timeout=10000)

        assert font_files["Beta.ttf"] not in _generated_command(picker_page)

        _pick(picker_page, "beta")
        assert f"--font {font_files['Beta.ttf']}" in _generated_command(picker_page)


@pytest.mark.e2e
def test_font_list_failure_keeps_saved_font(app_page: Page, font_files: dict[str, str]):
    """If the font list can't load, the saved choice stays (renders keep using it)."""
    app_page.evaluate(
        """(path) => {
            const config = JSON.parse(localStorage.getItem('gopro_unified_quick_config') || '{}');
            localStorage.setItem('gopro_unified_quick_config', JSON.stringify({ ...config, font: path, fontIndex: 0 }));
        }""",
        font_files["Beta.ttf"],
    )
    app_page.route("**/api/options/fonts", lambda route: route.fulfill(status=500, body="boom"))
    app_page.reload()
    app_page.wait_for_load_state("networkidle")

    expect(app_page.locator("#font-picker-trigger")).to_contain_text("Beta.ttf")
    assert _quick_config(app_page)["font"] == font_files["Beta.ttf"]

    app_page.locator("#font-picker-trigger").click()
    expect(app_page.locator(".font-picker-message")).to_have_text("Could not load fonts")
