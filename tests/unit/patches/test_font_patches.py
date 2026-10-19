"""Tests for the .ttc font face patch."""

import pytest
from gopro_overlay import font

from gpstitch.patches.font_patches import patch_font_index


@pytest.fixture(autouse=True)
def _restore_load_font():
    original = font.load_font
    yield
    font.load_font = original
    if hasattr(font, "_ts_font_index_patched"):
        del font._ts_font_index_patched


def test_patched_load_font_loads_requested_face(sample_font):
    # The sample font has a single face, so face 1 only fails if the index reaches FreeType
    patch_font_index(1)

    with pytest.raises(OSError):
        font.load_font(sample_font)


def test_patched_load_font_keeps_signature(sample_font):
    patch_font_index(0)

    loaded = font.load_font(font=sample_font, size=12)

    assert loaded.getname() == ("JetBrains Mono", "Regular")
    assert loaded.size == 12


def test_patch_is_idempotent(sample_font):
    patch_font_index(0)
    patch_font_index(5)

    assert font.load_font(sample_font).getname() == ("JetBrains Mono", "Regular")
