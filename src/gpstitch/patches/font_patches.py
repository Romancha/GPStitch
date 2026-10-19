"""Patch to load a specific face from a font collection (.ttc)."""

import logging

from PIL import ImageFont

logger = logging.getLogger(__name__)


def patch_font_index(face_index: int) -> None:
    """Patch gopro_overlay.font.load_font to load face ``face_index`` of the font file.

    ``--font`` takes only a path, so from a .ttc collection (e.g. macOS Helvetica.ttc)
    gopro-dashboard always gets the first face. gopro-dashboard.py imports load_font by
    name when it runs, so patching the module attribute before that is enough.

    Args:
        face_index: Index of the face within the font file.
    """
    from gopro_overlay import font as font_module

    if getattr(font_module, "_ts_font_index_patched", False):
        logger.debug("load_font already patched, skipping")
        return

    # Same signature as the original load_font(font, size=32)
    def patched_load_font(font: str, size: int = 32):
        return ImageFont.truetype(font=font, size=size, index=face_index)

    font_module.load_font = patched_load_font
    font_module._ts_font_index_patched = True
    logger.info("Patched load_font with face index: %d", face_index)
