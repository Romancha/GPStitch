#!/usr/bin/env python3
"""Wrapper for gopro-dashboard.py that applies telemetry-studio runtime patches.

This script serves as a drop-in replacement for gopro-dashboard.py,
applying patches for:
- Timecode extraction and preservation (Final Cut Pro compatibility)
- Enhanced FFmpeg options (audio copy, metadata preservation)
- DJI SRT camera metrics preservation (when --ts-srt-source is provided)

Usage:
    python gopro_dashboard_wrapper.py [gopro-dashboard.py arguments...]

The wrapper:
1. Applies runtime patches to gopro_overlay library
2. Locates and executes the original gopro-dashboard.py script
3. Passes through all command-line arguments
"""

import logging
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
# Shared with command.py which strips them from user-facing command strings.
TS_SRT_SOURCE_ARG = "--ts-srt-source"
TS_SRT_VIDEO_ARG = "--ts-srt-video"


def find_gopro_dashboard() -> Path | None:
    """Locate the original gopro-dashboard.py script.

    Searches in:
    1. bin/ directory relative to project root (development)
    2. System PATH (installed via pip)

    Returns:
        Path to gopro-dashboard.py or None if not found
    """
    # Check bin/ directory relative to telemetry-studio project root
    # This script is at: src/telemetry_studio/scripts/gopro_dashboard_wrapper.py
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


def _extract_srt_args() -> tuple[str | None, str | None]:
    """Extract and remove SRT-specific arguments from sys.argv.

    These custom args are consumed by the wrapper and must not be passed
    to gopro-dashboard.py (it would error on unknown args).

    Returns:
        Tuple of (srt_path, video_path). Either may be None.
    """
    srt_path = None
    video_path = None
    new_argv = []
    i = 0
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == TS_SRT_SOURCE_ARG and i + 1 < len(sys.argv):
            srt_path = sys.argv[i + 1]
            i += 2
        elif arg == TS_SRT_VIDEO_ARG and i + 1 < len(sys.argv):
            video_path = sys.argv[i + 1]
            i += 2
        else:
            new_argv.append(arg)
            i += 1
    sys.argv = new_argv
    return srt_path, video_path


def main():
    """Main entry point for the gopro-dashboard wrapper."""
    # Apply patches BEFORE importing anything from gopro_overlay
    # This ensures all classes are patched when gopro-dashboard.py loads them
    from telemetry_studio.patches import apply_patches

    apply_patches()
    logger.info("Patches applied successfully")

    # Extract SRT args before passing argv to gopro-dashboard.py
    srt_path, video_path = _extract_srt_args()

    # Patch GPX loading to use SRT directly (preserves camera metrics)
    if srt_path:
        from telemetry_studio.patches.gpx_patches import patch_gpx_load_for_srt

        patch_gpx_load_for_srt(srt_path, video_path)
        logger.info(f"SRT GPX patch applied: srt={srt_path}, video={video_path}")

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
        # Print error to stdout so render_service captures it in job logs
        error_msg = f"ERROR: {e}"
        print(error_msg, flush=True)
        logger.exception(f"Failed to execute gopro-dashboard.py: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
