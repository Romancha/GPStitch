"""Runtime patches for gopro_overlay library.

This module provides runtime patches to extend gopro_overlay functionality
without modifying the original library. Changes include:
- Timecode extraction for Final Cut Pro compatibility
- Enhanced FFmpeg options (audio copy, metadata preservation)
- DJI camera metrics support (metric_accessor patch, always applied)
- UTF-8 text/subprocess decoding instead of the OS locale encoding (issue #27)
- DJI SRT→GPX load bypass (gpx_patches, applied conditionally via wrapper
  when --ts-srt-source is present — preserves camera metrics in video render)
- Odometer start offset (odo_patches, applied conditionally via wrapper
  when --ts-odo-offset is present — shared GPX batch render)
- Smooth animation (overlay_fps_patches, applied conditionally via wrapper
  when --ts-overlay-fps is present — overlay drawn at the video frame rate)
- Smooth maps (smooth_map_patches, applied together with overlay_fps_patches —
  moving maps shift and rotate by fractions of a pixel every frame)
- Font face selection (font_patches, applied conditionally via wrapper
  when --ts-font-index is present — a face of a .ttc collection passed via --font)
"""

import logging

logger = logging.getLogger(__name__)

_patches_applied = False


def apply_patches() -> None:
    """Apply all runtime patches to gopro_overlay library.

    This function is idempotent and can be called multiple times safely.
    Patches are applied only once, subsequent calls are no-ops.
    """
    global _patches_applied

    if _patches_applied:
        logger.debug("Patches already applied, skipping")
        return

    from gpstitch.patches.encoding_patches import patch_text_encoding
    from gpstitch.patches.ffmpeg_gopro_patches import patch_ffmpeg_gopro
    from gpstitch.patches.ffmpeg_overlay_patches import patch_ffmpeg_overlay
    from gpstitch.patches.metric_patches import patch_metric_accessor

    patch_text_encoding()
    patch_ffmpeg_gopro()
    patch_ffmpeg_overlay()
    patch_metric_accessor()

    _patches_applied = True
    logger.info("gopro_overlay runtime patches applied successfully")


def is_patched() -> bool:
    """Check if patches have been applied."""
    return _patches_applied


__all__ = ["apply_patches", "is_patched"]
