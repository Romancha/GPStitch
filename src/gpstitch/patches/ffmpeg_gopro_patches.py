"""Patches for gopro_overlay.ffmpeg_gopro.FFMPEGGoPro.

Adds find_timecode() method to extract timecode from video metadata.
This is needed for Final Cut Pro relink functionality.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def patch_ffmpeg_gopro() -> None:
    """Add find_timecode method to FFMPEGGoPro class."""
    from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro

    # Check if already patched
    if hasattr(FFMPEGGoPro, "find_timecode"):
        logger.debug("FFMPEGGoPro.find_timecode already exists, skipping patch")
        return

    def find_timecode(self, filepath: Path) -> str | None:
        """Extract timecode from video file metadata using ffprobe.

        This timecode is important for Final Cut Pro compatibility,
        allowing proper relinking of the processed video.

        Args:
            filepath: Path to video file

        Returns:
            Timecode string (HH:MM:SS:FF) if found, None otherwise
        """
        try:
            ffprobe_output = str(
                self.exe.ffprobe()
                .invoke(
                    [
                        "-hide_banner",
                        "-print_format",
                        "json",
                        "-show_streams",
                        "-select_streams",
                        "v:0",
                        filepath,
                    ]
                )
                .stdout
            )

            ffprobe_json = json.loads(ffprobe_output)
            streams = ffprobe_json.get("streams", [])

            if streams:
                tags = streams[0].get("tags", {})
                timecode = tags.get("timecode")
                if timecode:
                    logger.debug(f"Found timecode in {filepath}: {timecode}")
                    return timecode

        except Exception as e:
            logger.warning(f"Failed to extract timecode from {filepath}: {e}")

        return None

    # Apply the patch
    FFMPEGGoPro.find_timecode = find_timecode
    logger.debug("Patched FFMPEGGoPro with find_timecode method")
