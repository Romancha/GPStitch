"""Entry point for GPStitch server."""

import argparse
import shutil
import sys


def check_ffmpeg():
    """Check that ffmpeg and ffprobe are available in PATH."""
    missing = []
    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")
    if not shutil.which("ffprobe"):
        missing.append("ffprobe")

    if missing:
        print(f"Error: {', '.join(missing)} not found in PATH\n")
        print("Install FFmpeg:")
        print("  macOS:    brew install ffmpeg")
        print("  Ubuntu:   sudo apt install ffmpeg")
        print("  Windows:  choco install ffmpeg")
        print("  Other:    https://ffmpeg.org/download.html")
        sys.exit(1)


def main():
    """Start the GPStitch server."""
    parser = argparse.ArgumentParser(description="GPStitch - Web interface for telemetry video overlay configuration")
    parser.add_argument(
        "--host",
        default=None,
        help="Host to bind to (default: from config or 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind to (default: from config or 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    args = parser.parse_args()

    check_ffmpeg()

    # Import here to avoid circular imports and allow config override
    from gpstitch.config import settings

    host = args.host or settings.host
    port = args.port or settings.port

    import uvicorn

    url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"
    print(f"Starting GPStitch at {url}")
    print("Press Ctrl+C to stop")

    # Store URL for browser opening after server startup (see app.py lifespan)
    import gpstitch.app as _app_module

    _app_module._startup_url = url

    uvicorn.run(
        "gpstitch.app:app",
        host=host,
        port=port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
