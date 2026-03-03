"""Patches for gopro_overlay.ffmpeg_overlay.FFMPEGOverlayVideo.

Adds timecode parameter and enhanced FFmpeg options:
- Explicit video output mapping [outv]
- Audio stream copy (-map 0:a?, -c:a copy)
- Metadata preservation (-map_metadata 0)
- Streaming optimization (-movflags +faststart+use_metadata_tags)
- Timecode preservation (-timecode) for Final Cut Pro

Key feature: Auto-extracts timecode from input video if not explicitly provided.
This allows timecode preservation without modifying gopro-dashboard.py.
"""

import contextlib
import logging
import re

from gopro_overlay.ffmpeg_overlay import flatten

logger = logging.getLogger(__name__)


def _extract_timecode_from_input(ffmpeg_exe, input_path) -> str | None:
    """Extract timecode from input video file.

    Args:
        ffmpeg_exe: FFMPEG instance (has ffprobe method)
        input_path: Path to input video file

    Returns:
        Timecode string (HH:MM:SS:FF) or None if not found
    """
    import json

    try:
        # Use ffprobe to get video stream metadata
        ffprobe_output = str(
            ffmpeg_exe.ffprobe()
            .invoke(
                [
                    "-hide_banner",
                    "-print_format",
                    "json",
                    "-show_streams",
                    "-select_streams",
                    "v:0",
                    str(input_path),
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
                logger.info(f"Auto-extracted timecode from input: {timecode}")
                return timecode

    except Exception as e:
        logger.debug(f"Could not extract timecode from {input_path}: {e}")

    return None


def patch_ffmpeg_overlay() -> None:
    """Patch FFMPEGOverlayVideo with timecode support and enhanced FFmpeg options."""
    from gopro_overlay.ffmpeg_overlay import FFMPEGOverlayVideo

    # Check if already patched
    if hasattr(FFMPEGOverlayVideo, "_ts_patched"):
        logger.debug("FFMPEGOverlayVideo already patched, skipping")
        return

    # Store original methods
    _original_init = FFMPEGOverlayVideo.__init__
    _original_generate = FFMPEGOverlayVideo.generate

    def patched_init(
        self,
        ffmpeg,
        input,
        output,
        overlay_size,
        options=None,
        execution=None,
        creation_time=None,
        timecode: str | None = None,
    ):
        """Enhanced __init__ with automatic timecode extraction.

        Args:
            ffmpeg: FFMPEG instance
            input: Input file path
            output: Output file path
            overlay_size: Dimension for overlay
            options: FFMPEGOptions instance
            execution: Execution strategy
            creation_time: Creation timestamp
            timecode: Optional timecode string (HH:MM:SS:FF) for Final Cut Pro.
                      If not provided, will be auto-extracted from input video.
        """
        # Call original __init__
        _original_init(
            self,
            ffmpeg=ffmpeg,
            input=input,
            output=output,
            overlay_size=overlay_size,
            options=options,
            execution=execution,
            creation_time=creation_time,
        )

        # Auto-extract timecode from input if not explicitly provided
        if timecode is None and input is not None:
            logger.debug(f"Attempting to auto-extract timecode from {input}")
            timecode = _extract_timecode_from_input(ffmpeg, input)

        # Store timecode for later use in generate()
        self._timecode = timecode
        if timecode:
            logger.debug(f"FFMPEGOverlayVideo using timecode: {timecode}")

    @contextlib.contextmanager
    def patched_generate(self):
        """Enhanced generate() with improved FFmpeg command.

        Changes from original:
        - Adds explicit [outv] output mapping for filter_complex
        - Copies audio streams from source (-map 0:a?, -c:a copy)
        - Preserves metadata (-map_metadata 0)
        - Adds streaming optimization (-movflags +faststart+use_metadata_tags)
        - Adds timecode if provided (-timecode)
        """
        filter_complex = self.options.filter_complex

        # Determine video output mapping
        # If filter ends with [name], use that as video map
        # Otherwise, add named output for explicit mapping
        output_match = re.search(r"\[(\w+)\]$", filter_complex)

        if output_match:
            video_map = ["-map", output_match.group(0)]
        else:
            filter_complex = filter_complex + "[outv]"
            video_map = ["-map", "[outv]"]

        # Add timecode option if available (important for Final Cut Pro relink)
        timecode_opts = ["-timecode", self._timecode] if getattr(self, "_timecode", None) else []

        cmd = flatten(
            [
                "-y",
                self.options.general,
                self.options.input,  # input options (list)
                "-i",
                str(self.input),
                "-f",
                "rawvideo",
                "-framerate",
                "10.0",  # hardcoded as in original
                "-s",
                f"{self.overlay_size.x}x{self.overlay_size.y}",
                "-pix_fmt",
                "rgba",
                "-i",
                "-",
                "-filter_complex",
                filter_complex,
                video_map,
                "-map",
                "0:a?",  # copy audio streams from source
                "-map_metadata",
                "0",  # copy all metadata from source
                "-c:a",
                "copy",  # audio without re-encoding
                "-movflags",
                "+faststart+use_metadata_tags",
                timecode_opts,
                self.options.output,
                "-metadata",
                f"creation_time={self.creation_time.isoformat()}",
                str(self.output),
            ]
        )

        # Use the same execution pattern as original
        yield from self.exe.execute(self.execution, cmd)

    # Apply the patches
    FFMPEGOverlayVideo.__init__ = patched_init
    FFMPEGOverlayVideo.generate = patched_generate
    FFMPEGOverlayVideo._ts_patched = True  # Mark as patched

    logger.debug("Patched FFMPEGOverlayVideo with timecode support and enhanced FFmpeg options")
