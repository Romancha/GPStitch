#!/usr/bin/env python3
"""Wrapper for gopro-dashboard.py that applies gpstitch runtime patches.

This script serves as a drop-in replacement for gopro-dashboard.py,
applying patches for:
- Timecode extraction and preservation (Final Cut Pro compatibility)
- Enhanced FFmpeg options (audio copy, metadata preservation)
- DJI SRT camera metrics preservation (when --ts-srt-source is provided)
- Odometer offset for shared GPX batch render (when --ts-odo-offset is provided)
- Smooth animation: overlay drawn at a given frame rate (when --ts-overlay-fps is provided)
- Font face within a .ttc collection (when --ts-font-index is provided)

Usage:
    python gopro_dashboard_wrapper.py [gopro-dashboard.py arguments...]

The wrapper:
1. Applies runtime patches to gopro_overlay library
2. Locates and executes the original gopro-dashboard.py script
3. Passes through all command-line arguments
"""

import logging
import math
import runpy
import shutil
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Wrapper-internal arg names consumed by this script (not passed to gopro-dashboard.py).
# Also used by renderer.py generate_cli_command() as part of the gpstitch-dashboard CLI interface.
TS_SRT_SOURCE_ARG = "--ts-srt-source"
TS_SRT_VIDEO_ARG = "--ts-srt-video"
TS_ODO_OFFSET_ARG = "--ts-odo-offset"
TS_DJI_META_SOURCE_ARG = "--ts-dji-meta-source"
TS_NOVATEK_SOURCE_ARG = "--ts-novatek-source"
TS_OVERLAY_FPS_ARG = "--ts-overlay-fps"
TS_FONT_INDEX_ARG = "--ts-font-index"


def find_gopro_dashboard() -> Path | None:
    """Locate the original gopro-dashboard.py script.

    Searches in:
    1. bin/ directory relative to project root (development)
    2. System PATH (installed via pip)

    Returns:
        Path to gopro-dashboard.py or None if not found
    """
    # Check bin/ directory relative to gpstitch project root
    # This script is at: src/gpstitch/scripts/gopro_dashboard_wrapper.py
    # Project root is 4 levels up
    current_file = Path(__file__)
    project_root = current_file.parents[3]
    bin_script = project_root / "bin" / "gopro-dashboard.py"
    if bin_script.exists():
        return bin_script

    # Check same directory as Python executable (pipx/venv installs)
    python_bin_dir = Path(sys.executable).parent
    venv_script = python_bin_dir / "gopro-dashboard.py"
    if venv_script.exists():
        return venv_script

    # Check PATH
    path_script = shutil.which("gopro-dashboard.py")
    if path_script:
        return Path(path_script)

    return None


def _extract_custom_args() -> dict:
    """Extract and remove gpstitch-specific arguments from sys.argv.

    These custom args are consumed by the wrapper and must not be passed
    to gopro-dashboard.py (it would error on unknown args).

    Returns:
        Dict with keys: srt_path, video_path, odo_offset, dji_meta_source,
        novatek_source, overlay_fps, font_index. Values may be None.
    """
    result = {
        "srt_path": None,
        "video_path": None,
        "odo_offset": None,
        "dji_meta_source": None,
        "novatek_source": None,
        "overlay_fps": None,
        "font_index": None,
    }
    new_argv = []
    i = 0
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == TS_SRT_SOURCE_ARG and i + 1 < len(sys.argv):
            result["srt_path"] = sys.argv[i + 1]
            i += 2
        elif arg == TS_SRT_VIDEO_ARG and i + 1 < len(sys.argv):
            result["video_path"] = sys.argv[i + 1]
            i += 2
        elif arg == TS_ODO_OFFSET_ARG and i + 1 < len(sys.argv):
            try:
                result["odo_offset"] = float(sys.argv[i + 1])
            except ValueError:
                logger.error("Invalid %s value: %s (expected a number)", TS_ODO_OFFSET_ARG, sys.argv[i + 1])
                sys.exit(1)
            i += 2
        elif arg == TS_DJI_META_SOURCE_ARG and i + 1 < len(sys.argv):
            result["dji_meta_source"] = sys.argv[i + 1]
            i += 2
        elif arg == TS_NOVATEK_SOURCE_ARG and i + 1 < len(sys.argv):
            result["novatek_source"] = sys.argv[i + 1]
            i += 2
        elif arg == TS_OVERLAY_FPS_ARG and i + 1 < len(sys.argv):
            try:
                fps = float(sys.argv[i + 1])
            except ValueError:
                fps = 0.0
            if not (math.isfinite(fps) and fps > 0):
                logger.error("Invalid %s value: %s (expected a positive number)", TS_OVERLAY_FPS_ARG, sys.argv[i + 1])
                sys.exit(1)
            result["overlay_fps"] = fps
            i += 2
        elif arg == TS_FONT_INDEX_ARG and i + 1 < len(sys.argv):
            try:
                face_index = int(sys.argv[i + 1])
            except ValueError:
                face_index = -1
            if face_index < 0:
                logger.error(
                    "Invalid %s value: %s (expected a non-negative integer)", TS_FONT_INDEX_ARG, sys.argv[i + 1]
                )
                sys.exit(1)
            result["font_index"] = face_index
            i += 2
        else:
            new_argv.append(arg)
            i += 1
    sys.argv = new_argv
    return result


def main():
    """Main entry point for the gopro-dashboard wrapper."""
    # Apply patches BEFORE importing anything from gopro_overlay
    # This ensures all classes are patched when gopro-dashboard.py loads them
    from gpstitch.patches import apply_patches

    apply_patches()
    logger.info("Patches applied successfully")

    # Extract custom args before passing argv to gopro-dashboard.py
    custom_args = _extract_custom_args()

    # Patch GPX loading to use SRT directly (preserves camera metrics)
    if custom_args["srt_path"]:
        from gpstitch.patches.gpx_patches import patch_gpx_load_for_srt

        patch_gpx_load_for_srt(custom_args["srt_path"], custom_args["video_path"])
        logger.info(f"SRT GPX patch applied: srt={custom_args['srt_path']}, video={custom_args['video_path']}")

    # Patch GPX loading to use DJI meta protobuf directly (preserves full GPS data)
    if custom_args["dji_meta_source"]:
        from gpstitch.patches.gpx_patches import patch_dji_meta_load

        patch_dji_meta_load(custom_args["dji_meta_source"])
        logger.info(f"DJI meta GPX patch applied: source={custom_args['dji_meta_source']}")

    # Patch GPX loading to use Novatek freeGPS blocks directly (Viofo dashcams)
    if custom_args["novatek_source"]:
        from gpstitch.patches.gpx_patches import patch_novatek_load

        patch_novatek_load(custom_args["novatek_source"])
        logger.info(f"Novatek GPS patch applied: source={custom_args['novatek_source']}")

    # Patch calculate_odo to start from offset (for shared GPX batch render)
    if custom_args["odo_offset"] is not None:
        from gpstitch.patches.odo_patches import patch_calculate_odo

        patch_calculate_odo(custom_args["odo_offset"])
        logger.info(f"Odo offset patch applied: {custom_args['odo_offset']} meters")

    # Draw the overlay at the requested frame rate instead of the fixed 10 FPS
    if custom_args["overlay_fps"] is not None:
        from gpstitch.patches.overlay_fps_patches import patch_overlay_fps

        patch_overlay_fps(custom_args["overlay_fps"])
        logger.info(f"Overlay FPS patch applied: {custom_args['overlay_fps']} FPS")

    # Load a specific face of a .ttc font collection passed via --font
    if custom_args["font_index"]:
        from gpstitch.patches.font_patches import patch_font_index

        patch_font_index(custom_args["font_index"])
        logger.info(f"Font index patch applied: face {custom_args['font_index']}")

    # Find the original gopro-dashboard.py
    dashboard_script = find_gopro_dashboard()

    if not dashboard_script:
        logger.error("gopro-dashboard.py not found. Ensure gopro-overlay is installed: uv add gopro-overlay")
        sys.exit(1)

    logger.info(f"Executing: {dashboard_script}")

    # Execute gopro-dashboard.py using runpy
    # This runs the script in the current interpreter with patches applied
    # sys.argv[0] will be the wrapper, but the script receives all args
    sys.argv[0] = str(dashboard_script)

    try:
        # Run the script as __main__
        runpy.run_path(str(dashboard_script), run_name="__main__")
    except SystemExit as e:
        # Propagate exit codes from gopro-dashboard.py
        sys.exit(e.code)
    except Exception as e:
        error_msg = f"Failed to execute gopro-dashboard.py: {e}"
        logger.exception(error_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
