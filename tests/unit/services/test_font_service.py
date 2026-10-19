"""Tests for system font discovery (font picker)."""

import io
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image, ImageFont

from gpstitch.services import font_service as font_service_module
from gpstitch.services.font_service import PREVIEW_HEIGHT, FontService
from tests.fixtures.data import SAMPLE_FONT, install_sample_font


@pytest.fixture
def font_dir(tmp_path):
    directory = tmp_path / "fonts"
    directory.mkdir()
    return directory


def _fake_faces(names: dict[int, tuple[str, str]]):
    """Patch font loading so every file is a collection with the given (family, style) per face."""
    real_truetype = ImageFont.truetype

    def fake_truetype(path, size, index=0):
        if index not in names:
            raise OSError("invalid face index")
        loaded = real_truetype(path, size)
        loaded.getname = lambda: names[index]
        return loaded

    return patch.object(font_service_module.ImageFont, "truetype", side_effect=fake_truetype)


class TestListFonts:
    def test_lists_installed_font_with_name(self, font_dir):
        path = install_sample_font(font_dir / "JetBrainsMono.ttf")

        fonts = FontService([font_dir]).list_fonts()

        assert len(fonts) == 1
        assert fonts[0].path == str(path)
        assert fonts[0].index == 0
        assert (fonts[0].family, fonts[0].style) == ("JetBrains Mono", "Regular")

    def test_finds_fonts_in_subdirectories_by_extension(self, font_dir):
        install_sample_font(font_dir / "truetype" / "jetbrains" / "Mono.ttf")
        (font_dir / "readme.txt").write_text("not a font")

        fonts = FontService([font_dir]).list_fonts()

        assert [Path(f.path).name for f in fonts] == ["Mono.ttf"]

    def test_skips_unreadable_files_and_missing_dirs(self, font_dir, tmp_path):
        (font_dir / "broken.ttf").write_bytes(b"not a font")

        fonts = FontService([font_dir, tmp_path / "missing"]).list_fonts()

        assert fonts == []

    def test_duplicate_family_style_keeps_first_directory(self, tmp_path):
        system_font = install_sample_font(tmp_path / "system" / "Mono.ttf")
        install_sample_font(tmp_path / "user" / "Mono.ttf")

        fonts = FontService([tmp_path / "system", tmp_path / "user"]).list_fonts()

        assert [f.path for f in fonts] == [str(system_font)]

    def test_lists_every_face_of_a_collection(self, font_dir):
        install_sample_font(font_dir / "Family.ttc")

        with _fake_faces({0: ("Family", "Regular"), 1: ("Family", "Bold"), 2: ("Family", "Light")}):
            fonts = FontService([font_dir]).list_fonts()

        # Sorted by weight within the family, each with its face index
        assert [(f.style, f.index) for f in fonts] == [("Light", 2), ("Regular", 0), ("Bold", 1)]

    def test_skips_hidden_system_faces(self, font_dir):
        install_sample_font(font_dir / "Hidden.ttf")

        with _fake_faces({0: (".SF Compact", "Regular")}):
            assert FontService([font_dir]).list_fonts() == []

    def test_skips_faces_that_cannot_render_overlay_text(self, font_dir):
        install_sample_font(font_dir / "Mono.ttf")

        with patch.object(font_service_module, "_renders_overlay_text", return_value=False):
            assert FontService([font_dir]).list_fonts() == []

    def test_no_font_dirs_lists_nothing(self):
        assert FontService([]).list_fonts() == []


class TestRendersOverlayText:
    def test_sample_font_renders_overlay_text(self):
        assert font_service_module._renders_overlay_text(ImageFont.truetype(str(SAMPLE_FONT), 12))

    def test_face_missing_a_sample_glyph_is_rejected(self):
        # "K" draws the same as .notdef, like a font without Latin capitals
        def glyph_pixels(_font, char):
            return "notdef" if char in ("\U0010fffd", "K") else char

        with patch.object(font_service_module, "_glyph_pixels", side_effect=glyph_pixels):
            assert not font_service_module._renders_overlay_text(ImageFont.truetype(str(SAMPLE_FONT), 12))

    def test_face_failing_to_render_is_rejected(self):
        # e.g. macOS Courier Oblique: FreeType raises "stack overflow" on any text
        broken = MagicMock()
        broken.getbbox.side_effect = OSError("stack overflow")

        assert not font_service_module._renders_overlay_text(broken)


class TestStyleSortKey:
    def test_sorts_light_to_heavy_with_italic_after_upright(self):
        styles = ["Black", "Bold Italic", "Italic", "Regular", "Thin", "SemiBold", "Medium", "Extra-Light", "Bold"]

        ordered = sorted(styles, key=font_service_module._style_sort_key)

        assert ordered == [
            "Thin",
            "Extra-Light",
            "Regular",
            "Italic",
            "Medium",
            "SemiBold",
            "Bold",
            "Bold Italic",
            "Black",
        ]

    @pytest.mark.parametrize(
        ("style", "same_weight_as"), [("Demi Bold", "SemiBold"), ("Book", "Regular"), ("Condensed", "Regular")]
    )
    def test_synonyms_and_unknown_styles(self, style, same_weight_as):
        key = font_service_module._style_sort_key
        assert key(style)[0] == key(same_weight_as)[0]


class TestSystemFontDirs:
    def test_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("WINDIR", "D:\\Win")
        monkeypatch.setenv("LOCALAPPDATA", "D:\\Users\\me\\AppData\\Local")

        assert font_service_module._system_font_dirs() == [
            Path("D:\\Win") / "Fonts",
            Path("D:\\Users\\me\\AppData\\Local") / "Microsoft" / "Windows" / "Fonts",
        ]

    def test_macos(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        assert font_service_module._system_font_dirs() == [
            Path("/System/Library/Fonts"),
            Path("/Library/Fonts"),
            tmp_path / "Library" / "Fonts",
        ]

    def test_linux(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        assert font_service_module._system_font_dirs() == [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            tmp_path / ".local" / "share" / "fonts",
            tmp_path / ".fonts",
        ]


class TestListFontsCache:
    def test_unchanged_fonts_are_not_read_again(self, font_dir):
        install_sample_font(font_dir / "Mono.ttf")
        service = FontService([font_dir])
        service.list_fonts()

        with patch.object(service, "_read_faces", wraps=service._read_faces) as read_faces:
            fonts = service.list_fonts()

        read_faces.assert_not_called()
        assert len(fonts) == 1

    def test_newly_installed_font_appears_without_restart(self, font_dir):
        service = FontService([font_dir])
        assert service.list_fonts() == []

        install_sample_font(font_dir / "Mono.ttf")

        assert [f.family for f in service.list_fonts()] == ["JetBrains Mono"]

    def test_modified_font_is_read_again(self, font_dir):
        path = install_sample_font(font_dir / "Mono.ttf")
        service = FontService([font_dir])
        service.list_fonts()
        stat = path.stat()
        os.utime(path, (stat.st_atime, stat.st_mtime + 10))

        with patch.object(service, "_read_faces", wraps=service._read_faces) as read_faces:
            service.list_fonts()

        read_faces.assert_called_once_with(str(path))

    def test_removed_font_disappears(self, font_dir):
        path = install_sample_font(font_dir / "Mono.ttf")
        service = FontService([font_dir])
        font_id = service.list_fonts()[0].id
        path.unlink()

        assert service.list_fonts() == []
        assert service.get_font(font_id) is None


class TestGetFont:
    def test_returns_listed_font_by_id(self, font_dir):
        install_sample_font(font_dir / "Mono.ttf")
        service = FontService([font_dir])
        listed = service.list_fonts()[0]

        assert service.get_font(listed.id) == listed

    def test_lists_fonts_on_first_lookup(self, font_dir):
        install_sample_font(font_dir / "Mono.ttf")
        listed = FontService([font_dir]).list_fonts()[0]

        # A fresh service (e.g. after a server restart) still resolves ids from the browser
        assert FontService([font_dir]).get_font(listed.id) == listed

    def test_finds_font_installed_after_the_last_listing(self, font_dir):
        service = FontService([font_dir])
        service.list_fonts()
        path = install_sample_font(font_dir / "Mono.ttf")

        font = service.get_font(font_service_module._font_id(str(path), 0))

        assert font is not None
        assert font.family == "JetBrains Mono"

    def test_unknown_id_returns_none(self, font_dir):
        install_sample_font(font_dir / "Mono.ttf")

        assert FontService([font_dir]).get_font("0123456789abcdef") is None


class TestRenderPreview:
    def test_renders_family_name_as_png_with_fixed_height(self, font_dir):
        install_sample_font(font_dir / "Mono.ttf")
        service = FontService([font_dir])

        png = service.render_preview(service.list_fonts()[0])

        image = Image.open(io.BytesIO(png))
        assert image.format == "PNG"
        assert image.mode == "RGBA"
        assert image.height == PREVIEW_HEIGHT
        assert image.getbbox() is not None  # Something was drawn

    def test_uninstalled_font_raises_oserror(self, font_dir):
        path = install_sample_font(font_dir / "Mono.ttf")
        service = FontService([font_dir])
        font = service.list_fonts()[0]
        path.unlink()

        with pytest.raises(OSError):
            service.render_preview(font)
