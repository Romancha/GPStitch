# GPStitch

[![PyPI](https://img.shields.io/pypi/v/gpstitch)](https://pypi.org/project/gpstitch/)
[![Downloads](https://img.shields.io/pypi/dm/gpstitch)](https://pypi.org/project/gpstitch/)
[![GitHub release](https://img.shields.io/github/v/release/Romancha/GPStitch)](https://github.com/Romancha/GPStitch/releases)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A visual web interface for creating video overlays with GPS telemetry data. Wraps the powerful [gopro-overlay](https://github.com/time4tea/gopro-dashboard-overlay) library with an intuitive UI.

## Features

- **Quick Mode** — Select from predefined layouts, customize units and map styles
- **Advanced Mode** — Visual drag-and-drop editor for creating custom overlay layouts
- **Live Preview** — See your overlay in real-time as you configure it
- **DJI Drone Support** — Automatic SRT telemetry parsing with timezone and time alignment auto-detection
- **DJI Osmo Action Support** — Automatic detection of embedded GPS from DJI GPS Bluetooth Remote Controller (Action 4/5/6) — no secondary file needed
- **Non-GoPro Video Support** — Use any video with external GPX/FIT/SRT files for GPS data
- **Vertical Video Support** — Automatic rotation detection and correct overlay rendering
- **GPS Quality Analysis** — Automatic signal quality check with warnings before rendering
- **Template Management** — Save and load custom templates
- **Batch Rendering** — Process multiple files with the same settings
- **Shared GPX Batch Render** — Apply a single GPX track to multiple videos with automatic odometer offset per video
- **Background Jobs** — Render videos in the background with progress tracking
- **Overlay-Only Mode** — Render transparent telemetry overlays (no video) for compositing in Final Cut Pro, DaVinci Resolve, etc.

## Screenshots

### Quick Mode

Simple configuration with predefined layouts. Perfect for quick renders.

![Quick Mode](https://raw.githubusercontent.com/Romancha/GPStitch/main/docs/images/quick_mode.jpg)

### Advanced Mode

Full visual editor with drag-and-drop widgets. Create custom layouts with complete control.

![Advanced Mode](https://raw.githubusercontent.com/Romancha/GPStitch/main/docs/images/advanced_mode.jpg)

### DJI Drone Support

Use DJI drone videos with SRT telemetry files. Timezone offset and time alignment are automatically detected from video metadata, supporting different DJI models and firmware versions.

![DJI Drone Support](https://raw.githubusercontent.com/Romancha/GPStitch/main/docs/images/dji_drone.jpg)

Camera metrics (ISO, shutter, f-number, EV, color temperature) from SRT files are displayed directly on the video overlay.

![DJI Drone Overlay](https://raw.githubusercontent.com/Romancha/GPStitch/main/docs/images/dji_drone_screen_from_video.jpg)

### External GPX & Vertical Video

Use any video with external GPX/FIT files. Vertical videos are automatically detected and rendered correctly.

![External GPX & Vertical Video](https://raw.githubusercontent.com/Romancha/GPStitch/main/docs/images/external_gpx_vertical.jpg)

### Batch Rendering

Process multiple videos at once with the same overlay settings.

<p align="center">
<img src="https://raw.githubusercontent.com/Romancha/GPStitch/main/docs/images/batch_create.png" width="400" alt="Batch Create"/>
<img src="https://raw.githubusercontent.com/Romancha/GPStitch/main/docs/images/batch_progress.png" width="400" alt="Batch Progress"/>
</p>

### Shared GPX Batch Render

Apply a single GPX track to multiple videos recorded during the same activity. Each video automatically gets an odometer offset calculated from its creation time relative to the GPX track start, so the overlay shows the correct absolute distance from the beginning of the track.

### Overlay-Only Mode

Render telemetry overlays with a transparent background — without any source video. Use a GPX, FIT, or SRT file as the primary input, and GPStitch will generate a video with an alpha channel that you can layer on top of your footage in any video editor (Final Cut Pro, DaVinci Resolve, Premiere Pro, etc.).

**How to use:**

1. Upload a GPX, FIT, or SRT file as the primary file (no video needed)
2. Configure your overlay layout and widgets as usual
3. Select an encoding profile with transparency support:
   - **MOV (PNG)** — Lossless quality, best compatibility with Final Cut Pro and DaVinci Resolve (large files)
   - **VP9** — Good quality with alpha channel, smaller files
   - **VP8** — Alpha channel support, widest browser compatibility
4. Render — the output is a video with a transparent background ready for compositing

## Requirements

- Python 3.14+
- FFmpeg (must be installed and available in PATH)
- [gopro-overlay](https://pypi.org/project/gopro-overlay/) (installed automatically)

## Installation

### pipx (recommended)

```bash
# Install FFmpeg first
# macOS:    brew install ffmpeg
# Ubuntu:   sudo apt install ffmpeg
# Windows:  choco install ffmpeg

# Install GPStitch
pipx install gpstitch

# Run (opens browser automatically)
gpstitch

# Or with custom host/port
gpstitch --host 127.0.0.1 --port 8080
```

#### Optional: Cairo widgets support

Some layouts (e.g. `example`, `example-2`) use cairo-based widgets (gauges, circuit maps). These require `pycairo`, which needs the cairo system library:

```bash
# 1. Install system library
# macOS:    brew install cairo pkg-config
# Ubuntu:   sudo apt install libcairo2-dev pkg-config python3-dev

# 2. Install with cairo support (new install)
pipx install 'gpstitch[cairo]'

# Or add to existing installation
pipx inject gpstitch pycairo
```

Without pycairo, GPStitch works normally — cairo layouts will be marked as unavailable in the UI.

### From source

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/Romancha/GPStitch.git
cd gpstitch

# Install dependencies
uv sync

# Run the application
uv run gpstitch
```

Then open http://localhost:8000 in your browser.

### Supported Input Files

| Type | Formats | Description |
|------|---------|-------------|
| Video | `.mp4`, `.mov`, `.avi` | Video files (GoPro and DJI Action files may contain embedded GPS) |
| GPS Data | `.gpx`, `.fit`, `.srt` | External GPS tracks — GPX, FIT, or DJI SRT telemetry (optional) |

## Configuration

Environment variables (prefix: `GPSTITCH_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8000` | Server port |
| `LOCAL_MODE` | `true` | Use local file paths instead of uploads |
| `TEMPLATES_DIR` | `~/.gpstitch/templates` | Custom templates directory |
| `ENABLE_GOPRO_PATCHES` | `true` | Enable runtime patches for gopro-overlay |
| `USE_WRAPPER_SCRIPT` | `true` | Use wrapper script for rendering |

You can also use a `.env` file in the project root.

## Runtime Patches

GPStitch includes runtime patches for `gopro-overlay` that add:

- **Timecode preservation** — Maintains original video timecode for Final Cut Pro compatibility
- **Audio stream copy** — Preserves audio without re-encoding
- **Metadata preservation** — Keeps original video metadata in output
- **DJI camera metrics** — Extends overlay engine with ISO, shutter, f-number, EV, color temperature, and focal length from DJI SRT files
- **DJI Osmo Action GPS** — Loads embedded protobuf GPS telemetry from DJI Action cameras with GPS Bluetooth Remote Controller
- **Odometer offset** — Allows odometer to start from a custom offset value for shared GPX batch rendering

Patches are applied automatically at startup. To disable:

```bash
export GPSTITCH_ENABLE_GOPRO_PATCHES=false
export GPSTITCH_USE_WRAPPER_SCRIPT=false
```

## Development

```bash
# Install with dev dependencies
uv sync --all-extras

# Linting and formatting
uv run ruff check src tests
uv run ruff format src tests

# Run tests
uv run pytest

# Run all checks (lint + format + tests)
uv run ruff check src tests && uv run ruff format src tests && uv run pytest

# Run E2E tests (requires: uv run playwright install chromium)
uv run pytest tests/e2e/ -v
```

### Project Structure

```
src/gpstitch/
├── main.py          # CLI entry point
├── app.py           # FastAPI application
├── config.py        # Settings
├── api/             # API routers
├── models/          # Pydantic data models
├── services/        # Business logic
└── static/          # Frontend assets
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the GPL-3.0 License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [gopro-dashboard-overlay](https://github.com/time4tea/gopro-dashboard-overlay) — The underlying overlay rendering engine
